"""
Weekly summary worker — runs every Monday at 9am.
Generates a personalized financial summary for each active tenant
and sends it via WhatsApp/Telegram.
"""
import asyncio
import logging
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text

from app.workers.celery_app import celery
from app.workers.notification_worker import send_notification
from app.config import settings
from app.agent.core import FinAgent

logger = logging.getLogger(__name__)

# Shared stateless FinAgent instance
_agent = FinAgent()


def _get_session() -> async_sessionmaker:
    engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_size=5)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _generate_weekly_summary(db: AsyncSession, tenant_id: str) -> str:
    """Generate a weekly summary message using the AI agent."""
    tenant_id_clean = tenant_id.replace("-", "_")
    fin_schema = f"tenant_{tenant_id_clean}_financial"

    today = date.today()
    week_start = today - timedelta(days=7)

    # Get week's financial data
    result = await db.execute(
        text(f"""
            SELECT
                SUM(CASE WHEN type='income' AND status='paid' THEN amount ELSE 0 END) AS income,
                SUM(CASE WHEN type='expense' AND status='paid' THEN amount ELSE 0 END) AS expenses,
                COUNT(*) FILTER (WHERE status='pending') AS pending_count,
                SUM(amount) FILTER (WHERE status='pending' AND type='expense') AS pending_amount
            FROM "{fin_schema}".transactions
            WHERE date BETWEEN :start AND :end
        """),
        {"start": week_start, "end": today},
    )
    row = result.fetchone()
    data = dict(row._mapping) if row else {}

    income = float(data.get("income") or 0)
    expenses = float(data.get("expenses") or 0)
    net = income - expenses
    pending_count = int(data.get("pending_count") or 0)
    pending_amount = float(data.get("pending_amount") or 0)

    # Ask the agent to write the summary in natural language
    prompt = (
        f"[SISTEMA - Resumo Semanal]\n"
        f"Semana: {week_start.strftime('%d/%m')} a {today.strftime('%d/%m/%Y')}\n"
        f"Receitas: R$ {income:.2f}\n"
        f"Despesas: R$ {expenses:.2f}\n"
        f"Resultado: R$ {net:+.2f}\n"
        f"Contas pendentes: {pending_count} (R$ {pending_amount:.2f})\n\n"
        f"Escreva um resumo semanal personalizado, amigável e motivador para o cliente. "
        f"Mencione os números, dê um insight relevante, e encoraje boas práticas financeiras. "
        f"Máximo 3 parágrafos curtos. Não use muitos emojis."
    )

    try:
        agent_response = await _agent.respond(
            tenant_id=tenant_id,
            message=prompt,
            channel="system",
            session_id=f"weekly_{today.isoformat()}",
        )
        return agent_response.content
    except Exception as e:
        logger.error(f"Agent summary generation failed: {e}")
        # Fallback to template
        return (
            f"📊 *Resumo da semana ({week_start.strftime('%d/%m')} - {today.strftime('%d/%m')})*\n\n"
            f"✅ Receitas: R$ {income:.2f}\n"
            f"❌ Despesas: R$ {expenses:.2f}\n"
            f"{'📈' if net >= 0 else '📉'} Resultado: R$ {net:+.2f}\n"
            + (f"\n⚠️ Você tem {pending_count} conta(s) pendente(s) no total de R$ {pending_amount:.2f}" if pending_count else "")
        )


@celery.task(name="app.workers.weekly_summary.send_weekly_summaries")
def send_weekly_summaries():
    """Send weekly financial summaries to all active tenants."""
    async def _run():
        Session = _get_session()
        async with Session() as db:
            result = await db.execute(
                text("""
                    SELECT id, whatsapp_number, telegram_chat_id, settings
                    FROM tenants WHERE is_active = true
                """)
            )
            tenants = [dict(r._mapping) for r in result.fetchall()]

        logger.info(f"Sending weekly summaries to {len(tenants)} tenants")

        for tenant in tenants:
            tenant_id = str(tenant["id"])
            # Check if tenant opted out of weekly summaries
            tenant_settings = tenant.get("settings") or {}
            if not tenant_settings.get("weekly_summary", True):
                continue

            try:
                async with Session() as db:
                    summary = await _generate_weekly_summary(db, tenant_id)

                send_notification.delay(
                    tenant_data={
                        "whatsapp_number": tenant.get("whatsapp_number"),
                        "telegram_chat_id": tenant.get("telegram_chat_id"),
                    },
                    message=summary,
                )
                logger.info(f"Weekly summary sent to tenant {tenant_id[:8]}")

            except Exception as e:
                logger.error(f"Weekly summary failed for tenant {tenant_id}: {e}")

    asyncio.run(_run())
