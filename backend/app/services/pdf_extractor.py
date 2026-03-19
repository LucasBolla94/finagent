"""
PDF text extractor for digital (selectable-text) PDFs.
Uses pdfplumber — best for bank statements with structured text.

Handles:
- Bradesco, Itaú, Nubank, Santander, Caixa, BB, Inter, C6
- Tries to extract: date, description, amount, type (debit/credit)
"""
import re
import logging
from typing import Optional
from dataclasses import dataclass, field
from datetime import date

import pdfplumber

logger = logging.getLogger(__name__)


@dataclass
class RawTransaction:
    """Raw transaction extracted from PDF before normalization."""
    date: Optional[date] = None
    description: str = ""
    amount: float = 0.0
    type: str = "expense"       # income | expense
    balance_after: Optional[float] = None
    raw_text: str = ""
    confidence: float = 1.0     # 0-1


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract all text from a digital PDF."""
    import io
    text_parts = []
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
    except Exception as e:
        logger.error(f"pdfplumber extraction error: {e}")
        return ""
    return "\n".join(text_parts)


def extract_tables_from_pdf(file_bytes: bytes) -> list[list]:
    """Extract tables from a digital PDF (better for structured bank statements)."""
    import io
    all_rows = []
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if row and any(cell for cell in row if cell):
                            all_rows.append([str(c or "").strip() for c in row])
    except Exception as e:
        logger.error(f"Table extraction error: {e}")
    return all_rows


def parse_amount(text: str) -> Optional[float]:
    """Parse Brazilian currency format: R$ 1.234,56 → 1234.56"""
    if not text:
        return None
    # Remove R$, spaces
    text = re.sub(r"R\$\s*", "", text).strip()
    # Remove thousands separator (.) and convert decimal (,) to (.)
    text = text.replace(".", "").replace(",", ".")
    # Remove any remaining non-numeric chars except - and .
    text = re.sub(r"[^\d.\-]", "", text)
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def parse_date_br(text: str) -> Optional[date]:
    """Parse Brazilian date formats: 12/03/2024, 12/03/24, 12-03-2024"""
    if not text:
        return None
    patterns = [
        r"(\d{2})[/\-](\d{2})[/\-](\d{4})",  # DD/MM/YYYY
        r"(\d{2})[/\-](\d{2})[/\-](\d{2})$",  # DD/MM/YY
    ]
    for pattern in patterns:
        m = re.search(pattern, text.strip())
        if m:
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if year < 100:
                year += 2000
            try:
                return date(year, month, day)
            except ValueError:
                continue
    return None


def detect_transaction_type(description: str, amount_str: str, context: str = "") -> str:
    """
    Detect if a transaction is income or expense.
    Uses description keywords + sign of amount + context markers.
    """
    desc_lower = description.lower()
    ctx_lower = context.lower()

    # Credit indicators
    credit_keywords = [
        "crédito", "credito", "credit", "depósito", "deposito",
        "ted recebido", "pix recebido", "recebimento", "salário", "salario",
        "reembolso", "cashback", "rendimento", "juros creditados",
        "transferência recebida", "venda", "restituição",
    ]
    # Debit indicators
    debit_keywords = [
        "débito", "debito", "debit", "pagamento", "saque", "compra",
        "transferência enviada", "pix enviado", "ted enviado", "fatura",
        "boleto", "tarifa", "anuidade", "cobrança",
    ]

    for kw in credit_keywords:
        if kw in desc_lower or kw in ctx_lower:
            return "income"
    for kw in debit_keywords:
        if kw in desc_lower or kw in ctx_lower:
            return "expense"

    # Check amount sign
    clean = amount_str.replace("R$", "").replace(" ", "")
    if clean.startswith("+"):
        return "income"
    if clean.startswith("-"):
        return "expense"

    # Default — most transactions are expenses
    return "expense"


def parse_transactions_from_text(text: str) -> list[RawTransaction]:
    """
    Generic parser — works when bank-specific parsers fail.
    Looks for lines with: date + description + amount.
    """
    transactions = []

    # Pattern: DD/MM/YYYY ... R$ 1.234,56 or just numbers
    line_pattern = re.compile(
        r"(\d{2}[/\-]\d{2}[/\-]\d{2,4})"   # date
        r"\s+(.+?)\s+"                        # description
        r"([\-\+]?\s*R?\$?\s*[\d.,]+)"       # amount
        r"(?:\s+([\-\+]?\s*R?\$?\s*[\d.,]+))?",  # optional balance
        re.IGNORECASE,
    )

    for line in text.split("\n"):
        line = line.strip()
        if not line or len(line) < 10:
            continue

        m = line_pattern.search(line)
        if not m:
            continue

        date_str = m.group(1)
        desc = m.group(2).strip()
        amount_str = m.group(3).strip()
        balance_str = m.group(4) if m.group(4) else None

        parsed_date = parse_date_br(date_str)
        parsed_amount = parse_amount(amount_str)

        if not parsed_date or parsed_amount is None or parsed_amount == 0:
            continue

        # Use absolute amount (we determine type separately)
        abs_amount = abs(parsed_amount)
        tx_type = detect_transaction_type(desc, amount_str)

        balance = parse_amount(balance_str) if balance_str else None

        transactions.append(RawTransaction(
            date=parsed_date,
            description=desc,
            amount=abs_amount,
            type=tx_type,
            balance_after=balance,
            raw_text=line,
            confidence=0.85,
        ))

    return transactions
