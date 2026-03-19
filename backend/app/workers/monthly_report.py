"""
Monthly report worker — runs on the 1st of each month at 8am.
Generates comprehensive financial report for the previous month.
"""
import asyncio
import logging
from datetime import date
from calendar import monthrange

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text

from app.workers.celery_app import celery
from app.workers.notification_worker import send_notification
from app.config import settings
from app.agent.core import FinAgent

logger = logging.getLogger(__name__)

_agent = FinAgent()


def _get_session() -> async_sessionmaker:
    engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_size=5)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _get_previous_month() -> tuple[date, date]:
    today = date.today()
    if today.month == 1:
        year, month = today.year - 1, 12
    else:
        year, month = today.year, today.month - 1
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    return first, last


async def _generate_monthly_report(db: AsyncSession, tenant_id: str) -> tuple[str, dict]:
    """Generate full monthly report. Returns (message, report_data)."""
    tenant_id_clean = tenant_id.replace("-", "_")
    fin_schema = f"tenant_{tenant_id_clean}_financial"
    first, last = _get_previous_month()

    result = await db.execute(
        text(f"""
            SELECT
                SUM(CASE WHEN type='income' AND status='paid' THEN amount ELSE 0 END) AS income,
                SUM(CASE WHEN type='expense' AND status='paid' THEN amount ELSE 0 END) AS expenses,
                COUNT(*) AS total_transactions
            FROM "{fin_schema}".transactions
            WHERE date BETWEEN :start AND :end
        """),
        {"start": first, "end": last},
    )
    row = dict((result.fetchone() or {})._mapping) if result.fetchone() else {}

    # Top categories
    cat_result = await db.execute(
        text(f"""
            SELECT COALESCE(c.name, 'Outros') AS category, SUM(t.amount) AS total
            FROM "{fin_schema}".transactions t
            LEFT JOIN "{fin_schema}".categories c ON c.id = t.category_id
            WHERE t.date BETWEEN :start AND :end AND t.type='expense' AND t.status='paid'
            GROUP BY c.name ORDER BY total DESC LIMIT 5
        """),
        {"start": first, "end": last},
    )
    top_cats = [dict(r._mapping) for r in cat_result.fetchall()]

    income = float(row.get("income") or 0)
    expenses = float(row.get("expenses") or 0)
    net = income - expenses

    report_data = {
        "period": f"{first.strftime('%B %Y')}",
        "income": income,
        "expenses": expenses,
        "net": net,
        "top_categories": top_cats,
    }

    month_name = first.strftime("%B %Y").capitalize()
    cats_text = "\n".join(
        [f"  • {c['category']}: R$ {float(c['total']):.2f}" for c in top_cats]
    ) or "  Nenhuma categoria registrada"

    prompt = (
        f"[SISTEMA - Relatório Mensal: {month_name}]\n"
        f"Receitas: R$ {income:.2f}\n"
        f"Despesas: R$ {expenses:.2f}\n"
        f"Resultado: R$ {net:+.2f}\n"
        f"Top categorias de despesa:\n{cats_text}\n\n"
        f"Escreva o relatório mensal de forma pessoal e profissional. "
        f"Dê 2-3 insights específicos sobre o mês, destaque pontos positivos, "
        f"e sugira 1-2 melhorias para o próximo mês. Seja direto e útil."
    )

    try:
        message = await _agent.respond(
            tenant_id=tenant_id,
            message=prompt,
            channel="system",
            session_id=f"monthly_{first.isoformat()}",
        )
    except Exception as e:
        logger.error(f"Agent monthly report failed: {e}")
        message = (
            f"📊 *Relatório de {month_name}*\n\n"
            f"💰 Receitas: R$ {income:.2f}\n"
            f"💸 Despesas: R$ {expenses:.2f}\n"
            f"{'📈' if net >= 0 else '📉'} Resultado: R$ {net:+.2f}\n\n"
            f"🏷️ *Maiores despesas:*\n{cats_text}"
        )

    return message, report_data


@celery.task(name="app.workers.monthly_report.send_monthly_reports")
def send_monthly_reports():
    """Send monthly reports to all active tenants."""
    async def _run():
        Session = _get_session()
        async with Session() as db:
            result = await db.execute(
                text("SELECT id, whatsapp_number, telegram_chat_id FROM tenants WHERE is_active = true")
            )
            tenants = [dict(r._mapping) for r in result.fetchall()]

        logger.info(f"Sending monthly reports to {len(tenants)} tenants")

        for tenant in tenants:
            tenant_id = str(tenant["id"])
            try:
                async with Session() as db:
                    message, report_data = await _generate_monthly_report(db, tenant_id)
                    # Save report to DB
                    first, last = _get_previous_month()
                    fin_schema = f"tenant_{tenant_id.replace('-', '_')}_financial"
                    import json
                    await db.execute(
                        text(f"""
                            INSERT INTO "{fin_schema}".reports
                                (type, period_start, period_end, data, generated_by)
                            VALUES ('monthly', :start, :end, :data::jsonb, 'ai')
                        """),
                        {"start": first, "end": last, "data": json.dumps(report_data)},
                    )
                    await db.commit()

                send_notification.delay(
                    tenant_data={
                        "whatsapp_number": tenant.get("whatsapp_number"),
                        "telegram_chat_id": tenant.get("telegram_chat_id"),
                    },
                    message=message,
                )
                logger.info(f"Monthly report sent to tenant {tenant_id[:8]}")

            except Exception as e:
                logger.error(f"Monthly report failed for tenant {tenant_id}: {e}")

    asyncio.run(_run())
