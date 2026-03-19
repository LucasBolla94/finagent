"""
Bank-specific parsers — identify which bank a document is from
and apply the right parsing strategy.

Each major Brazilian bank has a slightly different layout.
This module detects the bank and routes to the best parser.
"""
import re
import logging
from typing import Optional

from app.services.pdf_extractor import (
    RawTransaction,
    extract_text_from_pdf,
    extract_tables_from_pdf,
    parse_amount,
    parse_date_br,
    detect_transaction_type,
    parse_transactions_from_text,
)

logger = logging.getLogger(__name__)


# ─── Bank detection ───────────────────────────────────────────────────────

BANK_SIGNATURES = {
    "Nubank": [
        r"nubank", r"nu pagamentos", r"nu bank", r"roxinho"
    ],
    "Itaú": [
        r"itaú", r"itau", r"banco itau", r"banco itaú"
    ],
    "Bradesco": [
        r"bradesco", r"banco bradesco", r"bco\. bradesco"
    ],
    "Santander": [
        r"santander", r"banco santander"
    ],
    "Caixa Econômica Federal": [
        r"caixa econômica", r"caixa economica", r"cef", r"caixa federal"
    ],
    "Banco do Brasil": [
        r"banco do brasil", r"bco\. brasil", r"bb\.com\.br"
    ],
    "Inter": [
        r"banco inter", r"bancointer", r"conta digital inter"
    ],
    "C6 Bank": [
        r"c6 bank", r"c6bank", r"banco c6"
    ],
    "BTG Pactual": [
        r"btg pactual", r"btgpactual"
    ],
    "PicPay": [
        r"picpay", r"pic pay"
    ],
    "PagBank": [
        r"pagbank", r"pagseguro"
    ],
}


def detect_bank(text: str) -> Optional[str]:
    """
    Detect which bank issued this document.
    Returns bank name string or None if unknown.
    """
    text_lower = text.lower()
    for bank_name, patterns in BANK_SIGNATURES.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                return bank_name
    return None


# ─── Quality check ────────────────────────────────────────────────────────

def text_quality_score(text: str) -> float:
    """
    Estimate text quality (0-1).
    Low score = scanned/photo, needs Vision AI.
    High score = digital PDF, pdfplumber is enough.
    """
    if not text or len(text) < 50:
        return 0.0

    # Count recognizable patterns
    date_matches = len(re.findall(r"\d{2}/\d{2}/\d{4}", text))
    amount_matches = len(re.findall(r"[\d.,]{4,}", text))
    word_matches = len(re.findall(r"[a-zA-ZÀ-ÿ]{3,}", text))

    if word_matches == 0:
        return 0.0

    score = min(1.0, (date_matches * 0.3 + amount_matches * 0.3 + min(word_matches, 50) * 0.008))
    return round(score, 2)


# ─── Bank-specific parsers ────────────────────────────────────────────────

def parse_nubank(text: str, tables: list) -> list[RawTransaction]:
    """Nubank statement format."""
    transactions = []

    # Nubank uses table format with columns: Data | Descrição | Valor
    for row in tables:
        if len(row) < 3:
            continue
        date_str, desc = row[0], row[1]
        amount_str = row[2] if len(row) > 2 else ""

        parsed_date = parse_date_br(date_str)
        amount = parse_amount(amount_str)

        if not parsed_date or amount is None or amount == 0:
            continue

        abs_amount = abs(amount)
        tx_type = "income" if amount > 0 or "+" in amount_str else "expense"

        transactions.append(RawTransaction(
            date=parsed_date,
            description=desc,
            amount=abs_amount,
            type=tx_type,
            raw_text="|".join(row),
            confidence=0.95,
        ))

    # Fallback to text parsing
    if not transactions:
        transactions = parse_transactions_from_text(text)

    return transactions


def parse_itau(text: str, tables: list) -> list[RawTransaction]:
    """Itaú statement format."""
    transactions = []

    for row in tables:
        if len(row) < 3:
            continue
        # Itaú: Data | Histórico | Valor | Saldo
        date_str = row[0]
        desc = row[1] if len(row) > 1 else ""
        amount_str = row[2] if len(row) > 2 else ""
        balance_str = row[3] if len(row) > 3 else None

        parsed_date = parse_date_br(date_str)
        amount = parse_amount(amount_str)

        if not parsed_date or amount is None or amount == 0:
            continue

        abs_amount = abs(amount)
        tx_type = detect_transaction_type(desc, amount_str)
        balance = parse_amount(balance_str) if balance_str else None

        transactions.append(RawTransaction(
            date=parsed_date,
            description=desc,
            amount=abs_amount,
            type=tx_type,
            balance_after=balance,
            raw_text="|".join(row),
            confidence=0.93,
        ))

    if not transactions:
        transactions = parse_transactions_from_text(text)

    return transactions


# ─── Generic fallback ─────────────────────────────────────────────────────

def parse_generic(text: str, tables: list) -> list[RawTransaction]:
    """
    Generic parser — tries tables first, then text.
    Works for most banks not specifically handled above.
    """
    transactions = []

    # Try table parsing
    for row in tables:
        if len(row) < 2:
            continue

        # Find date in any column
        parsed_date = None
        date_col = -1
        for i, cell in enumerate(row):
            d = parse_date_br(cell)
            if d:
                parsed_date = d
                date_col = i
                break

        if not parsed_date:
            continue

        # Find amount — last numeric column
        amount = None
        amount_str = ""
        for cell in reversed(row):
            a = parse_amount(cell)
            if a is not None and a != 0:
                amount = abs(a)
                amount_str = cell
                break

        if not amount:
            continue

        # Description = everything between date and amount
        desc_parts = [row[i] for i in range(date_col + 1, len(row) - 1) if row[i]]
        desc = " ".join(desc_parts) if desc_parts else "Transação"

        tx_type = detect_transaction_type(desc, amount_str)

        transactions.append(RawTransaction(
            date=parsed_date,
            description=desc,
            amount=amount,
            type=tx_type,
            raw_text="|".join(row),
            confidence=0.80,
        ))

    if not transactions:
        transactions = parse_transactions_from_text(text)

    return transactions


# ─── Main router ──────────────────────────────────────────────────────────

BANK_PARSERS = {
    "Nubank": parse_nubank,
    "Itaú": parse_itau,
    # Others use generic for now (more parsers added in Phase 7)
}


def parse_pdf_document(file_bytes: bytes) -> tuple[list[RawTransaction], str, float]:
    """
    Main entry point for digital PDF parsing.
    Returns: (transactions, bank_name, quality_score)

    quality_score < 0.5 means Vision AI should be used instead.
    """
    text = extract_text_from_pdf(file_bytes)
    quality = text_quality_score(text)
    bank_name = detect_bank(text) or "Unknown"

    logger.info(f"PDF text quality: {quality:.2f}, bank: {bank_name}")

    if quality < 0.3:
        logger.info("Low quality text — Vision AI recommended")
        return [], bank_name, quality

    tables = extract_tables_from_pdf(file_bytes)

    # Use bank-specific parser if available
    parser_fn = BANK_PARSERS.get(bank_name, parse_generic)
    transactions = parser_fn(text, tables)

    logger.info(f"Extracted {len(transactions)} transactions via text parser")
    return transactions, bank_name, quality
