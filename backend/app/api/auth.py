"""
Authentication endpoints.

POST /api/v1/auth/register  — create new client account
POST /api/v1/auth/login     — login and get JWT tokens
POST /api/v1/auth/refresh   — get new access token using refresh token
POST /api/v1/auth/logout    — invalidate session (client-side token drop)
"""
import uuid
import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db, create_tenant_schemas
from app.models.tenant import Tenant
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Schemas ──────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    business_name: str | None = None
    whatsapp_number: str | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    tenant_id: str
    name: str


class RefreshRequest(BaseModel):
    refresh_token: str


# ─── Endpoints ────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Register a new client.
    - Creates the tenant record with hashed password
    - Creates two isolated PostgreSQL schemas for this client
    - Returns JWT tokens ready to use
    """
    # Check if email already exists
    existing = await db.execute(select(Tenant).where(Tenant.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Check if WhatsApp number is already taken
    if body.whatsapp_number:
        existing_wa = await db.execute(
            select(Tenant).where(Tenant.whatsapp_number == body.whatsapp_number)
        )
        if existing_wa.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="WhatsApp number already registered",
            )

    # Create tenant
    tenant = Tenant(
        name=body.name,
        email=body.email,
        hashed_password=get_password_hash(body.password),
        business_name=body.business_name,
        whatsapp_number=body.whatsapp_number,
    )
    db.add(tenant)
    await db.flush()  # get the UUID before commit

    # Create isolated schemas for this tenant
    tenant_id_clean = str(tenant.id).replace("-", "_")
    await create_tenant_schemas(tenant_id_clean)

    await db.commit()
    await db.refresh(tenant)

    logger.info(f"New tenant registered: {tenant.email} ({tenant.id})")

    # Issue tokens
    token_data = {"sub": str(tenant.id)}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
        tenant_id=str(tenant.id),
        name=tenant.name,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Login with email + password.
    Returns JWT access + refresh tokens.
    """
    result = await db.execute(select(Tenant).where(Tenant.email == body.email))
    tenant = result.scalar_one_or_none()

    if not tenant or not tenant.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(body.password, tenant.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    logger.info(f"Tenant logged in: {tenant.email}")

    token_data = {"sub": str(tenant.id)}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
        tenant_id=str(tenant.id),
        name=tenant.name,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """
    Get a new access token using a valid refresh token.
    Use this when the access token expires (after 60 minutes).
    """
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
    )

    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise exc

    tenant_id_str = payload.get("sub", "")
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

    token_data = {"sub": str(tenant.id)}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
        tenant_id=str(tenant.id),
        name=tenant.name,
    )


@router.post("/logout", status_code=204)
async def logout():
    """
    Logout — client should discard tokens on their side.
    (Stateless JWT: no server-side invalidation needed for MVP)
    """
    return None
