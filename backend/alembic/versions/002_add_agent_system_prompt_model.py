"""Add system_prompt and model columns to agents table

Revision ID: 002
Revises: 001
Create Date: 2026-03-19

BUG-002 FIX:
  - revision must be short (<=32 chars) — alembic_version.version_num is VARCHAR(32)
  - down_revision must match the actual revision value of migration 001 (which is "001",
    not "001_add_auth_fields" — that was the filename, not the revision ID)
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add system_prompt column — allows admin to set a full custom prompt
    op.add_column(
        "agents",
        sa.Column("system_prompt", sa.Text(), nullable=True, comment="Custom system prompt (overrides backstory if set)"),
    )
    # Add model column — allows per-agent model override
    op.add_column(
        "agents",
        sa.Column(
            "model",
            sa.String(100),
            nullable=True,
            server_default="anthropic/claude-haiku-4",
            comment="Default AI model for this agent",
        ),
    )
    # Add description column as alias/shorthand for backstory
    op.add_column(
        "agents",
        sa.Column("description", sa.Text(), nullable=True, comment="Short description shown in admin panel"),
    )


def downgrade() -> None:
    op.drop_column("agents", "system_prompt")
    op.drop_column("agents", "model")
    op.drop_column("agents", "description")
