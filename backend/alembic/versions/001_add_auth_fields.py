"""Add hashed_password to tenants table.

This migration adds authentication support to the tenants table.
Uses IF NOT EXISTS so it's safe to run on both fresh installs
(where init_postgres.sql already created the base schema) and
existing deployments.

Revision ID: 001
Revises: (initial)
Create Date: 2026-03-19
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add hashed_password column to tenants
    # Uses raw SQL with IF NOT EXISTS — safe to run on fresh or existing deployments
    op.execute("""
        ALTER TABLE tenants
        ADD COLUMN IF NOT EXISTS hashed_password VARCHAR(255)
    """)

    # Ensure pg_trgm and unaccent extensions exist (needed for duplicate detection)
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "unaccent"')

    # Add index on email for faster login lookups (may already exist)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tenants_email ON tenants(email)
    """)

    # Add index on whatsapp_number for webhook lookups
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tenants_whatsapp ON tenants(whatsapp_number)
        WHERE whatsapp_number IS NOT NULL
    """)

    # Add index on telegram_chat_id for webhook lookups
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tenants_telegram ON tenants(telegram_chat_id)
        WHERE telegram_chat_id IS NOT NULL
    """)

    # Add is_active index on agents
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_agents_active ON agents(is_active)
        WHERE is_active = true
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS hashed_password")
    op.execute("DROP INDEX IF EXISTS idx_tenants_email")
    op.execute("DROP INDEX IF EXISTS idx_tenants_whatsapp")
    op.execute("DROP INDEX IF EXISTS idx_tenants_telegram")
    op.execute("DROP INDEX IF EXISTS idx_agents_active")
