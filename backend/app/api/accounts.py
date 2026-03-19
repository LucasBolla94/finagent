"""
Bank accounts CRUD API.

GET    /api/v1/accounts        — list accounts with current balances
POST   /api/v1/accounts        — create new account
GET    /api/v1/accounts/{id}   — get one account
PUT    /api/v1/accounts/{id}   — update account
DELETE /api/v1/accounts/{id}   — deactivate account
"""
import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.models.tenant import Tenant
from app.middleware.auth import get_current_tenant

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Schemas ──────────────────────────────────────────────────────────────

class AccountCreate(BaseModel):
    name: str                          # "Nubank", "Bradesco Corrente", "Caixa"
    type: str = "checking"             # checking | savings | credit | investment | cash
    bank_name: Optional[str] = None
    currency: str = "BRL"
    initial_balance: float = 0.0


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    bank_name: Optional[str] = None
    is_active: Optional[bool] = None


# ─── Helpers ──────────────────────────────────────────────────────────────

def _fin_schema(tenant: Tenant) -> str:
    return f"tenant_{str(tenant.id).replace('-', '_')}_financial"


# ─── Endpoints ────────────────────────────────────────────────────────────

@router.get("")
async def list_accounts(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    List all accounts with their current balances.
    Also returns total balance across all active accounts.
    """
    schema = _fin_schema(tenant)

    sql = text(f"""
        SELECT
            a.id,
            a.name,
            a.type,
            a.bank_name,
            a.currency,
            a.initial_balance,
            a.current_balance,
            a.is_active,
            a.created_at,
            -- compute actual balance from transactions
            COALESCE(
                a.initial_balance +
                SUM(CASE
                    WHEN t.type = 'income' AND t.status = 'paid' THEN t.amount
                    WHEN t.type = 'expense' AND t.status = 'paid' THEN -t.amount
                    ELSE 0
                END),
                a.initial_balance
            ) AS computed_balance
        FROM "{schema}".accounts a
        LEFT JOIN "{schema}".transactions t ON t.account_id = a.id
        GROUP BY a.id
        ORDER BY a.created_at ASC
    """)

    result = await db.execute(sql)
    rows = result.fetchall()
    accounts = [dict(row._mapping) for row in rows]

    total_balance = sum(
        float(a.get("computed_balance", 0) or 0)
        for a in accounts
        if a.get("is_active") and a.get("currency") == "BRL"
    )

    return {"accounts": accounts, "total_balance": round(total_balance, 2)}


@router.post("", status_code=201)
async def create_account(
    body: AccountCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Create a new bank account / wallet."""
    schema = _fin_schema(tenant)
    account_id = uuid.uuid4()

    sql = text(f"""
        INSERT INTO "{schema}".accounts
            (id, name, type, bank_name, currency, initial_balance, current_balance)
        VALUES
            (:id, :name, :type, :bank_name, :currency, :initial_balance, :initial_balance)
        RETURNING *
    """)

    try:
        result = await db.execute(sql, {
            "id": account_id,
            "name": body.name,
            "type": body.type,
            "bank_name": body.bank_name,
            "currency": body.currency,
            "initial_balance": body.initial_balance,
        })
        row = result.fetchone()
        await db.commit()
        return dict(row._mapping)
    except Exception as e:
        await db.rollback()
        logger.error(f"Create account error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create account")


@router.get("/{account_id}")
async def get_account(
    account_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get a single account by ID."""
    schema = _fin_schema(tenant)

    sql = text(f"""
        SELECT * FROM "{schema}".accounts WHERE id = :id::uuid
    """)
    result = await db.execute(sql, {"id": account_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Account not found")

    return dict(row._mapping)


@router.put("/{account_id}")
async def update_account(
    account_id: str,
    body: AccountUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Update an account."""
    schema = _fin_schema(tenant)

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clauses = [f"{k} = :{k}" for k in updates.keys()]
    params = {"id": account_id, **updates}

    sql = text(f"""
        UPDATE "{schema}".accounts
        SET {', '.join(set_clauses)}
        WHERE id = :id::uuid
        RETURNING *
    """)

    try:
        result = await db.execute(sql, params)
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Account not found")
        await db.commit()
        return dict(row._mapping)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Update account error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update account")


@router.delete("/{account_id}", status_code=204)
async def delete_account(
    account_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate an account (soft delete — preserves transaction history)."""
    schema = _fin_schema(tenant)

    sql = text(f"""
        UPDATE "{schema}".accounts
        SET is_active = false
        WHERE id = :id::uuid
        RETURNING id
    """)
    result = await db.execute(sql, {"id": account_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Account not found")

    await db.commit()
    return None
