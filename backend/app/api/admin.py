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

  GET    /api/admin/logs             ← system log viewer
  DELETE /api/admin/logs             ← clear old logs
"""
import asyncio
import json
import logging
import secrets
import time
import uuid
import hashlib
from datetime import date
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.config import settings
from app.services.log_service import syslog

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Admin authentication ─────────────────────────────────────────────────────

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
        await syslog.warning("auth", "admin_invalid_key", "Invalid X-Admin-Key attempt")
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
    """Extract base64 QR code from various Evolution API v2 response shapes."""
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

    # Shape 3: {"code": "..."} (raw QR string)
    code = data.get("code")
    if code and len(code) > 20:
        return code

    return None


def _extract_state(data: dict) -> Optional[str]:
    """Extract connection state from Evolution API response."""
    inst = data.get("instance", {})
    if isinstance(inst, dict):
        return inst.get("state")
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


# ─── System Logs ──────────────────────────────────────────────────────────────

@router.get("/logs")
async def get_logs(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin),
    level: Optional[str] = Query(None, description="Filter: ERROR WARNING INFO DEBUG"),
    service: Optional[str] = Query(None, description="Filter by service (whatsapp, auth, ...)"),
    search: Optional[str] = Query(None, description="Search in message field"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """
    Returns recent system log entries, newest first.
    Query params: level, service, search, limit, offset
    """
    conditions = []
    params: dict = {"limit": limit, "offset": offset}

    if level:
        conditions.append("level = :level")
        params["level"] = level.upper()
    if service:
        conditions.append("service = :service")
        params["service"] = service.lower()
    if search:
        conditions.append("message ILIKE :search")
        params["search"] = f"%{search}%"

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    rows = await db.execute(
        text(f"""
            SELECT id, created_at, level, service, event, message, details, duration_ms, user_id
            FROM system_logs
            {where}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )

    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
    total_r = await db.execute(
        text(f"SELECT COUNT(*) FROM system_logs {where}"),
        count_params,
    )
    total = (total_r.fetchone() or [0])[0]

    logs = []
    for r in rows.fetchall():
        logs.append({
            "id":          r[0],
            "created_at":  r[1].isoformat() if r[1] else None,
            "level":       r[2],
            "service":     r[3],
            "event":       r[4],
            "message":     r[5],
            "details":     r[6],
            "duration_ms": r[7],
            "user_id":     r[8],
        })

    return {"logs": logs, "total": total, "limit": limit, "offset": offset}


@router.delete("/logs")
async def clear_old_logs(
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_admin),
    days: int = Query(30, ge=1, description="Delete logs older than N days"),
):
    """Delete logs older than N days (default 30)."""
    result = await db.execute(
        text(f"DELETE FROM system_logs WHERE created_at < NOW() - INTERVAL '{days} days'"),
    )
    await db.commit()
    deleted = result.rowcount
    await syslog.info("admin", "logs_cleared", f"Deleted {deleted} log entries older than {days} days")
    return {"deleted": deleted, "message": f"Deleted logs older than {days} days"}


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
    await syslog.info("admin", "agent_create", f"Created agent '{body.name}'", details={"id": str(agent_id)})
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

@router.get("/whatsapp/status")
async def whatsapp_status(_: bool = Depends(verify_admin)):
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
    Unified connect endpoint.  Returns:
      {"status": "connected"}                  — already open
      {"status": "qr_ready", "qr_base64": ...} — scan this

    QR generation strategy with progressive restarts + nuclear fallback:
      Round 1:  5s  → /instance/connect
      Round 2:  restart + 8s  → /instance/connect
      Round 3:  restart + 12s → /instance/connect
      Round 4:  DELETE + CREATE + 10s (nuclear option — always works)

    Every step is persisted to system_logs for diagnosis at GET /api/admin/logs.
    """
    backend_url = settings.BACKEND_PUBLIC_URL or "http://backend:8000"
    instance_name = settings.EVOLUTION_INSTANCE_NAME
    connect_start = time.monotonic()

    await syslog.info("whatsapp", "connect_start",
        f"Starting WhatsApp connect for instance '{instance_name}'",
        details={"instance": instance_name, "backend_url": backend_url})

    # ── Step 1: Check current state ──────────────────────────────────────
    state_code, state_data = await _evo("GET", f"/instance/connectionState/{instance_name}")

    await syslog.debug("whatsapp", "state_check",
        f"connectionState → HTTP {state_code}",
        details={"http_code": state_code, "response": state_data})

    if state_code == 200:
        state = _extract_state(state_data)
        if state == "open":
            owner = state_data.get("instance", {}).get("owner") if isinstance(state_data.get("instance"), dict) else None
            await syslog.info("whatsapp", "already_connected", f"Already connected (owner: {owner})")
            return {"status": "connected", "state": "open", "owner": owner}
        await syslog.info("whatsapp", "instance_exists",
            f"Instance exists, state={state}. Proceeding to QR generation.")

    elif state_code == 404:
        # ── Step 2: Create instance ──────────────────────────────────────
        await syslog.info("whatsapp", "instance_create",
            f"Instance '{instance_name}' not found — creating...")
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

        await syslog.info("whatsapp", "instance_created",
            f"/instance/create → HTTP {create_code}",
            details={"http_code": create_code, "response": create_data})

        if create_code == 409:
            await syslog.info("whatsapp", "instance_409", "Instance already exists (409) — continuing")
        elif create_code not in (200, 201):
            detail = create_data.get("detail") or create_data.get("message") or str(create_data)
            await syslog.error("whatsapp", "instance_create_failed",
                f"Failed to create instance: HTTP {create_code} — {detail}",
                details={"http_code": create_code, "response": create_data})
            if create_code == 403:
                raise HTTPException(status_code=500, detail=(
                    "Evolution API returned 403 Forbidden. "
                    "Verify AUTHENTICATION_TYPE=apikey and AUTHENTICATION_API_KEY "
                    f"are set in docker-compose. (key: '{settings.EVOLUTION_API_KEY[:8]}...')"
                ))
            raise HTTPException(status_code=500,
                detail=f"Evolution API error ({create_code}): {detail}")

        qr = _extract_qr(create_data)
        if qr:
            elapsed = int((time.monotonic() - connect_start) * 1000)
            await syslog.info("whatsapp", "qr_from_create",
                "QR code obtained directly from /instance/create", duration_ms=elapsed)
            return {"status": "qr_ready", "state": "connecting", "qr_base64": qr}

    elif state_code == 503:
        await syslog.error("whatsapp", "evolution_unreachable",
            f"Evolution API unreachable at {settings.EVOLUTION_API_URL}",
            details={"url": settings.EVOLUTION_API_URL})
        raise HTTPException(status_code=503,
            detail=f"Evolution API unreachable at {settings.EVOLUTION_API_URL}. Is the evolution_api container running?")
    else:
        await syslog.error("whatsapp", "state_unexpected",
            f"Unexpected HTTP {state_code} from connectionState",
            details={"http_code": state_code, "response": state_data})
        raise HTTPException(status_code=500,
            detail=f"Unexpected response from Evolution API: HTTP {state_code}")

    # ── Step 3: QR generation with progressive restart + nuclear fallback ──
    #
    # Root cause of {"count": 0}:
    #   Baileys (WA WebSocket inside Evolution API) initializes asynchronously.
    #   While not ready, /instance/connect returns {"count": 0}.
    #   Also happens when stale session is loaded from PostgreSQL.
    #
    # Strategy:
    #   Round 1: wait 5s  → fetch QR
    #   Round 2: restart Baileys + wait 8s  → fetch QR
    #   Round 3: restart Baileys + wait 12s → fetch QR
    #   Round 4: DELETE instance + CREATE fresh + wait 10s → fetch QR (nuclear)

    qr: Optional[str] = None
    last_raw: dict = {}
    round_logs = []

    async def _fetch_qr(round_num: int) -> Optional[str]:
        nonlocal last_raw
        t0 = time.monotonic()
        code, data = await _evo("GET", f"/instance/connect/{instance_name}")
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        last_raw = data

        count_val = data.get("count")
        qr_val = _extract_qr(data)
        state_val = _extract_state(data)

        entry = {
            "round": round_num,
            "http_code": code,
            "count": count_val,
            "has_qr": qr_val is not None,
            "state": state_val,
            "response_keys": list(data.keys()),
            "duration_ms": elapsed_ms,
        }
        round_logs.append(entry)

        await syslog.info("whatsapp", "qr_attempt",
            f"Round {round_num}: HTTP {code}, count={count_val}, has_qr={qr_val is not None}, state={state_val}",
            details=entry, duration_ms=elapsed_ms)

        if code != 200:
            return None
        if state_val == "open":
            return "ALREADY_CONNECTED"
        return qr_val

    async def _restart_baileys(round_num: int) -> None:
        t0 = time.monotonic()
        r_code, r_data = await _evo("POST", f"/instance/restart/{instance_name}")
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        await syslog.info("whatsapp", "baileys_restart",
            f"Restart before round {round_num}: HTTP {r_code}",
            details={"http_code": r_code, "response": r_data, "duration_ms": elapsed_ms})

    async def _nuclear_recreate() -> Optional[str]:
        """Delete instance + recreate from scratch. Last resort."""
        await syslog.warning("whatsapp", "nuclear_recreate",
            "All restart rounds failed — deleting and recreating instance",
            details={"instance": instance_name, "round_logs": round_logs})

        del_code, del_data = await _evo("DELETE", f"/instance/delete/{instance_name}")
        await syslog.info("whatsapp", "nuclear_delete",
            f"/instance/delete → HTTP {del_code}",
            details={"http_code": del_code, "response": del_data})

        await asyncio.sleep(2.0)

        c_code, c_data = await _evo("POST", "/instance/create", {
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
        await syslog.info("whatsapp", "nuclear_create",
            f"/instance/create → HTTP {c_code}",
            details={"http_code": c_code, "response": c_data})

        if c_code not in (200, 201):
            await syslog.error("whatsapp", "nuclear_create_failed",
                f"Nuclear recreate failed: HTTP {c_code}",
                details={"http_code": c_code, "response": c_data})
            return None

        # QR might be directly in create response
        qr_direct = _extract_qr(c_data)
        if qr_direct:
            await syslog.info("whatsapp", "nuclear_qr_from_create",
                "QR from nuclear /instance/create response")
            return qr_direct

        # Wait for fresh Baileys
        await syslog.info("whatsapp", "nuclear_waiting",
            "Waiting 10s for fresh Baileys after nuclear recreate...")
        await asyncio.sleep(10.0)
        n_code, n_data = await _evo("GET", f"/instance/connect/{instance_name}")
        await syslog.info("whatsapp", "nuclear_qr_fetch",
            f"Nuclear QR fetch: HTTP {n_code}, count={n_data.get('count')}",
            details={"http_code": n_code, "response": n_data})
        return _extract_qr(n_data)

    # Round 1
    await syslog.info("whatsapp", "qr_round1_start",
        "Round 1: waiting 5s for Baileys to initialize...")
    await asyncio.sleep(5.0)
    qr = await _fetch_qr(1)
    if qr == "ALREADY_CONNECTED":
        return {"status": "connected", "state": "open"}

    # Round 2
    if not qr:
        await _restart_baileys(2)
        await syslog.info("whatsapp", "qr_round2_start",
            "Round 2: waiting 8s after Baileys restart...")
        await asyncio.sleep(8.0)
        qr = await _fetch_qr(2)
        if qr == "ALREADY_CONNECTED":
            return {"status": "connected", "state": "open"}

    # Round 3
    if not qr:
        await _restart_baileys(3)
        await syslog.info("whatsapp", "qr_round3_start",
            "Round 3: waiting 12s after Baileys restart...")
        await asyncio.sleep(12.0)
        qr = await _fetch_qr(3)
        if qr == "ALREADY_CONNECTED":
            return {"status": "connected", "state": "open"}

    # Round 4: nuclear
    if not qr:
        qr = await _nuclear_recreate()

    if not qr:
        elapsed_total = int((time.monotonic() - connect_start) * 1000)
        await syslog.error("whatsapp", "qr_all_failed",
            "QR code unavailable after all rounds including nuclear recreate",
            details={
                "last_response": str(last_raw)[:500],
                "round_logs": round_logs,
                "total_duration_ms": elapsed_total,
                "evolution_url": settings.EVOLUTION_API_URL,
            },
            duration_ms=elapsed_total)
        raise HTTPException(
            status_code=500,
            detail=(
                "WhatsApp QR code unavailable after 3 restarts + instance recreation. "
                f"Last response: {str(last_raw)[:200]}. "
                "Check GET /api/admin/logs for full diagnostics."
            )
        )

    elapsed_total = int((time.monotonic() - connect_start) * 1000)
    await syslog.info("whatsapp", "qr_success",
        "QR code obtained successfully",
        duration_ms=elapsed_total,
        details={"rounds_needed": len(round_logs)})
    return {"status": "qr_ready", "state": "connecting", "qr_base64": qr}


@router.get("/whatsapp/qrcode")
async def whatsapp_qrcode(_: bool = Depends(verify_admin)):
    """Refresh / get the current QR code."""
    qr_code, qr_data = await _evo("GET", f"/instance/connect/{settings.EVOLUTION_INSTANCE_NAME}")

    if qr_code == 404:
        raise HTTPException(status_code=404,
            detail="WhatsApp instance not found. Use POST /whatsapp/connect first.")
    if qr_code != 200:
        raise HTTPException(status_code=500,
            detail=f"Evolution API error ({qr_code}): {qr_data.get('detail', str(qr_data))}")

    qr = _extract_qr(qr_data)
    if not qr:
        state = _extract_state(qr_data)
        if state == "open":
            return {"status": "connected", "state": "open"}
        raise HTTPException(status_code=500,
            detail=f"QR code not available. Response: {str(qr_data)[:300]}")

    return {"status": "qr_ready", "qr_base64": qr}


@router.delete("/whatsapp/disconnect")
async def whatsapp_disconnect(_: bool = Depends(verify_admin)):
    status_code, data = await _evo("DELETE", f"/instance/logout/{settings.EVOLUTION_INSTANCE_NAME}")
    if status_code == 404:
        return {"status": "already_disconnected"}
    if status_code not in (200, 201):
        raise HTTPException(status_code=500, detail=f"Disconnect failed ({status_code}): {data}")
    await syslog.info("whatsapp", "disconnected", "WhatsApp session logged out")
    return {"status": "disconnected"}


@router.delete("/whatsapp/delete")
async def whatsapp_delete_instance(_: bool = Depends(verify_admin)):
    """Fully delete the WhatsApp instance (nuclear option)."""
    status_code, data = await _evo("DELETE", f"/instance/delete/{settings.EVOLUTION_INSTANCE_NAME}")
    if status_code == 404:
        return {"status": "not_found", "message": "Instance did not exist"}
    if status_code not in (200, 201):
        raise HTTPException(status_code=500, detail=f"Delete failed ({status_code}): {data}")
    await syslog.warning("whatsapp", "instance_deleted", "WhatsApp instance manually deleted by admin")
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
            raise HTTPException(status_code=409,
                detail=f"WhatsApp {body.whatsapp_number} already registered")

    if body.email:
        dup_email = await db.execute(
            text("SELECT id FROM tenants WHERE email = :email"),
            {"email": body.email},
        )
        if dup_email.fetchone():
            raise HTTPException(status_code=409,
                detail=f"Email {body.email} already registered")

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
    await syslog.info("admin", "tenant_create", f"Created tenant '{body.name}'",
        details={"id": str(tenant_id), "plan": body.plan})
    return {"id": str(tenant_id), "name": body.name, "message": "Client created"}
