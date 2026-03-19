from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text, event
from app.config import settings
from typing import AsyncGenerator
import logging

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=40,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tenant_schemas(tenant_id: str) -> None:
    """
    Creates two isolated schemas for each tenant:
    - tenant_{id}_financial: transactions, accounts, categories, reports, alerts
    - tenant_{id}_context: conversation history, behavioral profile, agent memory
    """
    financial_schema = f"tenant_{tenant_id}_financial"
    context_schema = f"tenant_{tenant_id}_context"

    async with engine.begin() as conn:
        # Create schemas
        await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{financial_schema}"'))
        await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{context_schema}"'))

        # Enable pgvector on both
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))

        logger.info(f"Created schemas for tenant {tenant_id}")


async def drop_tenant_schemas(tenant_id: str) -> None:
    """Removes all data for a tenant (use with extreme caution)"""
    financial_schema = f"tenant_{tenant_id}_financial"
    context_schema = f"tenant_{tenant_id}_context"

    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{financial_schema}" CASCADE'))
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{context_schema}" CASCADE'))
        logger.warning(f"DROPPED all schemas for tenant {tenant_id}")


async def init_db() -> None:
    """Initialize database - create extensions and core tables"""
    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
        await Base.metadata.create_all(conn)
    logger.info("Database initialized")
