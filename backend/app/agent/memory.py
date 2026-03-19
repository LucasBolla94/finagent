"""
Memory Manager — The Agent's Long-Term Memory

Manages three types of memory for each Agent-Client relationship:
1. Short-term: Last N messages of the current session
2. Medium-term: Weekly summaries and key moments
3. Long-term: Semantic embeddings — searchable by meaning, not just keywords

This is what allows the agent to say:
"Na semana passada você mencionou aquela reunião com o banco — como foi?"
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.config import settings

logger = logging.getLogger(__name__)


class MemoryManager:
    def __init__(self, tenant_id: str, agent_id: str, db: AsyncSession):
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.db = db
        self.context_schema = f"tenant_{tenant_id.replace('-', '_')}_context"

    # ─────────────────────────────────────────────
    # SHORT-TERM MEMORY (conversation history)
    # ─────────────────────────────────────────────

    async def get_recent_messages(self, limit: int = 20) -> list[dict]:
        """Returns the last N messages for context injection."""
        result = await self.db.execute(
            text(f"""
                SELECT role, content, tool_calls, created_at
                FROM "{self.context_schema}".conversation_history
                WHERE agent_id = :agent_id
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"agent_id": self.agent_id, "limit": limit}
        )
        rows = result.fetchall()
        return [
            {
                "role": row.role,
                "content": row.content,
                "tool_calls": row.tool_calls,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in reversed(rows)  # chronological order
        ]

    async def save_message(
        self,
        role: str,
        content: str,
        channel: str = "whatsapp",
        tool_calls: Optional[dict] = None,
        model_used: Optional[str] = None,
        tokens_used: int = 0,
    ) -> None:
        await self.db.execute(
            text(f"""
                INSERT INTO "{self.context_schema}".conversation_history
                (agent_id, channel, role, content, tool_calls, model_used, tokens_used, created_at)
                VALUES (:agent_id, :channel, :role, :content, :tool_calls, :model_used, :tokens_used, NOW())
            """),
            {
                "agent_id": self.agent_id,
                "channel": channel,
                "role": role,
                "content": content,
                "tool_calls": json.dumps(tool_calls) if tool_calls else None,
                "model_used": model_used,
                "tokens_used": tokens_used,
            }
        )
        await self.db.commit()

    # ─────────────────────────────────────────────
    # MEDIUM-TERM MEMORY (key moments + promises)
    # ─────────────────────────────────────────────

    async def save_key_moment(
        self,
        memory_type: str,  # personal | financial | preference | achievement | concern
        content: str,
        importance: int = 3,  # 1-5
    ) -> None:
        """Save an important moment that the agent should remember long-term."""
        await self.db.execute(
            text(f"""
                INSERT INTO "{self.context_schema}".key_moments
                (agent_id, type, content, importance, created_at)
                VALUES (:agent_id, :type, :content, :importance, NOW())
            """),
            {
                "agent_id": self.agent_id,
                "type": memory_type,
                "content": content,
                "importance": importance,
            }
        )
        await self.db.commit()

        # Also create an embedding for this moment so it's searchable
        await self._embed_and_store(
            text=content,
            entity_type="key_moment",
            metadata={"type": memory_type, "importance": importance}
        )

    async def get_key_moments(self, limit: int = 10) -> list[dict]:
        """Get the most important moments, ordered by importance and recency."""
        result = await self.db.execute(
            text(f"""
                SELECT type, content, importance, created_at
                FROM "{self.context_schema}".key_moments
                WHERE agent_id = :agent_id
                ORDER BY importance DESC, created_at DESC
                LIMIT :limit
            """),
            {"agent_id": self.agent_id, "limit": limit}
        )
        rows = result.fetchall()
        return [
            {
                "type": row.type,
                "content": row.content,
                "importance": row.importance,
                "date": row.created_at.strftime("%d/%m/%Y") if row.created_at else None,
            }
            for row in rows
        ]

    async def save_promise(self, promise: str, due_date: datetime) -> None:
        """Agent made a promise — track it and follow up automatically."""
        await self.db.execute(
            text(f"""
                INSERT INTO "{self.context_schema}".agent_promises
                (agent_id, promise, due_date, status, created_at)
                VALUES (:agent_id, :promise, :due_date, 'pending', NOW())
            """),
            {"agent_id": self.agent_id, "promise": promise, "due_date": due_date}
        )
        await self.db.commit()

    async def get_pending_promises(self) -> list[dict]:
        """Returns promises that are due or overdue — agent must follow up."""
        result = await self.db.execute(
            text(f"""
                SELECT id, promise, due_date
                FROM "{self.context_schema}".agent_promises
                WHERE agent_id = :agent_id
                  AND status = 'pending'
                  AND due_date <= NOW() + INTERVAL '1 day'
                ORDER BY due_date ASC
            """),
            {"agent_id": self.agent_id}
        )
        return [
            {"id": str(row.id), "promise": row.promise, "due_date": row.due_date.isoformat()}
            for row in result.fetchall()
        ]

    # ─────────────────────────────────────────────
    # LONG-TERM MEMORY (semantic search)
    # ─────────────────────────────────────────────

    async def semantic_search(self, query: str, limit: int = 5) -> list[dict]:
        """
        Search memory by meaning, not keywords.
        "quando paguei a conta de luz?" will find transactions with "energia elétrica", "CEMIG", etc.
        """
        query_embedding = await self._create_embedding(query)
        if not query_embedding:
            return []

        result = await self.db.execute(
            text(f"""
                SELECT entity_type, content_text, metadata,
                       1 - (embedding <=> :embedding::vector) AS similarity
                FROM "{self.context_schema}".embeddings
                WHERE 1 - (embedding <=> :embedding::vector) > 0.6
                ORDER BY embedding <=> :embedding::vector
                LIMIT :limit
            """),
            {"embedding": str(query_embedding), "limit": limit}
        )
        rows = result.fetchall()
        return [
            {
                "type": row.entity_type,
                "content": row.content_text,
                "metadata": row.metadata,
                "similarity": round(row.similarity, 3),
            }
            for row in rows
        ]

    async def _embed_and_store(
        self,
        text: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> None:
        """Create embedding and store in pgvector."""
        embedding = await self._create_embedding(text)
        if not embedding:
            return

        await self.db.execute(
            text(f"""
                INSERT INTO "{self.context_schema}".embeddings
                (agent_id, entity_type, entity_id, content_text, embedding, metadata, created_at)
                VALUES (:agent_id, :entity_type, :entity_id, :content_text, :embedding::vector, :metadata, NOW())
            """),
            {
                "agent_id": self.agent_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "content_text": text,
                "embedding": str(embedding),
                "metadata": json.dumps(metadata or {}),
            }
        )
        await self.db.commit()

    async def _create_embedding(self, text: str) -> Optional[list[float]]:
        """Call OpenRouter to create a text embedding."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{settings.OPENROUTER_BASE_URL}/embeddings",
                    headers={
                        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={"model": settings.MODEL_EMBEDDING, "input": text},
                    timeout=15.0,
                )
                data = response.json()
                return data["data"][0]["embedding"]
        except Exception as e:
            logger.error(f"Embedding creation failed: {e}")
            return None

    # ─────────────────────────────────────────────
    # CONTEXT BUILDER — used before every response
    # ─────────────────────────────────────────────

    async def build_context_for_prompt(self, current_message: str) -> dict:
        """
        Assembles everything the agent needs to respond intelligently.
        Called before every AI request.
        """
        recent_messages = await self.get_recent_messages(limit=20)
        key_moments = await self.get_key_moments(limit=8)
        semantic_memories = await self.semantic_search(current_message, limit=5)
        pending_promises = await self.get_pending_promises()

        return {
            "recent_messages": recent_messages,
            "key_moments": key_moments,
            "semantic_memories": semantic_memories,
            "pending_promises": pending_promises,
        }

    def format_memory_for_prompt(self, context: dict) -> str:
        """Formats memory context as readable text for the system prompt."""
        sections = []

        if context.get("key_moments"):
            moments_text = "\n".join([
                f"  [{m['date']}] ({m['type']}) {m['content']}"
                for m in context["key_moments"]
            ])
            sections.append(f"## MOMENTOS IMPORTANTES LEMBRADOS:\n{moments_text}")

        if context.get("semantic_memories"):
            memories_text = "\n".join([
                f"  - {m['content']}" for m in context["semantic_memories"]
                if m["similarity"] > 0.7
            ])
            if memories_text:
                sections.append(f"## MEMÓRIAS RELACIONADAS À MENSAGEM ATUAL:\n{memories_text}")

        if context.get("pending_promises"):
            promises_text = "\n".join([
                f"  - PENDENTE: {p['promise']} (prazo: {p['due_date'][:10]})"
                for p in context["pending_promises"]
            ])
            sections.append(
                f"## PROMESSAS PENDENTES (mencione ou cumpra nessa conversa):\n{promises_text}"
            )

        return "\n\n".join(sections)
