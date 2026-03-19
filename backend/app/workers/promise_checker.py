"""
Promise checker — runs every hour at :30.

The agent can make promises to clients:
  "Vou te lembrar sobre a conta do cartão na sexta"
  "Na semana que vem te mando o relatório do mês"

These are stored in tenant_{id}_context.agent_promises.
This worker checks for overdue promises and sends follow-up messages.
"""
import asyncio
import logging
from datetime import datetime, timezone

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


@celery.task(name="app.workers.promise_checker.check_all_promises")
def check_all_promises():
    """Check for overdue agent promises and send follow-up messages."""
    async def _run():
        Session = _get_session()
        async with Session() as db:
            result = await db.execute(
                text("SELECT id, whatsapp_number, telegram_chat_id FROM tenants WHERE is_active = true")
            )
            tenants = [dict(r._mapping) for r in result.fetchall()]

        now = datetime.now(timezone.utc)
        logger.info(f"Checking promises for {len(tenants)} tenants")

        for tenant in tenants:
            tenant_id = str(tenant["id"])
            ctx_schema = f"tenant_{tenant_id.replace('-', '_')}_context"

            try:
                async with Session() as db:
                    result = await db.execute(
                        text(f"""
                            SELECT id, agent_id, promise, due_date
                            FROM "{ctx_schema}".agent_promises
                            WHERE status = 'pending'
                              AND due_date <= :now
                            LIMIT 5
                        """),
                        {"now": now},
                    )
                    due_promises = [dict(r._mapping) for r in result.fetchall()]

                for promise in due_promises:
                    try:
                        follow_up = await _agent.respond(
                            tenant_id=tenant_id,
                            message=(
                                f"[SISTEMA: Você prometeu ao cliente: '{promise['promise']}'. "
                                f"Envie uma mensagem natural de acompanhamento, lembrando o cliente "
                                f"e cumprindo sua promessa. Seja breve e natural.]"
                            ),
                            channel="system",
                            session_id=f"promise_{str(promise['id'])[:8]}",
                        )

                        send_notification.delay(
                            tenant_data={
                                "whatsapp_number": tenant.get("whatsapp_number"),
                                "telegram_chat_id": tenant.get("telegram_chat_id"),
                            },
                            message=follow_up.content,
                        )

                        # Mark promise as fulfilled
                        async with Session() as db:
                            await db.execute(
                                text(f"""
                                    UPDATE "{ctx_schema}".agent_promises
                                    SET status = 'fulfilled', fulfilled_at = NOW()
                                    WHERE id = :id::uuid
                                """),
                                {"id": str(promise["id"])},
                            )
                            await db.commit()

                        logger.info(f"Promise fulfilled for tenant {tenant_id}: {promise['promise'][:50]}")

                    except Exception as e:
                        logger.error(f"Failed to fulfill promise {promise['id']}: {e}")

            except Exception as e:
                logger.error(f"Promise check failed for tenant {tenant_id}: {e}")

    asyncio.run(_run())
