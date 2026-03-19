"""
Reports API.

GET /api/v1/reports                — list saved reports
GET /api/v1/reports/summary        — quick financial summary (current month)
GET /api/v1/reports/cash-flow      — cash flow by period
GET /api/v1/reports/by-category    — breakdown by category
POST /api/v1/reports/generate      — generate and save a new report (AI)
"""
import logging
from typing import Optional
from datetime import date, timedelta
from calendar import monthrange

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.models.tenant import Tenant
from app.middleware.auth import get_current_tenant

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Schemas ──────────────────────────────────────────────────────────────

class ReportGenerateRequest(BaseModel):
    type: str           # dre | cash_flow | by_category | custom
    period_start: date
    period_end: date
    notes: Optional[str] = None


# ─── Helpers ──────────────────────────────────────────────────────────────

def _fin_schema(tenant: Tenant) -> str:
    return f"tenant_{str(tenant.id).replace('-', '_')}_financial"


def _current_month_range() -> tuple[date, date]:
    today = date.today()
    first_day = today.replace(day=1)
    last_day = today.replace(day=monthrange(today.year, today.month)[1])
    return first_day, last_day


# ─── Endpoints ────────────────────────────────────────────────────────────

@router.get("/summary")
async def financial_summary(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2020, le=2100),
):
    """
    Quick financial summary for a given month.
    Returns: total income, total expenses, net result, top categories.
    Defaults to current month if not specified.
    """
    schema = _fin_schema(tenant)
    today = date.today()
    m = month or today.month
    y = year or today.year

    first_day = date(y, m, 1)
    last_day = date(y, m, monthrange(y, m)[1])

    sql = text(f"""
        SELECT
            SUM(CASE WHEN type = 'income' AND status = 'paid' THEN amount ELSE 0 END)  AS total_income,
            SUM(CASE WHEN type = 'expense' AND status = 'paid' THEN amount ELSE 0 END) AS total_expenses,
            SUM(CASE WHEN type = 'income' AND status = 'pending' THEN amount ELSE 0 END) AS pending_income,
            SUM(CASE WHEN type = 'expense' AND status = 'pending' THEN amount ELSE 0 END) AS pending_expenses,
            COUNT(*) FILTER (WHERE status = 'paid') AS paid_count,
            COUNT(*) FILTER (WHERE status = 'pending') AS pending_count
        FROM "{schema}".transactions
        WHERE date BETWEEN :start AND :end
    """)

    result = await db.execute(sql, {"start": first_day, "end": last_day})
    row = result.fetchone()
    data = dict(row._mapping)

    income = float(data.get("total_income") or 0)
    expenses = float(data.get("total_expenses") or 0)

    # Top expense categories this month
    cat_sql = text(f"""
        SELECT
            COALESCE(c.name, 'Sem categoria') AS category,
            SUM(t.amount) AS total,
            COUNT(*) AS count
        FROM "{schema}".transactions t
        LEFT JOIN "{schema}".categories c ON c.id = t.category_id
        WHERE t.date BETWEEN :start AND :end
          AND t.type = 'expense'
          AND t.status = 'paid'
        GROUP BY c.name
        ORDER BY total DESC
        LIMIT 5
    """)
    cat_result = await db.execute(cat_sql, {"start": first_day, "end": last_day})
    top_categories = [dict(r._mapping) for r in cat_result.fetchall()]

    return {
        "period": {"month": m, "year": y, "start": first_day, "end": last_day},
        "income": round(income, 2),
        "expenses": round(expenses, 2),
        "net": round(income - expenses, 2),
        "pending_income": round(float(data.get("pending_income") or 0), 2),
        "pending_expenses": round(float(data.get("pending_expenses") or 0), 2),
        "transaction_count": {
            "paid": data.get("paid_count") or 0,
            "pending": data.get("pending_count") or 0,
        },
        "top_expense_categories": top_categories,
    }


@router.get("/cash-flow")
async def cash_flow(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
    months: int = Query(6, ge=1, le=24, description="How many months to look back"),
):
    """
    Cash flow by month for the last N months.
    Returns income, expenses and net per month — great for charts.
    """
    schema = _fin_schema(tenant)
    today = date.today()
    start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)

    # Go back N months
    for _ in range(months - 1):
        start = (start - timedelta(days=1)).replace(day=1)

    sql = text(f"""
        SELECT
            DATE_TRUNC('month', date)::date AS month,
            SUM(CASE WHEN type = 'income' AND status = 'paid' THEN amount ELSE 0 END)  AS income,
            SUM(CASE WHEN type = 'expense' AND status = 'paid' THEN amount ELSE 0 END) AS expenses
        FROM "{schema}".transactions
        WHERE date >= :start
        GROUP BY DATE_TRUNC('month', date)
        ORDER BY month ASC
    """)

    result = await db.execute(sql, {"start": start})
    rows = result.fetchall()

    flow = []
    for row in rows:
        d = dict(row._mapping)
        income = float(d.get("income") or 0)
        expenses = float(d.get("expenses") or 0)
        flow.append({
            "month": d["month"],
            "income": round(income, 2),
            "expenses": round(expenses, 2),
            "net": round(income - expenses, 2),
        })

    return {"cash_flow": flow, "months": months}


@router.get("/by-category")
async def by_category(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    type: str = Query("expense", description="income | expense"),
):
    """Breakdown of transactions by category for a period."""
    schema = _fin_schema(tenant)
    first, last = _current_month_range()
    start = start_date or first
    end = end_date or last

    sql = text(f"""
        SELECT
            COALESCE(c.name, 'Sem categoria') AS category,
            COALESCE(c.icon, '📦') AS icon,
            COALESCE(c.color, '#888888') AS color,
            SUM(t.amount) AS total,
            COUNT(*) AS count,
            ROUND(
                100.0 * SUM(t.amount) /
                NULLIF(SUM(SUM(t.amount)) OVER (), 0),
            2) AS percentage
        FROM "{schema}".transactions t
        LEFT JOIN "{schema}".categories c ON c.id = t.category_id
        WHERE t.date BETWEEN :start AND :end
          AND t.type = :type
          AND t.status = 'paid'
        GROUP BY c.name, c.icon, c.color
        ORDER BY total DESC
    """)

    result = await db.execute(sql, {"start": start, "end": end, "type": type})
    rows = result.fetchall()

    return {
        "period": {"start": start, "end": end},
        "type": type,
        "categories": [dict(r._mapping) for r in rows],
    }


@router.get("")
async def list_reports(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, le=100),
):
    """List previously generated reports."""
    schema = _fin_schema(tenant)

    sql = text(f"""
        SELECT id, type, period_start, period_end, generated_by, created_at
        FROM "{schema}".reports
        ORDER BY created_at DESC
        LIMIT :limit
    """)
    result = await db.execute(sql, {"limit": limit})
    rows = result.fetchall()

    return {"reports": [dict(r._mapping) for r in rows]}
