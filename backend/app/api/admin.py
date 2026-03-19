"""
Admin API — for the owner (Lucas) only.
Protected by a separate ADMIN_SECRET_KEY in the .env.

Endpoints:
  GET  /api/admin/agents              — list all agents
  POST /api/admin/agents              — create new agent
  PUT  /api/admin/agents/{id}         — update agent
  DELETE /api/admin/agents/{id}       — deactivate agent

  GET  /api/admin/whatsapp/status     — Evolution API instance status
  POST /api/admin/whatsapp/connect    — start WhatsApp connection
  GET  /api/admin/whatsapp/qrcode     — get QR code image for scanning
  POST /api/admin/whatsapp/disconnect — disconnect instance

  GET  /api/admin/tenants             — list all clients (overview)
"""
import os
import json
import logging
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select

from app.database import get_db
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Admin authentication ─────────────────────────────────────────────────

ADMIN_SECRET = os.environ.get("ADMIN_SECRET_KEY", "changeme-admin-secret")


async def verify_admin(x_admin_key: str = Header(..., alias="X-Admin-Key")):
    """Simple header-based admin auth. Replace with stronger auth in production."""
    if x_admin_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    return True


# ─── Schemas ──────────────────────────────────────────────────────────────

class AgentCreate(BaseModel):
    name: str
    backstory: str
    personality: dict = {}
    greeting_templates: list = []
    confirmation_style: str = "brief"
    whatsapp_number: Optional[str] = None
    telegram_username: Optional[str] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    backstory: Optional[str] = None
    personality: Optional[dict] = None
    greeting_templates: Optional[list] = None
    confirmation_style: Optional[str] = None
    whatsapp_number: Optional[str] = None
    is_active: Optional[bool] = None


# ─── Agent management ─────────────────────────────────────────────────────

@router.get("/agents")
async def list_agents(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin),
):
    """List all agents with their stats."""
    result = await db.execute(
        text("""
            SELECT
                a.id, a.name, a.whatsapp_number, a.telegram_username,
                a.personality, a.is_active, a.created_at,
                COUNT(t.id) AS client_count
            FROM agents a
            LEFT JOIN tenants t ON t.agent_id = a.id
            GROUP BY a.id
            ORDER BY a.created_at ASC
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
                (id, name, backstory, personality, greeting_templates,
                 confirmation_style, whatsapp_number, telegram_username, is_active)
            VALUES
                (:id, :name, :backstory, :personality::jsonb, :templates::jsonb,
                 :confirmation_style, :whatsapp_number, :telegram_username, true)
        """),
        {
            "id": agent_id,
            "name": body.name,
            "backstory": body.backstory,
            "personality": json.dumps(body.personality),
            "templates": json.dumps(body.greeting_templates),
            "confirmation_style": body.confirmation_style,
            "whatsapp_number": body.whatsapp_number,
            "telegram_username": body.telegram_username,
        },
    )
    await db.commit()
    logger.info(f"Admin: created agent {body.name} ({agent_id})")
    return {"id": str(agent_id), "name": body.name, "message": "Agent created successfully"}


@router.put("/agents/{agent_id}")
async def update_agent(
    agent_id: str,
    body: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin),
):
    """Update an agent."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clauses = []
    params = {"id": agent_id}
    for field, value in updates.items():
        if field == "personality":
            set_clauses.append(f"{field} = :{field}::jsonb")
            params[field] = json.dumps(value)
        elif field == "greeting_templates":
            set_clauses.append(f"{field} = :{field}::jsonb")
            params[field] = json.dumps(value)
        else:
            set_clauses.append(f"{field} = :{field}")
            params[field] = value

    result = await db.execute(
        text(f"UPDATE agents SET {', '.join(set_clauses)} WHERE id = :id::uuid RETURNING id, name"),
        params,
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.commit()
    return {"id": str(row[0]), "name": row[1], "message": "Updated"}


@router.delete("/agents/{agent_id}")
async def deactivate_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin),
):
    """Deactivate an agent."""
    await db.execute(
        text("UPDATE agents SET is_active = false WHERE id = :id::uuid"),
        {"id": agent_id},
    )
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
    await db.execute(
        text("UPDATE tenants SET agent_id = :agent_id::uuid WHERE id = :tenant_id::uuid"),
        {"agent_id": agent_id, "tenant_id": tenant_id},
    )
    await db.commit()
    return {"message": f"Agent {agent_id[:8]} assigned to tenant {tenant_id[:8]}"}


# ─── WhatsApp (Evolution API) management ──────────────────────────────────

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
    resp.raise_for_status()
    return resp.json()


@router.get("/whatsapp/status")
async def whatsapp_status(_: bool = Depends(verify_admin)):
    """Get Evolution API instance connection status."""
    try:
        result = await _evolution_request("GET", f"/instance/connectionState/{settings.EVOLUTION_INSTANCE_NAME}")
        return result
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.post("/whatsapp/connect")
async def whatsapp_connect(_: bool = Depends(verify_admin)):
    """
    Create/connect the WhatsApp instance.
    After this, call /qrcode to get the QR code to scan.
    """
    try:
        # First try to get existing instance
        status = await _evolution_request("GET", f"/instance/connectionState/{settings.EVOLUTION_INSTANCE_NAME}")
        if status.get("instance", {}).get("state") == "open":
            return {"status": "already_connected", "message": "WhatsApp já está conectado!"}
    except Exception:
        pass

    try:
        # Create new instance
        result = await _evolution_request("POST", "/instance/create", {
            "instanceName": settings.EVOLUTION_INSTANCE_NAME,
            "token": settings.EVOLUTION_API_KEY,
            "qrcode": True,
            "integration": "WHATSAPP-BAILEYS",
            "webhook": {
                "url": f"{os.environ.get('BACKEND_PUBLIC_URL', 'http://backend:8000')}/api/v1/webhooks/whatsapp",
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
    After scanning, the agent is connected.
    """
    try:
        result = await _evolution_request("GET", f"/instance/connect/{settings.EVOLUTION_INSTANCE_NAME}")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not get QR code: {str(e)}")


@router.delete("/whatsapp/disconnect")
async def whatsapp_disconnect(_: bool = Depends(verify_admin)):
    """Disconnect and logout the WhatsApp instance."""
    try:
        result = await _evolution_request("DELETE", f"/instance/logout/{settings.EVOLUTION_INSTANCE_NAME}")
        return {"status": "disconnected", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Tenant (client) overview ─────────────────────────────────────────────

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
                a.name AS agent_name
            FROM tenants t
            LEFT JOIN agents a ON a.id = t.agent_id
            ORDER BY t.created_at DESC
        """)
    )
    tenants = [dict(r._mapping) for r in result.fetchall()]
    return {"tenants": tenants, "total": len(tenants)}


@router.get("/stats")
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin),
):
    """Quick overview stats for the admin dashboard."""
    tenants_result = await db.execute(text("SELECT COUNT(*) FROM tenants WHERE is_active = true"))
    agents_result = await db.execute(text("SELECT COUNT(*) FROM agents WHERE is_active = true"))
    docs_result = await db.execute(text("SELECT COUNT(*) FROM imported_documents"))

    return {
        "active_clients": (tenants_result.fetchone() or [0])[0],
        "active_agents": (agents_result.fetchone() or [0])[0],
        "imported_documents": (docs_result.fetchone() or [0])[0],
    }
