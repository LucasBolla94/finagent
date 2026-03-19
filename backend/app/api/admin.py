"""
Admin API — for the owner (Lucas) only.
Protected by ADMIN_API_KEY in .env (via settings.ADMIN_API_KEY).

All routes require the header:  X-Admin-Key: <ADMIN_API_KEY>

Endpoints:
  GET    /api/admin/stats
  GET    /api/admin/agents
  POST   /api/admin/agents
  PUT    /api/admin/agents/{id}
  DELETE /api/admin/agents/{id}
  POST   /api/admin/agents/{id}/assign/{tenant_id}

  GET    /api/admin/whatsapp/status
  POST   /api/admin/whatsapp/connect
  GET    /api/admin/whatsapp/qrcode
  DELETE /api/admin/whatsapp/disconnect
  DELETE /api/admin/whatsapp/delete

  GET    /api/admin/tenants
  POST   /api/admin/tenants
"""
import json
import logging
import secrets
import uuid
import hashlib
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
# Single source of truth: settings.ADMIN_API_KEY (from .env ADMIN_API_KEY).
# No more os.environ.get("ADMIN_SECRET_KEY") — that was the source of the
# "Admin key not configured" (503) bug when the .env used a different var name.

async def verify_admin(x_admin_key: str = Header(..., alias="X-Admin-Key")):
    if not settings.ADMIN_API_KEY:
        raise HTTPException(
            status_code=503,
            detail=(
                "Admin key not configured. "
                "Set ADMIN_API_KEY in your .env file and restart the backend."
            )
        )
    if not secrets.compare_digest(
        x_admin_key.encode("utf-8"),
        settings.ADMIN_API_KEY.encode("utf-8"),
    ):
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


# ─── Evolution API helper ─────────────────────────────────────────────────────

async def _evo(method: str, path: str, body: dict = None) -> tuple[int, dict]:
    """
    Make an authenticated request to Evolution API.
    Returns (status_code, response_body).
    Always reads the full body INSIDE the context manager to avoid issues.
    Does NOT raise on error — caller decides what to do with status codes.
    """
    url = f"{settings.EVOLUTION_API_URL}{path}"
    headers = {
        "apikey": settings.EVOLUTION_API_KEY,
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == "GET":
                resp = await client.get(url, headers=headers)
            elif method == "POST":
                resp = await client.post(url, headers=headers, json=body or {})
            elif method == "DELETE":
                resp = await client.delete(url, headers=headers)
            else:
                raise ValueError(f"Unknown method: {method}")

            status = resp.status_code
            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text}

        return status, data

    except httpx.ConnectError:
        logger.error(f"Evolution API unreachable at {settings.EVOLUTION_API_URL}")
        return 503, {"error": "evolution_unreachable", "detail": f"Cannot connect to Evolution API at {settings.EVOLUTION_API_URL}"}
    except httpx.TimeoutException:
        logger.error(f"Evolution API timeout on {method} {path}")
        return 504, {"error": "evolution_timeout", "detail": "Evolution API timeout"}
    except Exception as e:
        logger.error(f"Evolution API unexpected error: {e}")
        return 500, {"error": "evolution_error", "detail": str(e)}


def _extract_qr(data: dict) -> Optional[str]:
    """
    Extract base64 QR code from various Evolution API v2 response shapes.
    Returns data-URI string or None.
    """
    # Shape 1: {"qrcode": {"base64": "data:image/..."}}
    qr = data.get("qrcode", {})
    if isinstance(qr, dict):
        b64 = qr.get("base64") or qr.get("code")
        if b64:
            return b64 if b64.startswith("data:") else f"data:image/png;base64,{b64}"

    # Shape 2: {"base64": "..."}
    b64 = data.get("base64")
    if b64:
        return b64 if b64.startswith("data:") else f"data:image/png;base64,{b64}"

    # Shape 3: {"code": "..."}  (raw QR string, not image)
    code = data.get("code")
    if code and len(code) > 20:
        return code  # raw QR string — frontend can render with a QR library if needed

    return None


def _extract_state(data: dict) -> Optional[str]:
    """Extract connection state from Evolution API response."""
    # Shape: {"instance": {"state": "open"}}
    inst = data.get("instance", {})
    if isinstance(inst, dict):
        return inst.get("state")
    # Shape: {"state": "open"}
    return data.get("state")


# ─── Dashboard stats ──────────────────────────────────────────────────────────

@router.get("/stats")
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin),
):
    tenants_r = await db.execute(text("SELECT COUNT(*) FROM tenants WHERE is_active = true"))
    agents_r = await db.execute(text("SELECT COUNT(*) FROM agents WHERE is_active = true"))
    docs_r = await db.execute(text("SELECT COUNT(*) FROM imported_documents"))

    active_clients = (tenants_r.fetchone() or [0])[0]
    active_agents = (agents_r.fetchone() or [0])[0]
    imported_docs = (docs_r.fetchone() or [0])[0]

    # Messages today across all tenant context schemas
    messages_today = 0
    try:
        today_str = date.today().isoformat()
        tenants_result = await db.execute(text("SELECT id FROM tenants WHERE is_active = true"))
        tenant_ids = [str(r[0]).replace("-", "") for r in tenants_result.fetchall()]
        for tid in tenant_ids:
            schema = f"tenant_{tid}_context"
            try:
                result = await db.execute(
                    text(f"""
                        SELECT COUNT(*) FROM {schema}.conversation_history
                        WHERE role = 'assistant' AND DATE(created_at) = :today
                    """),
                    {"today": today_str},
                )
                messages_today += (result.fetchone() or [0])[0]
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Could not count messages_today: {e}")

    # WhatsApp state (non-blocking — if Evolution is down, just return null)
    whatsapp_state = None
    status_code, wa_data = await _evo(
        "GET", f"/instance/connectionState/{settings.EVOLUTION_INSTANCE_NAME}"
    )
    if status_code == 200:
        whatsapp_state = _extract_state(wa_data)

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
    result = await db.execute(
        text("""
            SELECT
                a.id, a.name, a.description, a.system_prompt, a.model,
                a.is_active, a.created_at,
                t_agg.tenant_id  AS tenant_id,
                t_agg.tenant_name AS tenant_name,
                COALESCE(t_agg.client_count, 0) AS client_count
            FROM agents a
            LEFT JOIN (
                SELECT agent_id,
                       MAX(id::text)  AS tenant_id,
                       MAX(name)      AS tenant_name,
                       COUNT(*)       AS client_count
                FROM tenants
                GROUP BY agent_id
            ) t_agg ON t_agg.agent_id = a.id
            ORDER BY a.is_active DESC, a.created_at ASC
        """)
    )
    return {"agents": [dict(r._mapping) for r in result.fetchall()]}


@router.post("/agents", status_code=201)
async def create_agent(
    body: AgentCreate,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin),
):
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
    return {"id": str(agent_id), "name": body.name, "message": "Agent created"}


@router.put("/agents/{agent_id}")
async def update_agent(
    agent_id: str,
    body: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clauses, params = [], {"id": agent_id}
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
    agent_r = await db.execute(
        text("SELECT id FROM agents WHERE id = :id::uuid AND is_active = true"),
        {"id": agent_id}
    )
    if not agent_r.fetchone():
        raise HTTPException(status_code=404, detail="Agent not found or inactive")

    result = await db.execute(
        text("UPDATE tenants SET agent_id = :aid::uuid WHERE id = :tid::uuid RETURNING id"),
        {"aid": agent_id, "tid": tenant_id},
    )
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Tenant not found")
    await db.commit()
    return {"message": "Agent assigned"}


# ─── WhatsApp (Evolution API v2) ──────────────────────────────────────────────
#
# Complete flow:
#   1. POST /whatsapp/connect  → creates instance (if not exists) + returns QR code
#   2. User scans QR on phone
#   3. GET  /whatsapp/status   → polls until state == "open"
#   4. GET  /whatsapp/qrcode   → refresh QR if expired before scanning
#   5. DELETE /whatsapp/disconnect → logout
#
# Evolution API v2 state values: "open" | "connecting" | "close"
# 403 on /instance/create means AUTHENTICATION_TYPE=apikey is missing in docker-compose
# 409 on /instance/create means instance already exists (handled gracefully below)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/whatsapp/status")
async def whatsapp_status(_: bool = Depends(verify_admin)):
    """
    Returns current WhatsApp connection state.
    state values: "open" (connected) | "connecting" | "close" | null (not created)
    """
    status_code, data = await _evo(
        "GET", f"/instance/connectionState/{settings.EVOLUTION_INSTANCE_NAME}"
    )
    if status_code == 404:
        return {"state": None, "status": "not_created", "instance_name": settings.EVOLUTION_INSTANCE_NAME}
    if status_code == 503:
        return {"state": "error", "status": "evolution_unreachable", "detail": data.get("detail")}
    if status_code != 200:
        return {"state": "error", "status": f"http_{status_code}", "detail": str(data)}

    state = _extract_state(data)
    owner = data.get("instance", {}).get("owner") if isinstance(data.get("instance"), dict) else None
    return {"state": state, "status": "ok", "owner": owner, "raw": data}


@router.post("/whatsapp/connect")
async def whatsapp_connect(_: bool = Depends(verify_admin)):
    """
    Unified connect endpoint:
    - If already connected → returns {"status": "connected"}
    - If instance exists but disconnected → returns {"status": "qr_ready", "qr_base64": "..."}
    - If instance doesn't exist → creates it, then returns QR code
    - Always returns QR code when not connected (ready to scan)
    """
    backend_url = os.environ.get("BACKEND_PUBLIC_URL", "http://backend:8000")
    instance_name = settings.EVOLUTION_INSTANCE_NAME

    # ── Step 1: Check current state ──────────────────────────────────────
    state_code, state_data = await _evo("GET", f"/instance/connectionState/{instance_name}")

    if state_code == 200:
        state = _extract_state(state_data)
        if state == "open":
            owner = state_data.get("instance", {}).get("owner") if isinstance(state_data.get("instance"), dict) else None
            return {"status": "connected", "state": "open", "owner": owner}
        # Instance exists but not connected → go straight to QR
        logger.info(f"WhatsApp instance '{instance_name}' exists, state={state}. Getting QR...")
    elif state_code == 404:
        # ── Step 2: Instance doesn't exist → create it ────────────────────
        logger.info(f"WhatsApp instance '{instance_name}' not found. Creating...")
        create_code, create_data = await _evo("POST", "/instance/create", {
            "instanceName": instance_name,
            "qrcode": True,
            "integration": "WHATSAPP-BAILEYS",
            "webhook": {
                "url": f"{backend_url}/api/v1/webhooks/whatsapp",
                "byEvents": True,
                "base64": True,
                "events": ["MESSAGES_UPSERT", "QRCODE_UPDATED", "CONNECTION_UPDATE"],
            },
        })

        if create_code == 409:
            # Race condition: created between our check and now — continue to QR
            logger.info("Instance already exists (409) — continuing to QR step")
        elif create_code not in (200, 201):
            detail = create_data.get("detail") or create_data.get("message") or str(create_data)
            logger.error(f"Failed to create Evolution instance: {create_code} {detail}")
            if create_code == 403:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Evolution API returned 403 Forbidden. "
                        "Verify AUTHENTICATION_TYPE=apikey and AUTHENTICATION_API_KEY "
                        "are set correctly in docker-compose. "
                        f"(key used: '{settings.EVOLUTION_API_KEY[:8]}...')"
                    )
                )
            raise HTTPException(status_code=500, detail=f"Evolution API error ({create_code}): {detail}")

        # If create returned a QR code directly, use it
        qr = _extract_qr(create_data)
        if qr:
            logger.info("QR code returned directly from /instance/create")
            return {"status": "qr_ready", "state": "connecting", "qr_base64": qr}
    elif state_code == 503:
        raise HTTPException(
            status_code=503,
            detail=f"Evolution API unreachable at {settings.EVOLUTION_API_URL}. Is the evolution_api container running?"
        )
    else:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected response from Evolution API: HTTP {state_code}"
        )

    # ── Step 3: Get QR code ───────────────────────────────────────────────
    qr_code, qr_data = await _evo("GET", f"/instance/connect/{instance_name}")
    logger.info(f"QR code endpoint returned: {qr_code} — keys: {list(qr_data.keys())}")

    if qr_code != 200:
        detail = qr_data.get("detail") or qr_data.get("message") or str(qr_data)
        raise HTTPException(
            status_code=500,
            detail=f"Could not get QR code ({qr_code}): {detail}"
        )

    qr = _extract_qr(qr_data)
    if not qr:
        logger.warning(f"QR code not found in response: {qr_data}")
        raise HTTPException(
            status_code=500,
            detail=f"QR code not found in Evolution API response. Raw: {str(qr_data)[:300]}"
        )

    return {"status": "qr_ready", "state": "connecting", "qr_base64": qr}


@router.get("/whatsapp/qrcode")
async def whatsapp_qrcode(_: bool = Depends(verify_admin)):
    """Refresh / get the current QR code for scanning."""
    qr_code, qr_data = await _evo("GET", f"/instance/connect/{settings.EVOLUTION_INSTANCE_NAME}")

    if qr_code == 404:
        raise HTTPException(
            status_code=404,
            detail="WhatsApp instance not found. Use POST /whatsapp/connect first."
        )
    if qr_code != 200:
        raise HTTPException(
            status_code=500,
            detail=f"Evolution API error ({qr_code}): {qr_data.get('detail', str(qr_data))}"
        )

    qr = _extract_qr(qr_data)
    if not qr:
        # Might be connected already
        state = _extract_state(qr_data)
        if state == "open":
            return {"status": "connected", "state": "open"}
        raise HTTPException(
            status_code=500,
            detail=f"QR code not available. Response: {str(qr_data)[:300]}"
        )

    return {"status": "qr_ready", "qr_base64": qr}


@router.delete("/whatsapp/disconnect")
async def whatsapp_disconnect(_: bool = Depends(verify_admin)):
    """Logout the WhatsApp session (keeps the instance, just disconnects the phone)."""
    status_code, data = await _evo(
        "DELETE", f"/instance/logout/{settings.EVOLUTION_INSTANCE_NAME}"
    )
    if status_code == 404:
        return {"status": "already_disconnected"}
    if status_code not in (200, 201):
        raise HTTPException(
            status_code=500,
            detail=f"Disconnect failed ({status_code}): {data}"
        )
    return {"status": "disconnected"}


@router.delete("/whatsapp/delete")
async def whatsapp_delete_instance(_: bool = Depends(verify_admin)):
    """
    Fully delete the WhatsApp instance (nuclear option — use when instance is stuck).
    After this, POST /whatsapp/connect will recreate it from scratch.
    """
    status_code, data = await _evo(
        "DELETE", f"/instance/delete/{settings.EVOLUTION_INSTANCE_NAME}"
    )
    if status_code == 404:
        return {"status": "not_found", "message": "Instance did not exist"}
    if status_code not in (200, 201):
        raise HTTPException(
            status_code=500,
            detail=f"Delete failed ({status_code}): {data}"
        )
    return {"status": "deleted", "message": "Instance deleted. Use connect to recreate."}


# ─── Tenant management ────────────────────────────────────────────────────────

@router.get("/tenants")
async def list_tenants(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin),
):
    result = await db.execute(
        text("""
            SELECT
                t.id, t.name, t.email, t.business_name,
                t.plan, t.whatsapp_number, t.telegram_chat_id,
                t.is_active, t.created_at,
                a.id   AS agent_id,
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
    if body.whatsapp_number:
        dup = await db.execute(
            text("SELECT id FROM tenants WHERE whatsapp_number = :phone"),
            {"phone": body.whatsapp_number},
        )
        if dup.fetchone():
            raise HTTPException(
                status_code=409,
                detail=f"WhatsApp {body.whatsapp_number} already registered"
            )

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

    try:
        await db.execute(
            text("SELECT create_tenant_schemas(:tenant_id)"),
            {"tenant_id": str(tenant_id)}
        )
    except Exception as e:
        logger.warning(f"Could not create schemas for tenant {tenant_id}: {e}")

    await db.commit()
    logger.info(f"Admin: created tenant '{body.name}' ({tenant_id})")
    return {"id": str(tenant_id), "name": body.name, "message": "Client created"}
