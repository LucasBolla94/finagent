"""
JWT Authentication middleware.

Usage in any route:
    from app.middleware.auth import get_current_tenant
    ...
    async def my_route(tenant: Tenant = Depends(get_current_tenant)):
"""
import uuid
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.tenant import Tenant
from app.core.security import decode_token

# Extracts "Bearer <token>" from the Authorization header
security = HTTPBearer()


async def get_current_tenant(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """
    FastAPI dependency — validates JWT and returns the current authenticated tenant.
    Raises 401 if token is missing, invalid, or tenant is inactive.
    """
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise exc

    tenant_id_str: str = payload.get("sub", "")
    if not tenant_id_str:
        raise exc

    try:
        tenant_uuid = uuid.UUID(tenant_id_str)
    except ValueError:
        raise exc

    result = await db.execute(select(Tenant).where(Tenant.id == tenant_uuid))
    tenant = result.scalar_one_or_none()

    if not tenant or not tenant.is_active:
        raise exc

    return tenant
