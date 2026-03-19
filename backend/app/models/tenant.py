from sqlalchemy import Column, String, Boolean, DateTime, JSON, Integer, Enum as SAEnum, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum
from app.database import Base


class TenantPlan(str, enum.Enum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"


class Tenant(Base):
    """
    A tenant is a client of the system (a person or business).
    Each tenant gets two isolated PostgreSQL schemas:
      - tenant_{id}_financial
      - tenant_{id}_context
    """
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    business_name = Column(String(255), nullable=True)
    plan = Column(SAEnum(TenantPlan), default=TenantPlan.FREE)

    # Authentication
    hashed_password = Column(String(255), nullable=True)

    # Channel identifiers
    whatsapp_number = Column(String(30), unique=True, nullable=True)
    telegram_chat_id = Column(String(50), unique=True, nullable=True)

    # Assigned agent
    agent_id = Column(UUID(as_uuid=True), nullable=True)  # FK to agents table

    # Settings (language, currency, timezone, preferences)
    settings = Column(JSON, default=lambda: {
        "language": "auto",       # auto-detected from first message
        "currency": "BRL",
        "timezone": "America/Sao_Paulo",
        "notification_hours": [8, 18],  # when to send proactive alerts
    })

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def financial_schema(self) -> str:
        return f"tenant_{str(self.id).replace('-', '_')}_financial"

    def context_schema(self) -> str:
        return f"tenant_{str(self.id).replace('-', '_')}_context"
