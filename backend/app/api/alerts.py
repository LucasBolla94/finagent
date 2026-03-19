"""
Alerts API — configure financial alerts that the agent monitors.

GET    /api/v1/alerts        — list alerts
POST   /api/v1/alerts        — create alert
PUT    /api/v1/alerts/{id}   — update alert (toggle on/off, change condition)
DELETE /api/v1/alerts/{id}   — delete alert

Alert types:
  - balance_below     : balance drops below X
  - expense_above     : monthly expenses exceed X
  - bill_due          : upcoming bill in N days
  - income_expected   : expected income not received
  - category_limit    : spending category exceeds budget
"""
import uuid
import logging
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.models.tenant import Tenant
from app.middleware.auth import get_current_tenant

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Schemas ──────────────────────────────────────────────────────────────

class AlertCreate(BaseModel):
    type: str                          # balance_below | expense_above | bill_due | category_limit
    name: str                          # "Saldo baixo Nubank"
    condition: dict                    # {"threshold": 500, "account_id": "..."}
    message: str                       # Message to send when triggered
    channels: list[str] = ["whatsapp"]  # whatsapp | telegram | web


class AlertUpdate(BaseModel):
    name: Optional[str] = None
    condition: Optional[dict] = None
    message: Optional[str] = None
    channels: Optional[list[str]] = None
    is_active: Optional[bool] = None


# ─── Helpers ──────────────────────────────────────────────────────────────

def _fin_schema(tenant: Tenant) -> str:
    return f"tenant_{str(tenant.id).replace('-', '_')}_financial"


# ─── Endpoints ────────────────────────────────────────────────────────────

@router.get("")
async def list_alerts(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
    active_only: bool = Query(False),
):
    """List all alerts configured for this client."""
    schema = _fin_schema(tenant)

    where = "WHERE is_active = true" if active_only else ""
    sql = text(f"""
        SELECT id, type, name, condition, message, channels,
               is_active, last_triggered, trigger_count, created_at
        FROM "{schema}".alerts
        {where}
        ORDER BY created_at DESC
    """)
    result = await db.execute(sql)
    rows = result.fetchall()
    return {"alerts": [dict(r._mapping) for r in rows]}


@router.post("", status_code=201)
async def create_alert(
    body: AlertCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new alert.

    Example — balance below R$ 500:
    {
        "type": "balance_below",
        "name": "Saldo baixo",
        "condition": {"threshold": 500, "account_id": "uuid-here"},
        "message": "⚠️ Seu saldo está abaixo de R$ 500!",
        "channels": ["whatsapp"]
    }
    """
    schema = _fin_schema(tenant)
    alert_id = uuid.uuid4()

    sql = text(f"""
        INSERT INTO "{schema}".alerts (id, type, name, condition, message, channels)
        VALUES (:id, :type, :name, :condition::jsonb, :message, :channels)
        RETURNING *
    """)

    import json
    try:
        result = await db.execute(sql, {
            "id": alert_id,
            "type": body.type,
            "name": body.name,
            "condition": json.dumps(body.condition),
            "message": body.message,
            "channels": body.channels,
        })
        row = result.fetchone()
        await db.commit()
        return dict(row._mapping)
    except Exception as e:
        await db.rollback()
        logger.error(f"Create alert error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create alert")


@router.put("/{alert_id}")
async def update_alert(
    alert_id: str,
    body: AlertUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Update an alert — toggle active/inactive, change condition, etc."""
    schema = _fin_schema(tenant)

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    import json
    set_clauses = []
    params = {"id": alert_id}
    for field, value in updates.items():
        if field == "condition":
            set_clauses.append(f"{field} = :{field}::jsonb")
            params[field] = json.dumps(value)
        else:
            set_clauses.append(f"{field} = :{field}")
            params[field] = value

    sql = text(f"""
        UPDATE "{schema}".alerts
        SET {', '.join(set_clauses)}
        WHERE id = :id::uuid
        RETURNING *
    """)

    try:
        result = await db.execute(sql, params)
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Alert not found")
        await db.commit()
        return dict(row._mapping)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Update alert error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update alert")


@router.delete("/{alert_id}", status_code=204)
async def delete_alert(
    alert_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Delete an alert."""
    schema = _fin_schema(tenant)

    sql = text(f"""
        DELETE FROM "{schema}".alerts WHERE id = :id::uuid RETURNING id
    """)
    result = await db.execute(sql, {"id": alert_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")

    await db.commit()
    return None
