"""
Alert checker worker — runs every hour.
Checks all active alerts for all active tenants.

Alert types handled:
- balance_below      : account balance < threshold
- expense_above      : monthly expenses > threshold
- bill_due           : transactions due in N days (status=pending, type=expense)
- category_limit     : spending in category > budget for current month
"""
import asyncio
import logging
from datetime import date, datetime
from calendar import monthrange

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text

from app.workers.celery_app import celery
from app.workers.notification_worker import send_notification
from app.config import settings

logger = logging.getLogger(__name__)


def _get_session() -> async_sessionmaker:
    engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_size=5)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _check_tenant_alerts(db: AsyncSession, tenant: dict) -> list[str]:
    """Check all alerts for a single tenant. Returns list of triggered messages."""
    tenant_id = str(tenant["id"])
    fin_schema = f"tenant_{tenant_id.replace('-', '_')}_financial"
    triggered = []

    # Get active alerts
    result = await db.execute(
        text(f"""
            SELECT id, type, name, condition, message, channels
            FROM "{fin_schema}".alerts
            WHERE is_active = true
        """)
    )
    alerts = [dict(r._mapping) for r in result.fetchall()]

    for alert in alerts:
        alert_type = alert["type"]
        condition = alert.get("condition") or {}
        should_trigger = False

        try:
            if alert_type == "balance_below":
                threshold = float(condition.get("threshold", 0))
                account_id = condition.get("account_id")
                acct_filter = "AND account_id = :acct_id::uuid" if account_id else ""
                params = {"threshold": threshold}
                if account_id:
                    params["acct_id"] = account_id

                balance_sql = text(f"""
                    SELECT COALESCE(SUM(CASE WHEN type='income' AND status='paid' THEN amount
                                        WHEN type='expense' AND status='paid' THEN -amount
                                        ELSE 0 END), 0) AS balance
                    FROM "{fin_schema}".transactions
                    WHERE 1=1 {acct_filter}
                """)
                bal_result = await db.execute(balance_sql, params)
                balance = float((bal_result.fetchone() or [0])[0])
                should_trigger = balance < threshold

            elif alert_type == "expense_above":
                threshold = float(condition.get("threshold", 0))
                today = date.today()
                first_day = today.replace(day=1)
                exp_result = await db.execute(
                    text(f"""
                        SELECT COALESCE(SUM(amount), 0) AS total
                        FROM "{fin_schema}".transactions
                        WHERE type='expense' AND status='paid'
                          AND date >= :first_day
                    """),
                    {"first_day": first_day},
                )
                total_expenses = float((exp_result.fetchone() or [0])[0])
                should_trigger = total_expenses > threshold

            elif alert_type == "bill_due":
                days_ahead = int(condition.get("days", 3))
                today = date.today()
                future = today.replace(day=today.day + days_ahead) if today.day + days_ahead <= 28 else today
                due_result = await db.execute(
                    text(f"""
                        SELECT COUNT(*) FROM "{fin_schema}".transactions
                        WHERE status='pending' AND type='expense'
                          AND due_date BETWEEN :today AND :future
                    """),
                    {"today": today, "future": future},
                )
                count = (due_result.fetchone() or [0])[0]
                should_trigger = count > 0

            elif alert_type == "category_limit":
                category_id = condition.get("category_id")
                threshold = float(condition.get("threshold", 0))
                if category_id:
                    today = date.today()
                    first_day = today.replace(day=1)
                    cat_result = await db.execute(
                        text(f"""
                            SELECT COALESCE(SUM(amount), 0) FROM "{fin_schema}".transactions
                            WHERE category_id = :cat_id::uuid
                              AND type='expense' AND status='paid'
                              AND date >= :first_day
                        """),
                        {"cat_id": category_id, "first_day": first_day},
                    )
                    spent = float((cat_result.fetchone() or [0])[0])
                    should_trigger = spent > threshold

            if should_trigger:
                triggered.append(alert["message"])
                # Update trigger stats
                await db.execute(
                    text(f"""
                        UPDATE "{fin_schema}".alerts
                        SET last_triggered = NOW(), trigger_count = trigger_count + 1
                        WHERE id = :id::uuid
                    """),
                    {"id": str(alert["id"])},
                )

        except Exception as e:
            logger.error(f"Alert check error for {alert_type}: {e}")

    if triggered:
        await db.commit()

    return triggered


@celery.task(name="app.workers.alert_checker.check_all_alerts")
def check_all_alerts():
    """
    Check all active alerts for all active tenants.
    Triggers notifications when conditions are met.
    """
    async def _run():
        Session = _get_session()
        async with Session() as db:
            # Get all active tenants
            result = await db.execute(
                text("""
                    SELECT id, whatsapp_number, telegram_chat_id
                    FROM tenants
                    WHERE is_active = true
                """)
            )
            tenants = [dict(r._mapping) for r in result.fetchall()]

        logger.info(f"Checking alerts for {len(tenants)} tenants")

        for tenant in tenants:
            try:
                async with Session() as db:
                    triggered_messages = await _check_tenant_alerts(db, tenant)

                for msg in triggered_messages:
                    send_notification.delay(
                        tenant_data={
                            "whatsapp_number": tenant.get("whatsapp_number"),
                            "telegram_chat_id": tenant.get("telegram_chat_id"),
                        },
                        message=msg,
                    )
                    logger.info(f"Alert triggered for tenant {tenant['id']}: {msg[:50]}")

            except Exception as e:
                logger.error(f"Alert check failed for tenant {tenant['id']}: {e}")

    asyncio.run(_run())
    logger.info("Alert check cycle complete")
