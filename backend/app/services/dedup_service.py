"""
4-layer duplicate detection service.

Layer 1 — Document hash (SHA-256 of entire file)
  → Prevents importing the SAME FILE twice

Layer 2 — Transaction fingerprint hash
  → Prevents importing the SAME TRANSACTION twice
  → Hash = SHA256(date + amount_cents + description_normalized)

Layer 3 — Fuzzy score
  → Catches near-duplicate transactions (same day ±3, amount ±5%, similar desc)
  → Score 0-100, flag if ≥ 85

Layer 4 — Semantic similarity (pgvector)
  → Catches transactions that mean the same thing described differently
  → Only runs if layers 1-3 pass
"""
import hashlib
import re
import logging
from dataclasses import dataclass
from typing import Optional
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.services.pdf_extractor import RawTransaction

logger = logging.getLogger(__name__)


# ─── Layer 1: Document hash ───────────────────────────────────────────────

def compute_document_hash(file_bytes: bytes) -> str:
    """SHA-256 hash of the entire file. Identical file = same hash."""
    return hashlib.sha256(file_bytes).hexdigest()


async def document_already_imported(db: AsyncSession, tenant_id: str, doc_hash: str) -> bool:
    """Check if this exact file was already imported."""
    result = await db.execute(
        text("""
            SELECT 1 FROM imported_documents
            WHERE tenant_id = :tenant_id::uuid
              AND document_hash = :doc_hash
            LIMIT 1
        """),
        {"tenant_id": tenant_id, "doc_hash": doc_hash},
    )
    return result.fetchone() is not None


# ─── Layer 2: Transaction fingerprint ────────────────────────────────────

def normalize_description(desc: str) -> str:
    """Normalize description for fingerprinting — remove noise."""
    if not desc:
        return ""
    # lowercase, remove extra spaces, numbers in middle of words
    desc = desc.lower().strip()
    desc = re.sub(r"\s+", " ", desc)
    # Remove common dynamic parts (transaction IDs, timestamps)
    desc = re.sub(r"\b\d{6,}\b", "", desc)  # long numbers
    desc = re.sub(r"\d{2}:\d{2}(:\d{2})?", "", desc)  # time
    return desc.strip()


def compute_transaction_fingerprint(tx: RawTransaction) -> str:
    """
    Hash that uniquely identifies a transaction.
    Combines: date + amount_cents + normalized_description
    """
    amount_cents = int(round(tx.amount * 100))
    norm_desc = normalize_description(tx.description)
    key = f"{tx.date.isoformat()}|{amount_cents}|{norm_desc}"
    return hashlib.sha256(key.encode()).hexdigest()


async def fingerprint_exists(db: AsyncSession, schema: str, fingerprint: str) -> bool:
    """Check if this exact transaction fingerprint exists."""
    result = await db.execute(
        text(f"""
            SELECT 1 FROM "{schema}".transactions
            WHERE document_hash = :fingerprint
            LIMIT 1
        """),
        {"fingerprint": fingerprint},
    )
    return result.fetchone() is not None


# ─── Layer 3: Fuzzy matching ──────────────────────────────────────────────

def fuzzy_score(tx: RawTransaction, existing: dict) -> float:
    """
    Calculate a fuzzy similarity score (0-100) between a new transaction
    and an existing one from the database.
    """
    score = 0.0

    # Date proximity (max 30 points)
    try:
        existing_date = existing["date"]
        if isinstance(existing_date, str):
            from datetime import datetime
            existing_date = datetime.fromisoformat(existing_date).date()
        days_diff = abs((tx.date - existing_date).days)
        if days_diff == 0:
            score += 30
        elif days_diff <= 1:
            score += 20
        elif days_diff <= 3:
            score += 10
    except Exception:
        pass

    # Amount similarity (max 40 points)
    try:
        ex_amount = float(existing.get("amount", 0))
        if ex_amount > 0 and tx.amount > 0:
            ratio = min(tx.amount, ex_amount) / max(tx.amount, ex_amount)
            if ratio >= 0.99:
                score += 40
            elif ratio >= 0.95:
                score += 30
            elif ratio >= 0.90:
                score += 15
    except Exception:
        pass

    # Description similarity (max 30 points)
    try:
        norm_new = normalize_description(tx.description)
        norm_existing = normalize_description(existing.get("description", ""))
        if norm_new and norm_existing:
            # Simple word overlap
            words_new = set(norm_new.split())
            words_existing = set(norm_existing.split())
            if words_new and words_existing:
                overlap = len(words_new & words_existing) / max(len(words_new), len(words_existing))
                score += overlap * 30
    except Exception:
        pass

    return round(score, 2)


async def find_fuzzy_duplicates(
    db: AsyncSession,
    schema: str,
    tx: RawTransaction,
    days_window: int = 5,
    score_threshold: float = 75.0,
) -> list[dict]:
    """
    Find potential fuzzy duplicates in the database.
    Returns list of existing transactions that are suspiciously similar.
    """
    if not tx.date:
        return []

    start_date = tx.date - timedelta(days=days_window)
    end_date = tx.date + timedelta(days=days_window)
    min_amount = tx.amount * 0.88
    max_amount = tx.amount * 1.12

    result = await db.execute(
        text(f"""
            SELECT id, date, amount, description, type
            FROM "{schema}".transactions
            WHERE date BETWEEN :start AND :end
              AND amount BETWEEN :min_amt AND :max_amt
            LIMIT 20
        """),
        {
            "start": start_date,
            "end": end_date,
            "min_amt": min_amount,
            "max_amt": max_amount,
        },
    )

    candidates = [dict(row._mapping) for row in result.fetchall()]
    duplicates = []

    for candidate in candidates:
        score = fuzzy_score(tx, candidate)
        if score >= score_threshold:
            candidate["_duplicate_score"] = score
            duplicates.append(candidate)

    return duplicates


# ─── Main dedup check ─────────────────────────────────────────────────────

@dataclass
class DuplicateCheckResult:
    is_duplicate: bool
    layer: Optional[str]        # Which layer caught it: "fingerprint", "fuzzy"
    score: float = 0.0          # Fuzzy score (0-100)
    existing_id: Optional[str] = None


async def check_transaction_duplicate(
    db: AsyncSession,
    schema: str,
    tx: RawTransaction,
    fingerprint: str,
) -> DuplicateCheckResult:
    """
    Run layers 2 + 3 on a single transaction.
    Returns whether it's a duplicate and which layer caught it.
    """
    # Layer 2: fingerprint check
    if await fingerprint_exists(db, schema, fingerprint):
        return DuplicateCheckResult(is_duplicate=True, layer="fingerprint", score=100.0)

    # Layer 3: fuzzy check
    fuzzy_dups = await find_fuzzy_duplicates(db, schema, tx)
    if fuzzy_dups:
        best = max(fuzzy_dups, key=lambda x: x["_duplicate_score"])
        return DuplicateCheckResult(
            is_duplicate=True,
            layer="fuzzy",
            score=best["_duplicate_score"],
            existing_id=str(best["id"]),
        )

    return DuplicateCheckResult(is_duplicate=False, layer=None)
