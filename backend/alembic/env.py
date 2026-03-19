"""
Alembic environment configuration.
Configured for async SQLAlchemy (asyncpg driver).
"""
import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Add backend directory to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import our SQLAlchemy models and Base so Alembic can detect schema changes
from app.database import Base  # noqa: E402
from app.models import *  # noqa: E402, F401, F403 — import all models

# Alembic Config object (provides access to .ini file values)
config = context.config

# Configure Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The metadata Alembic will compare against for autogenerate
target_metadata = Base.metadata


def get_url() -> str:
    """
    Get the database URL from app settings.
    Converts asyncpg URL to sync psycopg2 for Alembic compatibility.
    """
    # Try to import from app settings first
    try:
        from app.config import settings
        url = settings.DATABASE_URL
    except Exception:
        url = os.environ.get("DATABASE_URL", "postgresql://finagent:finagent@localhost:5432/finagent")

    # Alembic needs the asyncpg URL for async migrations
    # Keep asyncpg for online mode, convert to sync for offline
    return url


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.
    Generates SQL without connecting to the database.
    """
    url = get_url().replace("postgresql+asyncpg://", "postgresql://")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,        # detect column type changes
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations using async SQLAlchemy engine."""
    url = get_url()
    # Ensure we use asyncpg driver
    if "postgresql://" in url and "asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://")

    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connected to database)."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
