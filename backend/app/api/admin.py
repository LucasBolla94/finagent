"""
Admin API — for the owner (Lucas) only.
Protected by a separate ADMIN_SECRET_KEY in the .env.

All routes require the header:  X-Admin-Key: <ADMIN_SECRET_KEY>

Endpoints:
  GET  /api/admin/stats               — dashboard stats + whatsapp state
  GET  /api/admin/agents              — list all agents
  POST /api/admin/agents              — create new agent
  PUT  /api/admin/agents/{id}         — update agent
  DELETE /api/admin/agents/{id}       — deactivate agent
  POST /api/admin/agents/{id}/assign/{tenant_id}  — assign to tenant

  GET  /api/admin/whatsapp/status     — Evolution API instance status
  POST /api/admin/whatsapp/connect    — start WhatsApp connection / get QR
  GET  /api/admin/whatsapp/qrcode     — get QR code image for scanning
  DELETE /api/admin/whatsapp/disconnect — disconnect instance

  GET  /api/admin/tenants             — list all clients
  POST /api/admin/tenants             — create tenant manually (admin)
"""
import os
import json
import logging
import secrets
import uuid
from datetime import date
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Admin authentication ─────────────────────────────────────────────────────

ADMIN_SECRET = os.environ.get("ADMIN_SECRET_KEY", "")


async def verify_admin(x_admin_key: str = Header(..., alias="X-Admin-Key")):
    """Header-based admin auth using constant-time comparison to prevent timing attacks."""
    if not ADMIN_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Admin key not configured. Set ADMIN_SECRET_KEY in .env"
        )
    if not secrets.compare_digest(x_admin_key.encode(), ADMIN_SECRET.encode()):
        raise HTTPException(status_code=403, detail="Invalid admin key")
    return True


# ─── Schemas ──────────────────────────────────────────────────────────────────

class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    model: str = "anthropic/claude-haiku-4"
    backstory: Optional[str] = None
    personality: dict = {}
    greeting_templates: list = []
    confirmation_style: str = "brief"


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    backstory: Optional[str] = None
    personality: Optional[dict] = None
    greeting_templates: Optional[list] = None
    confirmation_style: Optional[str] = None
    is_active: Optional[bool] = None


class TenantCreate(BaseModel):
    name: str
    email: Optional[str] = None
    whatsapp_number: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    business_name: Optional[str] = None
    plan: str = "free"


# ─── Dashboard stats ──────────────────────────────────────────────────────────

@router.get("/stats")
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin),
):
    """Quick overview stats for the admin dashboard."""
    # Basic counts
    tenants_r = await db.execute(text("SELECT COUNT(*) FROM tenants WHERE is_active = true"))
    agents_r = await db.execute(text("SELECT COUNT(*) FROM agents WHERE is_active = true"))
    docs_r = await db.execute(text("SELECT COUNT(*) FROM imported_documents"))

    active_clients = (tenants_r.fetchone() or [0])[0]
    active_agents = (agents_r.fetchone() or [0])[0]
    imported_docs = (docs_r.fetchone() or [0])[0]

    # Messages sent today — count across all tenant context schemas
    messages_today = 0
    try:
        today_str = date.today().isoformat()
        tenants_result = await db.execute(
            text("SELECT id FROM tenants WHERE is_active = true")
        )
        tenant_ids = [str(r[0]).replace("-", "") for r in tenants_result.fetchall()]

        for tid in tenant_ids:
            schema = f"tenant_{tid}_context"
            try:
                result = await db.execute(
                    text(f"""
                        SELECT COUNT(*) FROM {schema}.conversation_history
                        WHERE role = 'assistant'
                          AND DATE(created_at) = :today
                    """),
                    {"today": today_str},
                )
                messages_today += (result.fetchone() or [0])[0]
            except Exception:
                pass  # schema might not exist yet for new tenants
    except Exception as e:
        logger.warning(f"Could not count messages_today: {e}")

    # WhatsApp status
    whatsapp_state = None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{settings.EVOLUTION_API_URL}/instance/connectionState/{settings.EVOLUTION_INSTANCE_NAME}",
                headers={"apikey": settings.EVOLUTION_API_KEY},
            )
            if resp.status_code == 200:
                data = resp.json()
                whatsapp_state = (
                    data.get("instance", {}).get("state")
                    or data.get("state")
                )
    except Exception:
        pass  # Evolution API might be down, not critical

    return {
        "active_clients": active_clients,
        "active_agents": active_agents,
        "imported_documents": imported_docs,
        "messages_today": messages_today,
        "whatsapp_state": whatsapp_state,
    }


# ─── Agent management ─────────────────────────────────────────────────────────

@router.get("/agents")
async def list_agents(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin),
):
    """List all agents with their assigned clients."""
    result = await db.execute(
        text("""
            SELECT
                a.id, a.name, a.description, a.system_prompt, a.model,
                a.is_active, a.created_at,
                t_agg.tenant_id AS tenant_id,
                t_agg.tenant_name AS tenant_name,
                COALESCE(t_agg.client_count, 0) AS client_count
            FROM agents a
            LEFT JOIN (
                SELECT
                    agent_id,
                    MAX(id::text) AS tenant_id,
                    MAX(name) AS tenant_name,
                    COUNT(*) AS client_count
                FROM tenants
                GROUP BY agent_id
            ) t_agg ON t_agg.agent_id = a.id
            ORDER BY a.is_active DESC, a.created_at ASC
        """)
    )
    agents = [dict(r._mapping) for r in result.fetchall()]
    return {"agents": agents}


@router.post("/agents", status_code=201)
async def create_agent(
    body: AgentCreate,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin),
):
    """Create a new agent persona."""
    agent_id = uuid.uuid4()
    await db.execute(
        text("""
            INSERT INTO agents
                (id, name, description, system_prompt, model, backstory,
                 personality, greeting_templates, confirmation_style, is_active)
            VALUES
                (:id, :name, :description, :system_prompt, :model, :backstory,
                 :personality::jsonb, :templates::jsonb, :confirmation_style, true)
        """),
        {
            "id": agent_id,
            "name": body.name,
            "description": body.description,
            "system_prompt": body.system_prompt,
            "model": body.model,
            "backstory": body.backstory or "",
            "personality": json.dumps(body.personality),
            "templates": json.dumps(body.greeting_templates),
            "confirmation_style": body.confirmation_style,
        },
    )
    await db.commit()
    logger.info(f"Admin: created agent '{body.name}' ({agent_id})")
    return {"id": str(agent_id), "name": body.name, "message": "Agent created successfully"}


@router.put("/agents/{agent_id}")
async def update_agent(
    agent_id: str,
    body: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin),
):
    """Update an agent (any field, including reactivating)."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clauses = []
    params: dict = {"id": agent_id}
    for field, value in updates.items():
        if field in ("personality", "greeting_templates"):
            set_clauses.append(f"{field} = :{field}::jsonb")
            params[field] = json.dumps(value)
        else:
            set_clauses.append(f"{field} = :{field}")
            params[field] = value

    result = await db.execute(
        text(f"UPDATE agents SET {', '.join(set_clauses)} WHERE id = :id::uuid RETURNING id, name, is_active"),
        params,
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.commit()
    return {"id": str(row[0]), "name": row[1], "is_active": row[2], "message": "Updated"}


@router.delete("/agents/{agent_id}")
async def deactivate_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin),
):
    """Deactivate (soft-delete) an agent."""
    result = await db.execute(
        text("UPDATE agents SET is_active = false WHERE id = :id::uuid RETURNING id"),
        {"id": agent_id},
    )
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.commit()
    return {"message": "Agent deactivated"}


@router.post("/agents/{agent_id}/assign/{tenant_id}")
async def assign_agent_to_tenant(
    agent_id: str,
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin),
):
    """Assign an agent to a tenant (client)."""
    # Validate both exist
    agent_r = await db.execute(
        text("SELECT id FROM agents WHERE id = :id::uuid AND is_active = true"),
        {"id": agent_id}
    )
    if not agent_r.fetchone():
        raise HTTPException(status_code=404, detail="Agent not found or inactive")

    result = await db.execute(
        text("UPDATE tenants SET agent_id = :agent_id::uuid WHERE id = :tenant_id::uuid RETURNING id"),
        {"agent_id": agent_id, "tenant_id": tenant_id},
    )
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Tenant not found")
    await db.commit()
    logger.info(f"Admin: assigned agent {agent_id[:8]} to tenant {tenant_id[:8]}")
    return {"message": "Agent assigned successfully"}


# ─── WhatsApp (Evolution API) management ──────────────────────────────────────

async def _evolution_request(method: str, path: str, body: dict = None) -> dict:
    """Make authenticated request to Evolution API."""
    url = f"{settings.EVOLUTION_API_URL}{path}"
    headers = {"apikey": settings.EVOLUTION_API_KEY, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        if method == "GET":
            resp = await client.get(url, headers=headers)
        elif method == "POST":
            resp = await client.post(url, headers=headers, json=body or {})
        elif method == "DELETE":
            resp = await client.delete(url, headers=headers)
        else:
            raise ValueError(f"Unknown method: {method}")

    if resp.status_code == 404:
        return {"error": "instance_not_found", "status": "not_connected"}
    try:
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"Evolution API {method} {path} → {resp.status_code}: {resp.text[:200]}")
        raise
    return resp.json()


@router.get("/whatsapp/status")
async def whatsapp_status(_: bool = Depends(verify_admin)):
    """Get Evolution API instance connection status."""
    try:
        return await _evolution_request(
            "GET",
            f"/instance/connectionState/{settings.EVOLUTION_INSTANCE_NAME}"
        )
    except Exception as e:
        return {"status": "error", "detail": str(e), "instance": {"state": "error"}}


@router.post("/whatsapp/connect")
async def whatsapp_connect(_: bool = Depends(verify_admin)):
    """
    Create/connect the WhatsApp instance.
    After this, call /qrcode to get the QR code to scan.
    """
    try:
        status = await _evolution_request(
            "GET",
            f"/instance/connectionState/{settings.EVOLUTION_INSTANCE_NAME}"
        )
        if status.get("instance", {}).get("state") == "open":
            return {"status": "already_connected", "message": "WhatsApp já está conectado!"}
    except Exception:
        pass

    try:
        backend_url = os.environ.get("BACKEND_PUBLIC_URL", "http://backend:8000")
        result = await _evolution_request("POST", "/instance/create", {
            "instanceName": settings.EVOLUTION_INSTANCE_NAME,
            "token": settings.EVOLUTION_API_KEY,
            "qrcode": True,
            "integration": "WHATSAPP-BAILEYS",
            "webhook": {
                "url": f"{backend_url}/api/v1/webhooks/whatsapp",
                "byEvents": True,
                "base64": False,
                "events": ["MESSAGES_UPSERT", "QRCODE_UPDATED", "CONNECTION_UPDATE"],
            },
        })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evolution API error: {str(e)}")


@router.get("/whatsapp/qrcode")
async def whatsapp_qrcode(_: bool = Depends(verify_admin)):
    """
    Get the QR code image to scan with WhatsApp.
    Returns base64 image or the QR string.
    """
    try:
        result = await _evolution_request(
            "GET",
            f"/instance/connect/{settings.EVOLUTION_INSTANCE_NAME}"
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not get QR code: {str(e)}")


@router.delete("/whatsapp/disconnect")
async def whatsapp_disconnect(_: bool = Depends(verify_admin)):
    """Disconnect and logout the WhatsApp instance."""
    try:
        result = await _evolution_request(
            "DELETE",
            f"/instance/logout/{settings.EVOLUTION_INSTANCE_NAME}"
        )
        return {"status": "disconnected", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Tenant (client) management ───────────────────────────────────────────────

@router.get("/tenants")
async def list_tenants(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin),
):
    """List all registered clients with basic stats."""
    result = await db.execute(
        text("""
            SELECT
                t.id, t.name, t.email, t.business_name,
                t.plan, t.whatsapp_number, t.telegram_chat_id,
                t.is_active, t.created_at,
                a.id AS agent_id,
                a.name AS agent_name
            FROM tenants t
            LEFT JOIN agents a ON a.id = t.agent_id
            ORDER BY t.created_at DESC
        """)
    )
    tenants = [dict(r._mapping) for r in result.fetchall()]
    return {"tenants": tenants, "total": len(tenants)}


@router.post("/tenants", status_code=201)
async def create_tenant(
    body: TenantCreate,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin),
):
    """
    Create a new tenant (client) manually from the admin panel.
    Also creates the per-tenant financial and context schemas.
    """
    # Check for duplicate whatsapp_number
    if body.whatsapp_number:
        dup = await db.execute(
            text("SELECT id FROM tenants WHERE whatsapp_number = :phone"),
            {"phone": body.whatsapp_number},
        )
        if dup.fetchone():
            raise HTTPException(
                status_code=409,
                detail=f"WhatsApp number {body.whatsapp_number} already registered"
            )

    # Check for duplicate email
    if body.email:
        dup_email = await db.execute(
            text("SELECT id FROM tenants WHERE email = :email"),
            {"email": body.email},
        )
        if dup_email.fetchone():
            raise HTTPException(
                status_code=409,
                detail=f"Email {body.email} already registered"
            )

    tenant_id = uuid.uuid4()
    # Generate a simple hashed password placeholder (admin-created users have no password)
    import hashlib
    placeholder_hash = hashlib.sha256(str(tenant_id).encode()).hexdigest()

    await db.execute(
        text("""
            INSERT INTO tenants
                (id, name, email, whatsapp_number, telegram_chat_id,
                 business_name, plan, is_active, password_hash)
            VALUES
                (:id, :name, :email, :whatsapp_number, :telegram_chat_id,
                 :business_name, :plan, true, :password_hash)
        """),
        {
            "id": tenant_id,
            "name": body.name,
            "email": body.email,
            "whatsapp_number": body.whatsapp_number,
            "telegram_chat_id": body.telegram_chat_id,
            "business_name": body.business_name,
            "plan": body.plan,
            "password_hash": placeholder_hash,
        },
    )

    # Create per-tenant schemas
    try:
        await db.execute(text("SELECT create_tenant_schemas(:tenant_id)"), {"tenant_id": str(tenant_id)})
    except Exception as e:
        logger.warning(f"Could not create schemas for tenant {tenant_id}: {e}")

    await db.commit()
    logger.info(f"Admin: created tenant '{body.name}' ({tenant_id})")
    return {
        "id": str(tenant_id),
        "name": body.name,
        "message": "Client created successfully"
    }
