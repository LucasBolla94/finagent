"""
Transactions CRUD API.

GET    /api/v1/transactions         — list transactions (with filters)
POST   /api/v1/transactions         — create new transaction
GET    /api/v1/transactions/{id}    — get one transaction
PUT    /api/v1/transactions/{id}    — update transaction
DELETE /api/v1/transactions/{id}    — delete transaction
"""
import uuid
import logging
from typing import Optional
from datetime import date

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

class TransactionCreate(BaseModel):
    type: str                          # income | expense | transfer
    amount: float
    description: str
    date: date
    category_id: Optional[str] = None
    account_id: Optional[str] = None
    notes: Optional[str] = None
    due_date: Optional[date] = None
    status: str = "paid"               # paid | pending | overdue
    tags: list[str] = []


class TransactionUpdate(BaseModel):
    type: Optional[str] = None
    amount: Optional[float] = None
    description: Optional[str] = None
    date: Optional[date] = None
    category_id: Optional[str] = None
    account_id: Optional[str] = None
    notes: Optional[str] = None
    due_date: Optional[date] = None
    status: Optional[str] = None
    tags: Optional[list[str]] = None


# ─── Helpers ──────────────────────────────────────────────────────────────

def _fin_schema(tenant: Tenant) -> str:
    return f"tenant_{str(tenant.id).replace('-', '_')}_financial"


# ─── Endpoints ────────────────────────────────────────────────────────────

@router.get("")
async def list_transactions(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
    type: Optional[str] = Query(None, description="income | expense | transfer"),
    status: Optional[str] = Query(None, description="paid | pending | overdue"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    category_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="Full-text search on description"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    """
    List transactions for the current client.
    Supports filtering by type, status, date range, category, and text search.
    """
    schema = _fin_schema(tenant)

    conditions = ["1=1"]
    params: dict = {"limit": limit, "offset": offset}

    if type:
        conditions.append("type = :type")
        params["type"] = type
    if status:
        conditions.append("status = :status")
        params["status"] = status
    if start_date:
        conditions.append("date >= :start_date")
        params["start_date"] = start_date
    if end_date:
        conditions.append("date <= :end_date")
        params["end_date"] = end_date
    if category_id:
        conditions.append("category_id = :category_id::uuid")
        params["category_id"] = category_id
    if search:
        conditions.append("description ILIKE :search")
        params["search"] = f"%{search}%"

    where_clause = " AND ".join(conditions)

    sql = text(f"""
        SELECT id, type, amount, description, date, due_date, status,
               category_id, account_id, notes, tags, source_channel,
               ai_confidence, created_at, updated_at
        FROM "{schema}".transactions
        WHERE {where_clause}
        ORDER BY date DESC, created_at DESC
        LIMIT :limit OFFSET :offset
    """)

    count_sql = text(f"""
        SELECT COUNT(*) FROM "{schema}".transactions WHERE {where_clause}
    """)

    result = await db.execute(sql, params)
    rows = result.fetchall()

    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
    count_result = await db.execute(count_sql, count_params)
    total = count_result.scalar()

    transactions = [dict(row._mapping) for row in rows]

    return {
        "items": transactions,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("", status_code=201)
async def create_transaction(
    body: TransactionCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Create a new transaction manually."""
    schema = _fin_schema(tenant)
    tx_id = uuid.uuid4()

    sql = text(f"""
        INSERT INTO "{schema}".transactions
            (id, type, amount, description, date, due_date, status,
             category_id, account_id, notes, tags, source_channel)
        VALUES
            (:id, :type, :amount, :description, :date, :due_date, :status,
             :category_id::uuid, :account_id::uuid, :notes, :tags, 'web')
        RETURNING *
    """)

    try:
        result = await db.execute(sql, {
            "id": tx_id,
            "type": body.type,
            "amount": body.amount,
            "description": body.description,
            "date": body.date,
            "due_date": body.due_date,
            "status": body.status,
            "category_id": body.category_id,
            "account_id": body.account_id,
            "notes": body.notes,
            "tags": body.tags,
        })
        row = result.fetchone()
        await db.commit()
        return dict(row._mapping)
    except Exception as e:
        await db.rollback()
        logger.error(f"Create transaction error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create transaction")


@router.get("/{transaction_id}")
async def get_transaction(
    transaction_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get a single transaction by ID."""
    schema = _fin_schema(tenant)

    sql = text(f"""
        SELECT * FROM "{schema}".transactions WHERE id = :id::uuid
    """)
    result = await db.execute(sql, {"id": transaction_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return dict(row._mapping)


@router.put("/{transaction_id}")
async def update_transaction(
    transaction_id: str,
    body: TransactionUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Update a transaction."""
    schema = _fin_schema(tenant)

    # Only update provided fields
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clauses = []
    params = {"id": transaction_id}

    for field, value in updates.items():
        if field in ("category_id", "account_id"):
            set_clauses.append(f"{field} = :{field}::uuid")
        else:
            set_clauses.append(f"{field} = :{field}")
        params[field] = value

    set_clauses.append("updated_at = NOW()")
    set_sql = ", ".join(set_clauses)

    sql = text(f"""
        UPDATE "{schema}".transactions
        SET {set_sql}
        WHERE id = :id::uuid
        RETURNING *
    """)

    try:
        result = await db.execute(sql, params)
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Transaction not found")
        await db.commit()
        return dict(row._mapping)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Update transaction error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update transaction")


@router.delete("/{transaction_id}", status_code=204)
async def delete_transaction(
    transaction_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Delete a transaction."""
    schema = _fin_schema(tenant)

    sql = text(f"""
        DELETE FROM "{schema}".transactions WHERE id = :id::uuid RETURNING id
    """)
    result = await db.execute(sql, {"id": transaction_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Transaction not found")

    await db.commit()
    return None
