"""
Document processing orchestrator.

Coordinates: PDF extraction → Vision AI → Bank parser → Dedup → Import

Flow:
  1. Receive file bytes + content type
  2. Check document hash (layer 1 dedup)
  3. Try digital PDF extraction; if quality is low, use Vision AI
  4. For each transaction: check fingerprint (layer 2) + fuzzy (layer 3)
  5. Return preview: {to_import, duplicates, transactions}
  6. On confirmation: batch insert into tenant schema
"""
import uuid
import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.services.pdf_extractor import RawTransaction
from app.services.bank_parser import parse_pdf_document
from app.services.vision_extractor import extract_from_image_file, extract_from_pdf_with_vision
from app.services.dedup_service import (
    compute_document_hash,
    document_already_imported,
    compute_transaction_fingerprint,
    check_transaction_duplicate,
    DuplicateCheckResult,
)

logger = logging.getLogger(__name__)

# Threshold: if digital PDF quality is below this, use Vision AI
QUALITY_THRESHOLD = 0.45

# Minimum transactions to consider a valid extraction
MIN_TRANSACTIONS = 1


# ─── Result types ─────────────────────────────────────────────────────────

@dataclass
class TransactionPreview:
    """A single transaction ready for import, with duplicate info."""
    date: str
    description: str
    amount: float
    type: str
    fingerprint: str
    is_duplicate: bool = False
    duplicate_layer: Optional[str] = None
    duplicate_score: float = 0.0
    duplicate_existing_id: Optional[str] = None
    confidence: float = 1.0
    raw_text: str = ""


@dataclass
class DocumentAnalysis:
    """Result of analyzing a document before user confirms import."""
    document_hash: str
    bank_name: Optional[str]
    document_type: str
    extraction_method: str        # "text", "vision", "vision_pdf"
    already_imported: bool = False
    total_found: int = 0
    to_import: int = 0
    duplicates_count: int = 0
    transactions: list[TransactionPreview] = field(default_factory=list)
    error: Optional[str] = None


# ─── Main functions ────────────────────────────────────────────────────────

async def analyze_document(
    db: AsyncSession,
    tenant_id: str,
    file_bytes: bytes,
    content_type: str,
    filename: str = "",
) -> DocumentAnalysis:
    """
    Step 1: Analyze a document — extract transactions and check for duplicates.
    Returns a preview for the user to confirm before importing.
    """
    # Layer 1: document hash
    doc_hash = compute_document_hash(file_bytes)
    tenant_id_clean = tenant_id.replace("-", "_")
    fin_schema = f"tenant_{tenant_id_clean}_financial"

    already_imported = await document_already_imported(db, tenant_id, doc_hash)
    if already_imported:
        return DocumentAnalysis(
            document_hash=doc_hash,
            bank_name=None,
            document_type="unknown",
            extraction_method="none",
            already_imported=True,
            error="Este documento já foi importado anteriormente.",
        )

    # Extract transactions based on content type
    transactions_raw: list[RawTransaction] = []
    bank_name: Optional[str] = None
    document_type = "bank_statement"
    extraction_method = "text"

    is_image = content_type.startswith("image/")
    is_pdf = content_type == "application/pdf" or filename.lower().endswith(".pdf")

    if is_image:
        # Direct image (photo of receipt)
        transactions_raw, metadata = await extract_from_image_file(file_bytes, content_type)
        bank_name = metadata.get("bank_name")
        document_type = metadata.get("document_type", "receipt")
        extraction_method = "vision"

    elif is_pdf:
        # Try digital extraction first
        transactions_raw, bank_name, quality = parse_pdf_document(file_bytes)

        if quality < QUALITY_THRESHOLD or len(transactions_raw) < MIN_TRANSACTIONS:
            # Fallback to Vision AI
            logger.info(f"Using Vision AI fallback for PDF (quality={quality:.2f}, txs={len(transactions_raw)})")
            transactions_raw, metadata = await extract_from_pdf_with_vision(file_bytes)
            bank_name = metadata.get("bank_name") or bank_name
            document_type = metadata.get("document_type", "bank_statement")
            extraction_method = "vision_pdf"
        else:
            extraction_method = "text"
    else:
        return DocumentAnalysis(
            document_hash=doc_hash,
            bank_name=None,
            document_type="unknown",
            extraction_method="none",
            error=f"Formato não suportado: {content_type}",
        )

    if not transactions_raw:
        return DocumentAnalysis(
            document_hash=doc_hash,
            bank_name=bank_name,
            document_type=document_type,
            extraction_method=extraction_method,
            error="Nenhuma transação encontrada no documento.",
        )

    # Check each transaction for duplicates (layers 2 + 3)
    previews: list[TransactionPreview] = []
    for tx in transactions_raw:
        if not tx.date:
            continue
        fingerprint = compute_transaction_fingerprint(tx)
        dup_result: DuplicateCheckResult = await check_transaction_duplicate(
            db, fin_schema, tx, fingerprint
        )
        previews.append(TransactionPreview(
            date=tx.date.isoformat(),
            description=tx.description,
            amount=tx.amount,
            type=tx.type,
            fingerprint=fingerprint,
            is_duplicate=dup_result.is_duplicate,
            duplicate_layer=dup_result.layer,
            duplicate_score=dup_result.score,
            duplicate_existing_id=dup_result.existing_id,
            confidence=tx.confidence,
            raw_text=tx.raw_text,
        ))

    to_import = [p for p in previews if not p.is_duplicate]
    duplicates = [p for p in previews if p.is_duplicate]

    return DocumentAnalysis(
        document_hash=doc_hash,
        bank_name=bank_name,
        document_type=document_type,
        extraction_method=extraction_method,
        total_found=len(previews),
        to_import=len(to_import),
        duplicates_count=len(duplicates),
        transactions=previews,
    )


async def confirm_import(
    db: AsyncSession,
    tenant_id: str,
    analysis: DocumentAnalysis,
    account_id: Optional[str] = None,
    skip_duplicates: bool = True,
    filename: str = "",
) -> dict:
    """
    Step 2: User confirmed — insert all non-duplicate transactions in batch.
    Also records the document in imported_documents table.
    """
    tenant_id_clean = tenant_id.replace("-", "_")
    fin_schema = f"tenant_{tenant_id_clean}_financial"

    transactions_to_insert = [
        tx for tx in analysis.transactions
        if not tx.is_duplicate or not skip_duplicates
    ]

    if not transactions_to_insert:
        return {
            "imported": 0,
            "skipped": len(analysis.transactions),
            "message": "Todas as transações eram duplicatas. Nada foi importado.",
        }

    imported_count = 0
    errors = []

    for tx in transactions_to_insert:
        try:
            await db.execute(
                text(f"""
                    INSERT INTO "{fin_schema}".transactions
                        (id, type, amount, description, date, status,
                         account_id, document_hash, ai_confidence,
                         raw_message, source_channel)
                    VALUES
                        (uuid_generate_v4(), :type, :amount, :description, :date::date,
                         'paid', :account_id::uuid, :fingerprint, :confidence,
                         :raw_text, 'import')
                    ON CONFLICT DO NOTHING
                """),
                {
                    "type": tx.type,
                    "amount": tx.amount,
                    "description": tx.description,
                    "date": tx.date,
                    "account_id": account_id,
                    "fingerprint": tx.fingerprint,
                    "confidence": tx.confidence,
                    "raw_text": tx.raw_text[:500] if tx.raw_text else None,
                },
            )
            imported_count += 1
        except Exception as e:
            logger.error(f"Failed to insert transaction: {e}")
            errors.append(str(e))

    # Record the document as imported
    try:
        await db.execute(
            text("""
                INSERT INTO imported_documents
                    (id, tenant_id, document_hash, filename, document_type,
                     bank_name, transactions_imported, duplicates_found)
                VALUES
                    (uuid_generate_v4(), :tenant_id::uuid, :doc_hash, :filename,
                     :doc_type, :bank_name, :imported, :dups)
                ON CONFLICT (document_hash) DO NOTHING
            """),
            {
                "tenant_id": tenant_id,
                "doc_hash": analysis.document_hash,
                "filename": filename,
                "doc_type": analysis.document_type,
                "bank_name": analysis.bank_name,
                "imported": imported_count,
                "dups": analysis.duplicates_count,
            },
        )
    except Exception as e:
        logger.warning(f"Failed to record imported_documents: {e}")

    await db.commit()

    return {
        "imported": imported_count,
        "skipped": analysis.duplicates_count,
        "errors": len(errors),
        "message": f"✅ {imported_count} transações importadas. {analysis.duplicates_count} duplicatas ignoradas.",
    }
