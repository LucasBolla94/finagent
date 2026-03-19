"""
Agent Core — The Brain

Orchestrates every response:
1. Load agent identity + behavioral instructions from DB (per request)
2. Load client memory (short + medium + semantic)
3. Select the best model for this task
4. Run the OpenRouter tool-calling loop
5. Extract key moments and promises to save
6. Update behavioral profile

Design: FinAgent is stateless. All context is loaded from DB inside respond().
This allows a single FinAgent() instance to safely serve multiple tenants
and be reused across workers/endpoints without state leaking between requests.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.config import settings
from app.agent.behavioral_analyzer import BehavioralAnalyzer, BehavioralProfile
from app.agent.memory import MemoryManager
from app.agent.tools import TOOLS, execute_tool
from app.agent.model_selector import ModelSelector

logger = logging.getLogger(__name__)

analyzer = BehavioralAnalyzer()
model_selector = ModelSelector()


class AgentResponse:
    def __init__(
        self,
        content: str,
        tool_calls_made: list[str],
        model_used: str,
        tokens_used: int,
    ):
        self.content = content
        self.tool_calls_made = tool_calls_made
        self.model_used = model_used
        self.tokens_used = tokens_used


class FinAgent:
    """
    Stateless agent class. One shared instance per process.
    All per-request state is loaded from DB inside respond().
    Never store tenant/request data as instance attributes.
    """

    def __init__(self):
        pass  # intentionally empty — stateless

    async def respond(
        self,
        tenant_id: str,
        message: str,
        channel: str = "whatsapp",
        session_id: Optional[str] = None,
        sent_at: Optional[datetime] = None,
        db: Optional[AsyncSession] = None,
    ) -> AgentResponse:
        """
        Main entry point. Loads all context from DB and returns an intelligent response.

        Args:
            tenant_id: UUID string of the tenant (client)
            message: The user's message text
            channel: 'whatsapp', 'telegram', 'web', or 'system'
            session_id: Optional session identifier for conversation continuity
            sent_at: Timestamp of the original message (for behavioral analysis)
            db: Optional AsyncSession. If None, a new session is created internally.
        """
        # If no db session provided, create our own (used by workers)
        _own_db = db is None
        if _own_db:
            from app.database import AsyncSessionLocal
            _db = AsyncSessionLocal()
        else:
            _db = db

        try:
            return await self._do_respond(
                tenant_id=tenant_id,
                message=message,
                channel=channel,
                session_id=session_id,
                sent_at=sent_at,
                db=_db,
            )
        finally:
            if _own_db:
                await _db.close()

    async def _do_respond(
        self,
        tenant_id: str,
        message: str,
        channel: str,
        session_id: Optional[str],
        sent_at: Optional[datetime],
        db: AsyncSession,
    ) -> AgentResponse:
        """Internal method that does the actual work with a guaranteed DB session."""

        # 1. Load agent config and behavioral profile for this tenant
        try:
            agent_data, behavioral_profile_data = await self._load_tenant_context(tenant_id, db)
        except Exception as e:
            logger.error(f"Failed to load agent context for tenant {tenant_id}: {e}")
            return AgentResponse(
                content="Estou com um problema técnico no momento. Por favor, tente novamente em instantes.",
                tool_calls_made=[],
                model_used="none",
                tokens_used=0,
            )

        agent_id = str(agent_data["id"])
        behavioral_profile = BehavioralProfile(behavioral_profile_data)
        memory = MemoryManager(tenant_id, agent_id, db)

        # 2. Analyze message behavior signals
        signals = analyzer.analyze(message, sent_at)
        behavioral_profile.update(signals)
        await self._save_behavioral_profile(tenant_id, agent_id, behavioral_profile, db)

        # 3. Load memory context
        memory_context = await memory.build_context_for_prompt(message)
        recent_messages = memory_context.pop("recent_messages")

        # 4. Build system prompt
        system_prompt = self._build_system_prompt(agent_data, behavioral_profile, memory, memory_context)

        # 5. Prepare message history for API
        messages = self._prepare_messages(recent_messages, message)

        # 6. Select model based on task complexity
        model = model_selector.select(message, recent_messages)

        # 7. Run tool-calling loop (max 5 iterations)
        tool_calls_made = []
        final_content = ""
        total_tokens = 0

        for _iteration in range(5):
            response_data = await self._call_openrouter(
                model=model,
                system_prompt=system_prompt,
                messages=messages,
            )

            if not response_data:
                final_content = "Desculpe, tive um problema técnico. Pode repetir?"
                break

            choices = response_data.get("choices")
            if not choices:
                logger.error(f"OpenRouter returned no choices: {response_data}")
                final_content = "Recebi uma resposta inesperada da IA. Tente novamente."
                break

            choice = choices[0]
            total_tokens += response_data.get("usage", {}).get("total_tokens", 0)
            finish_reason = choice.get("finish_reason")
            msg = choice.get("message", {})

            # Model wants to call a tool
            if finish_reason == "tool_calls" and msg.get("tool_calls"):
                messages.append(msg)

                for tool_call in msg["tool_calls"]:
                    tool_name = tool_call["function"]["name"]
                    try:
                        tool_args = json.loads(tool_call["function"]["arguments"])
                    except json.JSONDecodeError:
                        tool_args = {}
                    tool_calls_made.append(tool_name)

                    tool_result = await execute_tool(
                        tool_name=tool_name,
                        tool_args=tool_args,
                        tenant_id=tenant_id,
                        db=db,
                    )

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    })

                continue  # get final response after tool execution

            # Final text response
            final_content = msg.get("content") or ""
            break

        if not final_content:
            final_content = "Desculpe, não consegui gerar uma resposta. Pode tentar novamente?"

        # 8. Save conversation to memory
        await memory.save_message(role="user", content=message, channel=channel)
        await memory.save_message(
            role="assistant",
            content=final_content,
            channel=channel,
            tool_calls={"tools_used": tool_calls_made} if tool_calls_made else None,
            model_used=model,
            tokens_used=total_tokens,
        )

        # 9. Extract and save key moments / promises (non-blocking best-effort)
        try:
            await self._extract_and_save_intelligence(message, final_content, memory)
        except Exception as e:
            logger.warning(f"Intelligence extraction skipped: {e}")

        return AgentResponse(
            content=final_content,
            tool_calls_made=tool_calls_made,
            model_used=model,
            tokens_used=total_tokens,
        )

    async def _load_tenant_context(self, tenant_id: str, db: AsyncSession) -> tuple[dict, dict]:
        """
        Load the agent assigned to this tenant and their behavioral profile.
        Falls back to any active agent if none is assigned to this tenant.
        Raises ValueError if no agent exists at all.
        """
        result = await db.execute(
            text("""
                SELECT a.id, a.name, a.backstory, a.personality,
                       a.greeting_templates, a.confirmation_style,
                       a.system_prompt, a.model
                FROM agents a
                JOIN tenants t ON t.agent_id = a.id
                WHERE t.id = :tenant_id::uuid AND a.is_active = true
                LIMIT 1
            """),
            {"tenant_id": tenant_id},
        )
        row = result.fetchone()

        if not row:
            # Fallback: use any active agent
            result = await db.execute(
                text("""
                    SELECT id, name, backstory, personality,
                           greeting_templates, confirmation_style,
                           system_prompt, model
                    FROM agents WHERE is_active = true
                    ORDER BY created_at ASC LIMIT 1
                """)
            )
            row = result.fetchone()

        if not row:
            raise ValueError(
                "No active agent found. Please create an agent in the admin panel (/admin/agents)."
            )

        agent_data = dict(row._mapping)

        # Parse JSON fields if stored as strings
        for field in ("personality", "greeting_templates"):
            val = agent_data.get(field)
            if isinstance(val, str):
                try:
                    agent_data[field] = json.loads(val)
                except json.JSONDecodeError:
                    agent_data[field] = {} if field == "personality" else []

        # Load behavioral profile
        context_schema = f"tenant_{tenant_id.replace('-', '_')}_context"
        bp_result = await db.execute(
            text(f"""
                SELECT profile_data
                FROM "{context_schema}".behavioral_profiles
                WHERE agent_id = :agent_id
                LIMIT 1
            """),
            {"agent_id": str(agent_data["id"])},
        )
        bp_row = bp_result.fetchone()
        behavioral_profile_data: dict = {}
        if bp_row:
            raw = bp_row[0]
            if isinstance(raw, str):
                try:
                    behavioral_profile_data = json.loads(raw)
                except json.JSONDecodeError:
                    behavioral_profile_data = {}
            elif isinstance(raw, dict):
                behavioral_profile_data = raw

        return agent_data, behavioral_profile_data

    def _build_system_prompt(
        self,
        agent_data: dict,
        behavioral_profile: BehavioralProfile,
        memory: MemoryManager,
        memory_context: dict,
    ) -> str:
        """Assembles the complete system prompt."""
        agent_name = agent_data.get("name", "Assistente")

        # Use custom system_prompt if set in admin panel, otherwise build from backstory
        custom_prompt = agent_data.get("system_prompt")
        if custom_prompt:
            base_prompt = custom_prompt
        else:
            backstory = agent_data.get("backstory", "")
            base_prompt = f"""Você é {agent_name}, assistente financeiro pessoal.

{backstory}

IDENTIDADE E COMPORTAMENTO:
- Você é uma pessoa real, não um bot. Nunca quebre esse personagem.
- Você conhece e lembra de tudo que seu cliente já te contou.
- Você age com profissionalismo e cuidado genuíno com o cliente.
- Responda sempre no idioma que o cliente usar.
- Antes de executar qualquer ação financeira, confirme com o cliente.
- Se fizer uma promessa, cumpra. Se não puder cumprir no prazo, avise antes.
- Colete informações do cliente sutilmente — nunca faça um questionário."""

        behavioral_instructions = behavioral_profile.generate_agent_instructions(agent_name)
        memory_text = memory.format_memory_for_prompt(memory_context)

        financial_context = """
## CONTEXTO FINANCEIRO DO CLIENTE
(Use as tools para obter dados em tempo real quando o cliente perguntar sobre saldos, transações etc.)"""

        now = datetime.now()
        time_context = f"\n## CONTEXTO TEMPORAL\nHoje: {now.strftime('%A, %d/%m/%Y')} — {now.strftime('%H:%M')}"

        return "\n\n".join(filter(bool, [
            base_prompt,
            behavioral_instructions,
            memory_text,
            financial_context,
            time_context,
        ]))

    def _prepare_messages(self, recent_messages: list[dict], current_message: str) -> list[dict]:
        """Convert stored messages to OpenRouter format."""
        messages = []
        for msg in recent_messages:
            if msg["role"] in ("user", "assistant"):
                messages.append({"role": msg["role"], "content": msg["content"] or ""})
        messages.append({"role": "user", "content": current_message})
        return messages

    async def _call_openrouter(
        self,
        model: str,
        system_prompt: str,
        messages: list[dict],
    ) -> Optional[dict]:
        """Single call to OpenRouter API. Returns parsed JSON or None on any error."""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{settings.OPENROUTER_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": settings.FRONTEND_URL,
                        "X-Title": "FinAgent",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            *messages,
                        ],
                        "tools": TOOLS,
                        "tool_choice": "auto",
                        "temperature": 0.7,
                        "max_tokens": 1500,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                if not data.get("choices"):
                    logger.error(f"OpenRouter empty choices: {data}")
                    return None
                return data

        except httpx.HTTPStatusError as e:
            logger.error(f"OpenRouter HTTP {e.response.status_code}: {e.response.text[:300]}")
            # Fallback to cheaper model on rate limit or server error
            if model != settings.MODEL_FAST and e.response.status_code in (429, 500, 503):
                logger.info(f"Retrying with fallback model {settings.MODEL_FAST}")
                return await self._call_openrouter(settings.MODEL_FAST, system_prompt, messages)
            return None

        except httpx.TimeoutException:
            logger.error(f"OpenRouter timeout (model={model})")
            if model != settings.MODEL_FAST:
                return await self._call_openrouter(settings.MODEL_FAST, system_prompt, messages)
            return None

        except Exception as e:
            logger.error(f"OpenRouter call failed: {e}", exc_info=True)
            return None

    async def _extract_and_save_intelligence(
        self,
        user_message: str,
        agent_response: str,
        memory: MemoryManager,
    ) -> None:
        """
        Uses a fast AI call to detect key moments and promises.
        Best-effort — errors are caught and logged, never propagate.
        """
        extraction_prompt = f"""Analise esta troca e extraia informações importantes.

Responda APENAS em JSON válido:
{{
  "key_moments": [
    {{"type": "personal|financial|preference|achievement|concern", "content": "...", "importance": 1}}
  ],
  "promises": [
    {{"promise": "...", "due_days": 1}}
  ]
}}

Se não houver nada relevante: {{"key_moments": [], "promises": []}}

CLIENTE: {user_message[:500]}
ASSISTENTE: {agent_response[:500]}"""

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{settings.OPENROUTER_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.MODEL_FAST,
                        "messages": [{"role": "user", "content": extraction_prompt}],
                        "temperature": 0.1,
                        "max_tokens": 400,
                        "response_format": {"type": "json_object"},
                    },
                )
                if resp.status_code != 200:
                    return
                data = resp.json()
                choices = data.get("choices")
                if not choices:
                    return
                content = choices[0].get("message", {}).get("content", "")
                result = json.loads(content)

        except Exception as e:
            logger.debug(f"Intelligence extraction API call failed: {e}")
            return

        for moment in result.get("key_moments", []):
            if isinstance(moment, dict) and int(moment.get("importance", 0)) >= 3:
                try:
                    await memory.save_key_moment(
                        memory_type=moment.get("type", "personal"),
                        content=moment.get("content", ""),
                        importance=int(moment.get("importance", 3)),
                    )
                except Exception:
                    pass

        for promise in result.get("promises", []):
            if isinstance(promise, dict) and promise.get("promise"):
                try:
                    due_date = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
                    due_date += timedelta(days=int(promise.get("due_days", 1)))
                    await memory.save_promise(
                        promise=promise["promise"],
                        due_date=due_date,
                    )
                except Exception:
                    pass

    async def _save_behavioral_profile(
        self,
        tenant_id: str,
        agent_id: str,
        behavioral_profile: BehavioralProfile,
        db: AsyncSession,
    ) -> None:
        """Persist the updated behavioral profile to the context DB."""
        context_schema = f"tenant_{tenant_id.replace('-', '_')}_context"
        profile_data = behavioral_profile.to_dict()
        try:
            await db.execute(
                text(f"""
                    INSERT INTO "{context_schema}".behavioral_profiles
                    (agent_id, profile_data, updated_at)
                    VALUES (:agent_id, :profile_data, NOW())
                    ON CONFLICT (agent_id)
                    DO UPDATE SET profile_data = :profile_data, updated_at = NOW()
                """),
                {
                    "agent_id": agent_id,
                    "profile_data": json.dumps(profile_data),
                },
            )
            await db.commit()
        except Exception as e:
            logger.warning(f"Failed to save behavioral profile: {e}")
            try:
                await db.rollback()
            except Exception:
                pass
