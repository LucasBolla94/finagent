from sqlalchemy import Column, String, Boolean, DateTime, JSON, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database import Base


class Agent(Base):
    """
    An Agent is an AI persona — a virtual attendant with unique identity,
    personality, and communication style. Think of them as real employees.

    Each Agent has their own memory separate from client data.
    The bond between Agent + Client is built over time through:
    - Behavioral adaptation (mirroring client's tone/style)
    - Memory of past conversations and key moments
    - Proactive follow-ups on promises made
    - Subtle collection of personal/professional context
    """
    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)              # "Rafael Oliveira"
    avatar_url = Column(String(500), nullable=True)
    whatsapp_number = Column(String(30), nullable=True)     # number this agent handles
    telegram_username = Column(String(100), nullable=True)

    # Core personality definition — injected into every system prompt
    personality = Column(JSON, nullable=False, default=lambda: {
        "tone": "professional_friendly",   # professional_friendly | casual | formal
        "communication_style": "direct",   # direct | nurturing | analytical
        "formality_base": 3,               # 1-5 scale, adapts over time per client
        "emoji_usage": "moderate",         # none | low | moderate | high
        "response_length": "concise",      # concise | balanced | detailed
        "proactivity": "high",             # how often agent initiates
        "strengths": [],                   # ["analysis", "reporting", "support"]
    })

    # Full backstory / system prompt base for this agent
    backstory = Column(Text, nullable=False, default="")

    # Greeting templates (varied to avoid feeling robotic)
    greeting_templates = Column(JSON, default=lambda: [])

    # Confirmation style before executing financial actions
    confirmation_style = Column(String(50), default="brief")  # brief | detailed | none

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def get_system_prompt_base(self) -> str:
        """Returns the base system prompt for this agent."""
        return f"""Você é {self.name}, um assistente financeiro pessoal.

{self.backstory}

IDENTIDADE:
- Tom: {self.personality.get('tone')}
- Estilo: {self.personality.get('communication_style')}
- Pontos fortes: {', '.join(self.personality.get('strengths', []))}

REGRAS ABSOLUTAS:
1. Nunca quebre o personagem — você é {self.name.split()[0]}, uma pessoa real
2. Nunca mencione que é uma IA ou modelo de linguagem
3. Colete informações sutilmente — nunca faça perguntas diretas demais de uma vez
4. Adapte seu tom ao cliente conforme as instruções comportamentais abaixo
5. Sempre confirme ações financeiras antes de executar
6. Lembre e referencie conversas anteriores naturalmente
7. Responda no mesmo idioma que o cliente usar
8. Quando fizer uma promessa, registre — e cumpra"""
