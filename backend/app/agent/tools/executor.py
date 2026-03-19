"""
Tool Executor — Runs the actual database operations when the AI calls a tool.
"""

import logging
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)


async def execute_tool(
    tool_name: str,
    tool_args: dict,
    tenant_id: str,
    db: AsyncSession,
) -> dict:
    """Routes tool calls to the correct handler."""
    schema = f"tenant_{tenant_id.replace('-', '_')}_financial"

    handlers = {
        "create_transaction": _create_transaction,
        "get_balance": _get_balance,
        "list_transactions": _list_transactions,
        "generate_report": _generate_report,
        "search_history": _search_history,
        "forecast_balance": _forecast_balance,
        "create_alert": _create_alert,
        "update_transaction": _update_transaction,
        "get_client_context": _get_client_context,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return {"error": f"Tool '{tool_name}' not found"}

    try:
        return await handler(tool_args, schema, db, tenant_id)
    except Exception as e:
        logger.error(f"Tool '{tool_name}' failed: {e}")
        return {"error": str(e)}


async def _create_transaction(args: dict, schema: str, db: AsyncSession, tenant_id: str) -> dict:
    tx_date = args.get("date") or date.today().isoformat()
    tx_type = args["transaction_type"]
    amount = Decimal(str(args["amount"]))
    description = args["description"]
    category_name = args.get("category_name", "Outros")
    account_name = args.get("account_name")
    status = args.get("status", "paid")
    notes = args.get("notes")

    # Find or create category
    cat_result = await db.execute(
        text(f'SELECT id FROM "{schema}".categories WHERE LOWER(name) = LOWER(:name) LIMIT 1'),
        {"name": category_name}
    )
    cat_row = cat_result.fetchone()
    if not cat_row:
        cat_insert = await db.execute(
            text(f'INSERT INTO "{schema}".categories (name, type) VALUES (:name, :type) RETURNING id'),
            {"name": category_name, "type": tx_type}
        )
        category_id = cat_insert.fetchone().id
    else:
        category_id = cat_row.id

    # Find account
    account_id = None
    if account_name:
        acc_result = await db.execute(
            text(f'SELECT id FROM "{schema}".accounts WHERE LOWER(name) = LOWER(:name) LIMIT 1'),
            {"name": account_name}
        )
        acc_row = acc_result.fetchone()
        if acc_row:
            account_id = acc_row.id

    if not account_id:
        # Use first/main account
        acc_result = await db.execute(
            text(f'SELECT id FROM "{schema}".accounts WHERE is_active = true ORDER BY created_at ASC LIMIT 1')
        )
        acc_row = acc_result.fetchone()
        if acc_row:
            account_id = acc_row.id

    # Duplicate detection (multi-layer)
    duplicate = await _check_duplicate(schema, db, tx_date, amount, description, account_id)
    if duplicate:
        return {
            "status": "duplicate_detected",
            "message": f"Encontrei uma transação similar em {duplicate['date']}: {duplicate['description']} R${duplicate['amount']}. É a mesma?",
            "duplicate": duplicate,
        }

    # Insert transaction
    result = await db.execute(
        text(f"""
            INSERT INTO "{schema}".transactions
            (account_id, category_id, type, amount, description, notes, date, status, source_channel)
            VALUES (:account_id, :category_id, :type, :amount, :description, :notes, :date, :status, 'ai_agent')
            RETURNING id, amount, description, date
        """),
        {
            "account_id": account_id,
            "category_id": category_id,
            "type": tx_type,
            "amount": amount,
            "description": description,
            "notes": notes,
            "date": tx_date,
            "status": status,
        }
    )
    row = result.fetchone()

    # Update account balance
    if account_id and status == "paid":
        balance_delta = amount if tx_type == "income" else -amount
        await db.execute(
            text(f'UPDATE "{schema}".accounts SET current_balance = current_balance + :delta WHERE id = :id'),
            {"delta": balance_delta, "id": account_id}
        )

    await db.commit()

    # Get new balance
    new_balance = await _get_account_balance(schema, db, account_id)

    return {
        "status": "created",
        "transaction_id": str(row.id),
        "amount": float(row.amount),
        "description": row.description,
        "date": str(row.date),
        "new_balance": new_balance,
    }


async def _check_duplicate(
    schema: str, db: AsyncSession, tx_date: str, amount: Decimal,
    description: str, account_id: Any
) -> dict | None:
    """Multi-layer duplicate detection."""
    try:
        tx_date_obj = datetime.strptime(tx_date, "%Y-%m-%d").date()
    except Exception:
        return None

    # Check exact match (±1 day, exact amount, similar description)
    result = await db.execute(
        text(f"""
            SELECT id, description, amount, date,
                similarity(LOWER(description), LOWER(:description)) as sim
            FROM "{schema}".transactions
            WHERE ABS(amount - :amount) < 0.01
              AND date BETWEEN :date_from AND :date_to
              AND similarity(LOWER(description), LOWER(:description)) > 0.5
            ORDER BY sim DESC
            LIMIT 1
        """),
        {
            "amount": float(amount),
            "description": description,
            "date_from": (tx_date_obj - timedelta(days=1)).isoformat(),
            "date_to": (tx_date_obj + timedelta(days=1)).isoformat(),
        }
    )
    row = result.fetchone()
    if row:
        return {
            "id": str(row.id),
            "description": row.description,
            "amount": float(row.amount),
            "date": str(row.date),
            "similarity": float(row.sim),
        }
    return None


async def _get_balance(args: dict, schema: str, db: AsyncSession, tenant_id: str) -> dict:
    account_name = args.get("account_name")

    if account_name:
        result = await db.execute(
            text(f'SELECT name, current_balance, currency FROM "{schema}".accounts WHERE LOWER(name) = LOWER(:name) AND is_active = true'),
            {"name": account_name}
        )
        row = result.fetchone()
        if not row:
            return {"error": f"Conta '{account_name}' não encontrada"}
        return {"account": row.name, "balance": float(row.current_balance), "currency": row.currency}

    result = await db.execute(
        text(f'SELECT name, current_balance, currency FROM "{schema}".accounts WHERE is_active = true ORDER BY created_at')
    )
    rows = result.fetchall()
    accounts = [{"account": r.name, "balance": float(r.current_balance), "currency": r.currency} for r in rows]
    total = sum(a["balance"] for a in accounts)
    return {"accounts": accounts, "total_balance": total}


async def _list_transactions(args: dict, schema: str, db: AsyncSession, tenant_id: str) -> dict:
    conditions = ["1=1"]
    params: dict = {}

    today = date.today()

    if args.get("start_date"):
        conditions.append("t.date >= :start_date")
        params["start_date"] = args["start_date"]
    else:
        conditions.append("t.date >= :start_date")
        params["start_date"] = today.replace(day=1).isoformat()

    if args.get("end_date"):
        conditions.append("t.date <= :end_date")
        params["end_date"] = args["end_date"]

    if args.get("transaction_type") and args["transaction_type"] != "all":
        conditions.append("t.type = :tx_type")
        params["tx_type"] = args["transaction_type"]

    if args.get("category_name"):
        conditions.append("LOWER(c.name) LIKE LOWER(:category)")
        params["category"] = f"%{args['category_name']}%"

    if args.get("status") and args["status"] != "all":
        conditions.append("t.status = :status")
        params["status"] = args["status"]

    where = " AND ".join(conditions)
    limit = min(args.get("limit", 10), 50)

    result = await db.execute(
        text(f"""
            SELECT t.id, t.type, t.amount, t.description, t.date, t.status,
                   c.name as category, a.name as account
            FROM "{schema}".transactions t
            LEFT JOIN "{schema}".categories c ON t.category_id = c.id
            LEFT JOIN "{schema}".accounts a ON t.account_id = a.id
            WHERE {where}
            ORDER BY t.date DESC, t.created_at DESC
            LIMIT {limit}
        """),
        params
    )
    rows = result.fetchall()
    transactions = [
        {
            "id": str(r.id), "type": r.type, "amount": float(r.amount),
            "description": r.description, "date": str(r.date),
            "status": r.status, "category": r.category, "account": r.account,
        }
        for r in rows
    ]

    total_income = sum(t["amount"] for t in transactions if t["type"] == "income")
    total_expense = sum(t["amount"] for t in transactions if t["type"] == "expense")

    return {
        "transactions": transactions,
        "count": len(transactions),
        "total_income": total_income,
        "total_expense": total_expense,
        "net": total_income - total_expense,
    }


async def _generate_report(args: dict, schema: str, db: AsyncSession, tenant_id: str) -> dict:
    report_type = args["report_type"]
    today = date.today()
    start_date = args.get("start_date", today.replace(day=1).isoformat())
    end_date = args.get("end_date", today.isoformat())

    if report_type == "monthly_summary":
        result = await db.execute(
            text(f"""
                SELECT
                    SUM(CASE WHEN type='income' AND status='paid' THEN amount ELSE 0 END) as total_income,
                    SUM(CASE WHEN type='expense' AND status='paid' THEN amount ELSE 0 END) as total_expense,
                    SUM(CASE WHEN type='expense' AND status='pending' THEN amount ELSE 0 END) as pending_expenses,
                    COUNT(*) as transaction_count
                FROM "{schema}".transactions
                WHERE date BETWEEN :start AND :end
            """),
            {"start": start_date, "end": end_date}
        )
        row = result.fetchone()
        return {
            "period": f"{start_date} to {end_date}",
            "total_income": float(row.total_income or 0),
            "total_expense": float(row.total_expense or 0),
            "net_result": float((row.total_income or 0) - (row.total_expense or 0)),
            "pending_expenses": float(row.pending_expenses or 0),
            "transaction_count": row.transaction_count,
        }

    elif report_type == "category_breakdown":
        result = await db.execute(
            text(f"""
                SELECT c.name as category, t.type,
                       SUM(t.amount) as total, COUNT(*) as count
                FROM "{schema}".transactions t
                LEFT JOIN "{schema}".categories c ON t.category_id = c.id
                WHERE t.date BETWEEN :start AND :end AND t.status = 'paid'
                GROUP BY c.name, t.type
                ORDER BY total DESC
            """),
            {"start": start_date, "end": end_date}
        )
        rows = result.fetchall()
        return {
            "period": f"{start_date} to {end_date}",
            "breakdown": [
                {"category": r.category, "type": r.type, "total": float(r.total), "count": r.count}
                for r in rows
            ]
        }

    elif report_type == "pending_bills":
        result = await db.execute(
            text(f"""
                SELECT description, amount, due_date, category_id
                FROM "{schema}".transactions
                WHERE status = 'pending' AND type = 'expense'
                ORDER BY due_date ASC NULLS LAST
                LIMIT 20
            """)
        )
        rows = result.fetchall()
        return {
            "pending_bills": [
                {"description": r.description, "amount": float(r.amount), "due_date": str(r.due_date or "")}
                for r in rows
            ],
            "total_pending": sum(float(r.amount) for r in rows),
        }

    return {"error": f"Report type '{report_type}' not implemented yet"}


async def _search_history(args: dict, schema: str, db: AsyncSession, tenant_id: str) -> dict:
    """Fallback text search when embeddings unavailable."""
    query = args.get("query", "")
    result = await db.execute(
        text(f"""
            SELECT description, amount, date, type, status
            FROM "{schema}".transactions
            WHERE description ILIKE :query
            ORDER BY date DESC
            LIMIT :limit
        """),
        {"query": f"%{query}%", "limit": args.get("limit", 5)}
    )
    rows = result.fetchall()
    return {
        "results": [
            {"description": r.description, "amount": float(r.amount),
             "date": str(r.date), "type": r.type, "status": r.status}
            for r in rows
        ]
    }


async def _forecast_balance(args: dict, schema: str, db: AsyncSession, tenant_id: str) -> dict:
    days_ahead = args.get("days_ahead", 30)

    balance_result = await db.execute(
        text(f'SELECT SUM(current_balance) as total FROM "{schema}".accounts WHERE is_active = true')
    )
    current_balance = float(balance_result.fetchone().total or 0)

    # Pending bills that will reduce balance
    pending_result = await db.execute(
        text(f"""
            SELECT SUM(amount) as total
            FROM "{schema}".transactions
            WHERE status = 'pending' AND type = 'expense'
              AND (due_date IS NULL OR due_date <= NOW() + :days * INTERVAL '1 day')
        """),
        {"days": days_ahead}
    )
    pending_expenses = float(pending_result.fetchone().total or 0)

    # Average monthly income
    income_result = await db.execute(
        text(f"""
            SELECT AVG(monthly_income) as avg_income FROM (
                SELECT DATE_TRUNC('month', date) as month, SUM(amount) as monthly_income
                FROM "{schema}".transactions
                WHERE type = 'income' AND status = 'paid'
                  AND date >= NOW() - INTERVAL '3 months'
                GROUP BY month
            ) monthly
        """)
    )
    avg_monthly_income = float(income_result.fetchone().avg_income or 0)
    projected_income = (avg_monthly_income / 30) * days_ahead

    projected_balance = current_balance + projected_income - pending_expenses

    return {
        "current_balance": current_balance,
        "pending_expenses": pending_expenses,
        "projected_income": projected_income,
        "projected_balance": projected_balance,
        "days_ahead": days_ahead,
        "confidence": "medium",
    }


async def _create_alert(args: dict, schema: str, db: AsyncSession, tenant_id: str) -> dict:
    await db.execute(
        text(f"""
            INSERT INTO "{schema}".alerts (type, name, condition, message, is_active, created_at)
            VALUES (:type, :name, :condition, :message, true, NOW())
        """),
        {
            "type": args["alert_type"],
            "name": args["name"],
            "condition": f'{{"threshold": {args.get("threshold", 0)}}}',
            "message": args["message"],
        }
    )
    await db.commit()
    return {"status": "created", "name": args["name"]}


async def _update_transaction(args: dict, schema: str, db: AsyncSession, tenant_id: str) -> dict:
    updates = []
    params = {"id": args["transaction_id"]}
    for field in ["amount", "description", "date", "status", "notes"]:
        if args.get(field) is not None:
            updates.append(f"{field} = :{field}")
            params[field] = args[field]
    if not updates:
        return {"error": "No fields to update"}
    await db.execute(
        text(f'UPDATE "{schema}".transactions SET {", ".join(updates)} WHERE id = :id'),
        params
    )
    await db.commit()
    return {"status": "updated", "transaction_id": args["transaction_id"]}


async def _get_client_context(args: dict, schema: str, db: AsyncSession, tenant_id: str) -> dict:
    balance = await _get_balance({}, schema, db, tenant_id)
    summary = await _generate_report({"report_type": "monthly_summary"}, schema, db, tenant_id)
    pending = await _generate_report({"report_type": "pending_bills"}, schema, db, tenant_id)
    return {
        "balance_summary": balance,
        "current_month": summary,
        "pending_bills": pending.get("pending_bills", [])[:5],
    }


async def _get_account_balance(schema: str, db: AsyncSession, account_id: Any) -> float:
    if not account_id:
        return 0.0
    result = await db.execute(
        text(f'SELECT current_balance FROM "{schema}".accounts WHERE id = :id'),
        {"id": account_id}
    )
    row = result.fetchone()
    return float(row.current_balance) if row else 0.0
