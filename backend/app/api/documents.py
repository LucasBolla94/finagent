"""
Document upload and import API.

POST /api/v1/documents/upload    — upload file → returns analysis (preview)
POST /api/v1/documents/confirm   — confirm import after reviewing preview
GET  /api/v1/documents           — list previously imported documents
"""
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.models.tenant import Tenant
from app.middleware.auth import get_current_tenant
from app.services.document_processor import (
    analyze_document,
    confirm_import,
    DocumentAnalysis,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Max file size: 20MB
MAX_FILE_SIZE = 20 * 1024 * 1024

# Supported content types
SUPPORTED_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/heic",
}


# ─── In-memory pending imports (with TTL) ──────────────────────────────────
# Stores analysis results temporarily between /upload and /confirm.
# Uses a simple dict with timestamps. TTL = 30 minutes.
# NOTE: In a multi-worker production environment, use Redis instead.
# For single-worker or dev, this works correctly.
_PENDING_TTL = 1800  # 30 minutes in seconds
_pending_imports: dict[str, tuple[DocumentAnalysis, float]] = {}  # key → (analysis, timestamp)


def _cleanup_expired_imports() -> None:
    """Remove pending imports older than TTL. Called on each upload."""
    now = time.time()
    expired = [k for k, (_, ts) in _pending_imports.items() if now - ts > _PENDING_TTL]
    for k in expired:
        _pending_imports.pop(k, None)
    if expired:
        logger.debug(f"Cleaned up {len(expired)} expired pending imports")


# ─── Schemas ──────────────────────────────────────────────────────────────

class ConfirmImportRequest(BaseModel):
    import_id: str
    account_id: Optional[str] = None
    skip_duplicates: bool = True


# ─── Endpoints ────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a bank statement PDF or photo.

    Returns a preview of what will be imported:
    - Total transactions found
    - How many are new (to be imported)
    - How many are duplicates (will be skipped)
    - Full transaction list with duplicate flags

    After reviewing, call /confirm to complete the import.
    """
    # Validate file size
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum is {MAX_FILE_SIZE // 1024 // 1024}MB",
        )

    # Validate content type
    content_type = file.content_type or "application/octet-stream"
    # Handle browser quirks with HEIC/HEIF
    filename_lower = (file.filename or "").lower()
    if filename_lower.endswith(".heic") or filename_lower.endswith(".heif"):
        content_type = "image/heic"
    elif filename_lower.endswith(".pdf"):
        content_type = "application/pdf"
    elif filename_lower.endswith((".jpg", ".jpeg")):
        content_type = "image/jpeg"
    elif filename_lower.endswith(".png"):
        content_type = "image/png"

    if content_type not in SUPPORTED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {content_type}. Supported: PDF, JPEG, PNG, WebP",
        )

    logger.info(
        f"Document upload: tenant={tenant.id}, file={file.filename}, "
        f"size={len(file_bytes)//1024}KB, type={content_type}"
    )

    try:
        analysis = await analyze_document(
            db=db,
            tenant_id=str(tenant.id),
            file_bytes=file_bytes,
            content_type=content_type,
            filename=file.filename or "",
        )
    except Exception as e:
        logger.error(f"Document analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

    if analysis.error:
        if analysis.already_imported:
            raise HTTPException(status_code=409, detail=analysis.error)
        raise HTTPException(status_code=422, detail=analysis.error)

    # Store analysis for confirmation step (with TTL)
    _cleanup_expired_imports()
    import_id = analysis.document_hash[:16]
    _pending_imports[f"{tenant.id}:{import_id}"] = (analysis, time.time())

    # Build response (convert dataclasses to dicts)
    transactions_preview = [
        {
            "date": tx.date,
            "description": tx.description,
            "amount": tx.amount,
            "type": tx.type,
            "is_duplicate": tx.is_duplicate,
            "duplicate_layer": tx.duplicate_layer,
            "duplicate_score": tx.duplicate_score,
            "confidence": tx.confidence,
        }
        for tx in analysis.transactions
    ]

    return {
        "import_id": import_id,
        "bank_name": analysis.bank_name,
        "document_type": analysis.document_type,
        "extraction_method": analysis.extraction_method,
        "total_found": analysis.total_found,
        "to_import": analysis.to_import,
        "duplicates": analysis.duplicates_count,
        "transactions": transactions_preview,
        "message": (
            f"Encontrei {analysis.total_found} transações. "
            f"{analysis.to_import} novas para importar, "
            f"{analysis.duplicates_count} duplicatas."
        ),
    }


@router.post("/confirm")
async def confirm_document_import(
    body: ConfirmImportRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Confirm and execute document import.

    Call this after reviewing the /upload preview.
    Set skip_duplicates=false to force-import even duplicates.
    """
    key = f"{tenant.id}:{body.import_id}"
    entry = _pending_imports.get(key)

    # Check existence and TTL
    if entry is None:
        analysis = None
    else:
        analysis, ts = entry
        if time.time() - ts > _PENDING_TTL:
            _pending_imports.pop(key, None)
            analysis = None

    if not analysis:
        raise HTTPException(
            status_code=404,
            detail="Import session not found or expired. Please re-upload the file.",
        )

    try:
        result = await confirm_import(
            db=db,
            tenant_id=str(tenant.id),
            analysis=analysis,
            account_id=body.account_id,
            skip_duplicates=body.skip_duplicates,
        )
    except Exception as e:
        logger.error(f"Import confirmation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")

    # Clean up this import after successful confirmation
    _pending_imports.pop(key, None)

    return result


@router.get("")
async def list_documents(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
    limit: int = 30,
):
    """List previously imported documents for this client."""
    result = await db.execute(
        text("""
            SELECT id, filename, document_type, bank_name,
                   transactions_imported, duplicates_found, imported_at
            FROM imported_documents
            WHERE tenant_id = :tenant_id::uuid
            ORDER BY imported_at DESC
            LIMIT :limit
        """),
        {"tenant_id": str(tenant.id), "limit": limit},
    )
    rows = result.fetchall()
    return {"documents": [dict(r._mapping) for r in rows]}
