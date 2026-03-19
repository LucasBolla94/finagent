"""
Vision-based extractor — for scanned PDFs and photos.
Uses GPT-4o Vision via OpenRouter to read documents with near 100% accuracy.

Handles:
- Photos of receipts
- Scanned bank statements
- Low-quality images
- Handwritten notes
"""
import base64
import io
import json
import logging
import re
from typing import Optional
from datetime import date

import httpx

from app.config import settings
from app.services.pdf_extractor import RawTransaction, parse_date_br, parse_amount

logger = logging.getLogger(__name__)

# System prompt for the Vision AI — instructs it to extract transactions as JSON
VISION_SYSTEM_PROMPT = """You are a financial document scanner specialized in Brazilian bank statements, receipts, and financial documents.

Your task: Extract ALL financial transactions from the provided image and return them as a JSON array.

Rules:
1. Extract EVERY transaction you can see — don't skip any
2. For amounts: use positive numbers. For debits/expenses use type "expense", for credits/income use "income"
3. For dates: use format "DD/MM/YYYY"
4. For amounts: use decimal format with period (e.g., 1234.56)
5. If you can't read a value clearly, use your best estimate and set confidence below 0.8
6. Include the raw text you read for each transaction

Return ONLY valid JSON, no markdown, no explanation. Format:
{
  "bank_name": "detected bank name or null",
  "document_type": "bank_statement | receipt | invoice | other",
  "period": {"start": "DD/MM/YYYY or null", "end": "DD/MM/YYYY or null"},
  "transactions": [
    {
      "date": "DD/MM/YYYY",
      "description": "transaction description",
      "amount": 123.45,
      "type": "expense | income",
      "balance_after": 1000.00 or null,
      "confidence": 0.95,
      "raw_text": "original text from document"
    }
  ]
}"""


def pdf_page_to_image(file_bytes: bytes, page_num: int = 0) -> Optional[bytes]:
    """Convert a PDF page to a PNG image using PyMuPDF (fitz)."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        if page_num >= len(doc):
            page_num = 0
        page = doc[page_num]
        # High DPI for better OCR (300 DPI equivalent)
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        doc.close()
        return img_bytes
    except Exception as e:
        logger.error(f"PDF to image conversion error: {e}")
        return None


def pdf_all_pages_to_images(file_bytes: bytes) -> list[bytes]:
    """Convert all PDF pages to images."""
    try:
        import fitz
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        images = []
        mat = fitz.Matrix(2.0, 2.0)
        for page in doc:
            pix = page.get_pixmap(matrix=mat)
            images.append(pix.tobytes("png"))
        doc.close()
        return images
    except Exception as e:
        logger.error(f"PDF multi-page conversion error: {e}")
        return []


async def extract_with_vision(image_bytes: bytes, mime_type: str = "image/png") -> dict:
    """
    Send an image to GPT-4o Vision and extract transaction data.
    Returns raw parsed JSON from the model.
    """
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{mime_type};base64,{image_b64}"

    payload = {
        "model": settings.MODEL_VISION,
        "messages": [
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url, "detail": "high"},
                    },
                    {
                        "type": "text",
                        "text": "Extract all financial transactions from this document as JSON.",
                    },
                ],
            },
        ],
        "max_tokens": 4096,
        "temperature": 0.1,  # Low temperature for consistent extraction
    }

    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://finagent.app",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{settings.OPENROUTER_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]

    # Parse JSON from response
    # Sometimes models wrap in markdown code blocks
    json_text = content.strip()
    if json_text.startswith("```"):
        json_text = re.sub(r"^```[a-z]*\n?", "", json_text)
        json_text = re.sub(r"\n?```$", "", json_text)

    return json.loads(json_text)


def vision_result_to_raw_transactions(result: dict) -> list[RawTransaction]:
    """Convert the Vision AI JSON response to RawTransaction objects."""
    transactions = []
    for item in result.get("transactions", []):
        parsed_date = parse_date_br(item.get("date", ""))
        amount = float(item.get("amount", 0))
        if amount < 0:
            amount = abs(amount)
        tx_type = item.get("type", "expense")
        if tx_type not in ("income", "expense", "transfer"):
            tx_type = "expense"

        if not parsed_date or amount == 0:
            continue

        transactions.append(RawTransaction(
            date=parsed_date,
            description=item.get("description", "Transação"),
            amount=amount,
            type=tx_type,
            balance_after=item.get("balance_after"),
            raw_text=item.get("raw_text", ""),
            confidence=float(item.get("confidence", 0.9)),
        ))

    return transactions


async def extract_from_image_file(file_bytes: bytes, content_type: str) -> tuple[list[RawTransaction], dict]:
    """
    Main entry point for image extraction.
    Returns (transactions, metadata) where metadata has bank_name, document_type, period.
    """
    try:
        result = await extract_with_vision(file_bytes, mime_type=content_type)
        transactions = vision_result_to_raw_transactions(result)
        metadata = {
            "bank_name": result.get("bank_name"),
            "document_type": result.get("document_type", "bank_statement"),
            "period": result.get("period", {}),
            "extraction_method": "vision",
        }
        return transactions, metadata
    except Exception as e:
        logger.error(f"Vision extraction failed: {e}")
        return [], {"extraction_method": "vision", "error": str(e)}


async def extract_from_pdf_with_vision(file_bytes: bytes) -> tuple[list[RawTransaction], dict]:
    """
    Extract from a PDF by converting pages to images and sending to Vision AI.
    Used for scanned PDFs or when pdfplumber yields poor results.
    """
    images = pdf_all_pages_to_images(file_bytes)
    if not images:
        return [], {"error": "Could not convert PDF to images"}

    all_transactions = []
    metadata = {}

    for i, image_bytes in enumerate(images):
        try:
            result = await extract_with_vision(image_bytes, "image/png")
            txs = vision_result_to_raw_transactions(result)
            all_transactions.extend(txs)
            if i == 0:  # Use first page for metadata
                metadata = {
                    "bank_name": result.get("bank_name"),
                    "document_type": result.get("document_type", "bank_statement"),
                    "period": result.get("period", {}),
                    "extraction_method": "vision_pdf",
                    "pages_processed": len(images),
                }
        except Exception as e:
            logger.warning(f"Vision failed on page {i}: {e}")
            continue

    return all_transactions, metadata
