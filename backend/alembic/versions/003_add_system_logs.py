"""Add system_logs table for centralized error and event tracking

Revision ID: 003
Revises: 002
Create Date: 2026-03-19

Creates the system_logs table used by /api/admin/logs endpoint.
Logs all errors, warnings, and events from backend services
(whatsapp, auth, celery, agent, etc.) with full JSON details.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("level", sa.String(10), nullable=False),       # ERROR WARNING INFO DEBUG
        sa.Column("service", sa.String(50), nullable=False),     # whatsapp auth celery agent
        sa.Column("event", sa.String(100), nullable=True),       # qr_fetch instance_create etc
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("details", JSONB, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),     # how long the op took
        sa.Column("user_id", sa.String(36), nullable=True),
    )
    # Indexes for the most common filter queries
    op.create_index("ix_system_logs_created_at", "system_logs", ["created_at"])
    op.create_index("ix_system_logs_level",      "system_logs", ["level"])
    op.create_index("ix_system_logs_service",    "system_logs", ["service"])


def downgrade() -> None:
    op.drop_index("ix_system_logs_service",    "system_logs")
    op.drop_index("ix_system_logs_level",      "system_logs")
    op.drop_index("ix_system_logs_created_at", "system_logs")
    op.drop_table("system_logs")
