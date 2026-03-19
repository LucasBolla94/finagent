"""
Client profile API.

GET  /api/v1/profile   — get current client's profile
PUT  /api/v1/profile   — update profile (name, settings, WhatsApp number, etc.)
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.models.tenant import Tenant
from app.middleware.auth import get_current_tenant
from app.core.security import verify_password, get_password_hash

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Schemas ──────────────────────────────────────────────────────────────

class ProfileResponse(BaseModel):
    id: str
    name: str
    email: str
    business_name: Optional[str]
    plan: str
    whatsapp_number: Optional[str]
    telegram_chat_id: Optional[str]
    settings: dict
    is_active: bool
    created_at: str


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    business_name: Optional[str] = None
    whatsapp_number: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    settings: Optional[dict] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# ─── Endpoints ────────────────────────────────────────────────────────────

@router.get("")
async def get_profile(tenant: Tenant = Depends(get_current_tenant)):
    """Get the current client's profile information."""
    return {
        "id": str(tenant.id),
        "name": tenant.name,
        "email": tenant.email,
        "business_name": tenant.business_name,
        "plan": tenant.plan.value if hasattr(tenant.plan, 'value') else tenant.plan,
        "whatsapp_number": tenant.whatsapp_number,
        "telegram_chat_id": tenant.telegram_chat_id,
        "settings": tenant.settings or {},
        "is_active": tenant.is_active,
        "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
    }


@router.put("")
async def update_profile(
    body: ProfileUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Update profile information.
    You can update name, business name, WhatsApp/Telegram numbers, and settings.
    """
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Check if WhatsApp number is already taken by another tenant
    if "whatsapp_number" in updates:
        from sqlalchemy import select
        from app.models.tenant import Tenant as TenantModel
        existing = await db.execute(
            select(TenantModel).where(
                TenantModel.whatsapp_number == updates["whatsapp_number"],
                TenantModel.id != tenant.id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail="WhatsApp number already registered to another account",
            )

    import json
    set_clauses = []
    params = {"tenant_id": str(tenant.id)}

    for field, value in updates.items():
        if field == "settings":
            set_clauses.append(f"{field} = :{field}::jsonb")
            params[field] = json.dumps(value)
        else:
            set_clauses.append(f"{field} = :{field}")
            params[field] = value

    set_clauses.append("updated_at = NOW()")

    sql = text(f"""
        UPDATE tenants
        SET {', '.join(set_clauses)}
        WHERE id = :tenant_id::uuid
        RETURNING *
    """)

    try:
        result = await db.execute(sql, params)
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Profile not found")
        await db.commit()
        d = dict(row._mapping)
        return {
            "id": str(d["id"]),
            "name": d["name"],
            "email": d["email"],
            "business_name": d.get("business_name"),
            "whatsapp_number": d.get("whatsapp_number"),
            "telegram_chat_id": d.get("telegram_chat_id"),
            "settings": d.get("settings") or {},
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Update profile error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update profile")


@router.post("/change-password", status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Change the account password."""
    if not tenant.hashed_password:
        raise HTTPException(status_code=400, detail="Account has no password set")

    if not verify_password(body.current_password, tenant.hashed_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")

    sql = text("""
        UPDATE tenants
        SET hashed_password = :hashed_password, updated_at = NOW()
        WHERE id = :id::uuid
    """)

    try:
        await db.execute(sql, {
            "hashed_password": get_password_hash(body.new_password),
            "id": str(tenant.id),
        })
        await db.commit()
        return None
    except Exception as e:
        await db.rollback()
        logger.error(f"Change password error: {e}")
        raise HTTPException(status_code=500, detail="Failed to change password")
