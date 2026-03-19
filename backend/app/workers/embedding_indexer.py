"""
Embedding indexer — indexes new transactions and conversations into pgvector.
Called after a transaction is created or after a conversation session ends.

This enables semantic search:
  "Quanto gastei com Uber em dezembro?" → finds all ride-hailing transactions
  "Mostre transações do supermercado" → finds all grocery-related transactions
"""
import asyncio
import json
import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text

from app.workers.celery_app import celery
from app.config import settings

logger = logging.getLogger(__name__)


def _get_session() -> async_sessionmaker:
    engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_size=5)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _get_embedding(text_content: str) -> list[float]:
    """Get embedding vector from OpenRouter (OpenAI-compatible)."""
    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.MODEL_EMBEDDING,
        "input": text_content[:8000],  # Limit to avoid token overflow
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.OPENROUTER_BASE_URL}/embeddings",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]


@celery.task(name="app.workers.embedding_indexer.index_transaction", bind=True, max_retries=3)
def index_transaction(self, tenant_id: str, transaction_id: str, agent_id: str):
    """
    Index a single transaction into pgvector.
    Called after each transaction is created/imported.
    """
    async def _run():
        tenant_id_clean = tenant_id.replace("-", "_")
        fin_schema = f"tenant_{tenant_id_clean}_financial"
        ctx_schema = f"tenant_{tenant_id_clean}_context"

        Session = _get_session()
        async with Session() as db:
            # Get transaction
            result = await db.execute(
                text(f"""
                    SELECT date, amount, description, type, category_id
                    FROM "{fin_schema}".transactions
                    WHERE id = :tx_id::uuid
                """),
                {"tx_id": transaction_id},
            )
            row = result.fetchone()
            if not row:
                return

            tx = dict(row._mapping)
            # Build text for embedding
            content = (
                f"{tx['type'].upper()} "
                f"R$ {tx['amount']:.2f} "
                f"em {tx['date']} — "
                f"{tx['description']}"
            )

            embedding = await _get_embedding(content)

            # Store in context schema embeddings table
            await db.execute(
                text(f"""
                    INSERT INTO "{ctx_schema}".embeddings
                        (id, agent_id, entity_type, entity_id, content_text, embedding)
                    VALUES
                        (uuid_generate_v4(), :agent_id::uuid, 'transaction',
                         :entity_id::uuid, :content, :embedding)
                    ON CONFLICT DO NOTHING
                """),
                {
                    "agent_id": agent_id,
                    "entity_id": transaction_id,
                    "content": content,
                    "embedding": embedding,
                },
            )
            await db.commit()
            logger.info(f"Indexed transaction {transaction_id[:8]} for tenant {tenant_id[:8]}")

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.error(f"Embedding index error: {exc}")
        raise self.retry(exc=exc, countdown=120)


@celery.task(name="app.workers.embedding_indexer.index_pending_transactions")
def index_pending_transactions():
    """
    Bulk index all transactions that don't have embeddings yet.
    Runs once on startup and periodically.
    """
    async def _run():
        Session = _get_session()
        async with Session() as db:
            result = await db.execute(
                text("SELECT id, agent_id FROM tenants WHERE is_active = true")
            )
            tenants = [dict(r._mapping) for r in result.fetchall()]

        total_indexed = 0
        for tenant in tenants:
            tenant_id = str(tenant["id"])
            agent_id = str(tenant["agent_id"]) if tenant.get("agent_id") else None
            if not agent_id:
                continue

            tenant_id_clean = tenant_id.replace("-", "_")
            fin_schema = f"tenant_{tenant_id_clean}_financial"
            ctx_schema = f"tenant_{tenant_id_clean}_context"

            try:
                async with Session() as db:
                    # Find transactions without embeddings
                    result = await db.execute(
                        text(f"""
                            SELECT t.id FROM "{fin_schema}".transactions t
                            WHERE NOT EXISTS (
                                SELECT 1 FROM "{ctx_schema}".embeddings e
                                WHERE e.entity_id = t.id AND e.entity_type = 'transaction'
                            )
                            LIMIT 50
                        """)
                    )
                    unindexed = [str(r[0]) for r in result.fetchall()]

                for tx_id in unindexed:
                    index_transaction.delay(tenant_id, tx_id, agent_id)
                    total_indexed += 1

            except Exception as e:
                logger.error(f"Bulk index error for tenant {tenant_id}: {e}")

        logger.info(f"Queued {total_indexed} transactions for embedding indexing")

    asyncio.run(_run())
