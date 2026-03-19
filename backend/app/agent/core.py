"""
Agent Core — The Brain

Orchestrates every response:
1. Load agent identity + behavioral instructions
2. Load client memory (short + medium + semantic)
3. Select the best model for this task
4. Run the OpenRouter tool-calling loop
5. Extract key moments and promises to save
6. Update behavioral profile
"""

import json
import logging
from datetime import datetime
from typing import Optional, AsyncGenerator

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
    The core agent class. One instance per conversation turn.
    """

    def __init__(
        self,
        tenant_id: str,
        agent_id: str,
        agent_data: dict,           # name, backstory, personality, etc.
        behavioral_profile: dict,   # client's current behavioral profile
        db: AsyncSession,
    ):
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.agent_data = agent_data
        self.behavioral_profile = BehavioralProfile(behavioral_profile)
        self.db = db
        self.memory = MemoryManager(tenant_id, agent_id, db)
        self.financial_schema = f"tenant_{tenant_id.replace('-', '_')}_financial"

    async def respond(
        self,
        user_message: str,
        channel: str = "whatsapp",
        sent_at: Optional[datetime] = None,
    ) -> AgentResponse:
        """
        Main entry point. Takes a user message, returns an intelligent response.
        """

        # 1. Analyze message behavior signals
        signals = analyzer.analyze(user_message, sent_at)
        self.behavioral_profile.update(signals)

        # Save updated profile back to DB
        await self._save_behavioral_profile()

        # 2. Load memory context
        memory_context = await self.memory.build_context_for_prompt(user_message)
        recent_messages = memory_context.pop("recent_messages")

        # 3. Build system prompt
        system_prompt = self._build_system_prompt(memory_context)

        # 4. Prepare message history for API
        messages = self._prepare_messages(recent_messages, user_message)

        # 5. Select model based on task complexity
        model = model_selector.select(user_message, recent_messages)

        # 6. Run tool-calling loop
        tool_calls_made = []
        final_content = ""
        total_tokens = 0

        for iteration in range(5):  # max 5 tool calls per response
            response_data = await self._call_openrouter(
                model=model,
                system_prompt=system_prompt,
                messages=messages,
            )

            if not response_data:
                final_content = "Desculpe, tive um problema técnico. Pode repetir?"
                break

            choice = response_data["choices"][0]
            total_tokens += response_data.get("usage", {}).get("total_tokens", 0)
            finish_reason = choice.get("finish_reason")
            message = choice.get("message", {})

            # If the model wants to call a tool
            if finish_reason == "tool_calls" and message.get("tool_calls"):
                messages.append(message)  # add assistant's tool call to history

                for tool_call in message["tool_calls"]:
                    tool_name = tool_call["function"]["name"]
                    tool_args = json.loads(tool_call["function"]["arguments"])
                    tool_calls_made.append(tool_name)

                    # Execute the tool
                    tool_result = await execute_tool(
                        tool_name=tool_name,
                        tool_args=tool_args,
                        tenant_id=self.tenant_id,
                        db=self.db,
                    )

                    # Add tool result to message history
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(tool_result),
                    })

                continue  # loop back to get final response

            # Model has a final text response
            final_content = message.get("content", "")
            break

        # 7. Save conversation to memory
        await self.memory.save_message(
            role="user",
            content=user_message,
            channel=channel,
        )
        await self.memory.save_message(
            role="assistant",
            content=final_content,
            channel=channel,
            tool_calls={"tools_used": tool_calls_made} if tool_calls_made else None,
            model_used=model,
            tokens_used=total_tokens,
        )

        # 8. Extract and save key moments / promises (async background task)
        await self._extract_and_save_intelligence(user_message, final_content)

        return AgentResponse(
            content=final_content,
            tool_calls_made=tool_calls_made,
            model_used=model,
            tokens_used=total_tokens,
        )

    def _build_system_prompt(self, memory_context: dict) -> str:
        """Assembles the complete system prompt with identity + behavioral instructions + memory."""
        agent_name = self.agent_data.get("name", "Assistente")

        # Base identity
        backstory = self.agent_data.get("backstory", "")
        base_prompt = f"""Você é {agent_name}, assistente financeiro pessoal.

{backstory}

IDENTIDADE E COMPORTAMENTO:
- Você é uma pessoa real, não um bot. Nunca quebre esse personagem.
- Você conhece e lembra de tudo que seu cliente já te contou.
- Você age com profissionalismo e cuidado genuíno com o cliente.
- Responda sempre no idioma que o cliente usar.
- Antes de executar qualquer ação financeira, confirme com o cliente.
- Se fizer uma promessa, cumpra. Se não puder cumprir no prazo, avise antes.
- Colete informações do cliente sutilmente — nunca faça um questionário.
  Aprenda sobre ele/ela através da conversa natural."""

        # Behavioral instructions (dynamic per client)
        behavioral_instructions = self.behavioral_profile.generate_agent_instructions(agent_name)

        # Memory context
        memory_text = self.memory.format_memory_for_prompt(memory_context)

        # Financial context
        financial_context = f"""
## CONTEXTO FINANCEIRO DO CLIENTE
(Dados sempre atualizados — use para respostas precisas)
Consulte as tools para obter dados em tempo real quando necessário."""

        # Current date/time context
        now = datetime.now()
        time_context = f"\n## CONTEXTO TEMPORAL\nHoje: {now.strftime('%A, %d/%m/%Y')} — {now.strftime('%H:%M')}"

        return "\n\n".join(filter(bool, [
            base_prompt,
            behavioral_instructions,
            memory_text,
            financial_context,
            time_context,
        ]))

    def _prepare_messages(
        self,
        recent_messages: list[dict],
        current_message: str,
    ) -> list[dict]:
        """Convert stored messages to OpenRouter format."""
        messages = []

        for msg in recent_messages:
            if msg["role"] in ("user", "assistant"):
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"] or "",
                })

        messages.append({"role": "user", "content": current_message})
        return messages

    async def _call_openrouter(
        self,
        model: str,
        system_prompt: str,
        messages: list[dict],
    ) -> Optional[dict]:
        """Makes a single call to OpenRouter API."""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
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
                    }
                )
                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"OpenRouter HTTP error: {e.response.status_code} — {e.response.text}")
            # Fallback to simpler model
            if model != settings.MODEL_FAST:
                logger.info(f"Falling back to {settings.MODEL_FAST}")
                return await self._call_openrouter(settings.MODEL_FAST, system_prompt, messages)
            return None

        except Exception as e:
            logger.error(f"OpenRouter call failed: {e}")
            return None

    async def _extract_and_save_intelligence(
        self, user_message: str, agent_response: str
    ) -> None:
        """
        Uses a fast AI call to detect key moments and promises in the conversation.
        Runs after the main response is sent (non-blocking).
        """
        extraction_prompt = f"""Analise esta troca de mensagens e extraia:
1. KEY_MOMENTS: fatos importantes que o assistente deve lembrar a longo prazo
   (ex: cliente mencionou algo pessoal, financeiro importante, preferência)
2. PROMISES: promessas que o assistente fez (ex: "vou verificar", "te envio até sexta")

Responda APENAS em JSON:
{{
  "key_moments": [
    {{"type": "personal|financial|preference|achievement|concern", "content": "...", "importance": 1-5}}
  ],
  "promises": [
    {{"promise": "...", "due_days": 1}}
  ]
}}

Se não houver nada relevante, retorne {{"key_moments": [], "promises": []}}

CLIENTE DISSE: {user_message}
ASSISTENTE RESPONDEU: {agent_response}"""

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    f"{settings.OPENROUTER_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.MODEL_FAST,
                        "messages": [{"role": "user", "content": extraction_prompt}],
                        "temperature": 0.1,
                        "max_tokens": 500,
                        "response_format": {"type": "json_object"},
                    }
                )
                data = response.json()
                result = json.loads(data["choices"][0]["message"]["content"])

                for moment in result.get("key_moments", []):
                    if moment.get("importance", 0) >= 3:
                        await self.memory.save_key_moment(
                            memory_type=moment["type"],
                            content=moment["content"],
                            importance=moment["importance"],
                        )

                for promise in result.get("promises", []):
                    due_date = datetime.now().replace(
                        hour=9, minute=0, second=0, microsecond=0
                    )
                    from datetime import timedelta
                    due_date += timedelta(days=promise.get("due_days", 1))
                    await self.memory.save_promise(
                        promise=promise["promise"],
                        due_date=due_date,
                    )

        except Exception as e:
            logger.warning(f"Intelligence extraction failed (non-critical): {e}")

    async def _save_behavioral_profile(self) -> None:
        """Persist the updated behavioral profile to the context DB."""
        context_schema = f"tenant_{self.tenant_id.replace('-', '_')}_context"
        profile_data = self.behavioral_profile.to_dict()
        await self.db.execute(
            text(f"""
                INSERT INTO "{context_schema}".behavioral_profiles
                (agent_id, profile_data, updated_at)
                VALUES (:agent_id, :profile_data, NOW())
                ON CONFLICT (agent_id)
                DO UPDATE SET profile_data = :profile_data, updated_at = NOW()
            """),
            {"agent_id": self.agent_id, "profile_data": json.dumps(profile_data)}
        )
        await self.db.commit()
