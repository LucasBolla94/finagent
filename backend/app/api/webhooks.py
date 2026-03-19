"""
Webhook endpoints — receive messages from WhatsApp (Evolution API) and Telegram.

POST /api/v1/webhooks/whatsapp  — Evolution API pushes messages here
POST /api/v1/webhooks/telegram  — Telegram Bot API pushes updates here

How it works:
1. User sends WhatsApp/Telegram message
2. Evolution API / Telegram Bot sends a POST request to this webhook
3. We find the tenant by their phone number / chat_id
4. We call the FinAgent with the message
5. We send the agent's response back via the channel
"""
import logging
import asyncio
import httpx
from typing import Any

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import Depends

from app.database import get_db
from app.models.tenant import Tenant
from app.models.agent import Agent
from app.agent.core import FinAgent
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Shared stateless FinAgent instance
_agent = FinAgent()


# ─── WhatsApp (Evolution API) ─────────────────────────────────────────────

@router.post("/whatsapp")
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Receives messages from Evolution API (WhatsApp).
    Evolution API sends a JSON payload with the sender's number and message.

    We process the message in the background so the webhook returns fast (200 OK).
    Evolution API requires a quick response to avoid retry storms.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Evolution API webhook structure
    # See: https://doc.evolution-api.com/webhooks
    event_type = payload.get("event", "")

    if event_type not in ("MESSAGES_UPSERT", "messages.upsert"):
        # Ignore non-message events (status updates, receipts, etc.)
        return {"status": "ignored", "event": event_type}

    data = payload.get("data", {})
    message_data = data if isinstance(data, dict) else {}

    # Extract sender's phone number (remove country code prefix if needed)
    # Evolution sends: {"key": {"remoteJid": "5511999999999@s.whatsapp.net"}}
    key = message_data.get("key", {})
    from_me = key.get("fromMe", False)

    if from_me:
        return {"status": "ignored", "reason": "own message"}

    remote_jid: str = key.get("remoteJid", "")
    phone_number = remote_jid.split("@")[0]  # strip @s.whatsapp.net

    if not phone_number:
        return {"status": "ignored", "reason": "no sender"}

    # Extract message text
    msg = message_data.get("message", {})
    text = (
        msg.get("conversation")
        or msg.get("extendedTextMessage", {}).get("text")
        or msg.get("imageMessage", {}).get("caption")
        or ""
    ).strip()

    if not text:
        # Audio, sticker, video without caption — ignore for now (Phase 7: audio transcription)
        return {"status": "ignored", "reason": "no text content"}

    # Find tenant by WhatsApp number
    result = await db.execute(
        select(Tenant).where(Tenant.whatsapp_number == phone_number)
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        logger.info(f"Unregistered WhatsApp number: {phone_number}")
        # Optionally: send a welcome message asking them to register
        return {"status": "ignored", "reason": "unknown number"}

    if not tenant.is_active:
        return {"status": "ignored", "reason": "inactive tenant"}

    # Process in background (so webhook returns 200 immediately)
    background_tasks.add_task(
        _process_whatsapp_message,
        tenant_id=str(tenant.id),
        phone_number=phone_number,
        text=text,
        remote_jid=remote_jid,
    )

    return {"status": "accepted"}


async def _process_whatsapp_message(
    tenant_id: str,
    phone_number: str,
    text: str,
    remote_jid: str,
):
    """Background task: call agent and send response via WhatsApp."""
    try:
        agent_response = await _agent.respond(
            tenant_id=tenant_id,
            message=text,
            channel="whatsapp",
            session_id=f"wa_{phone_number}",
        )
        await _send_whatsapp_message(remote_jid=remote_jid, text=agent_response.content)

    except Exception as e:
        logger.error(f"WhatsApp processing error for {phone_number}: {e}", exc_info=True)


async def _send_whatsapp_message(remote_jid: str, text: str):
    """Send a WhatsApp message via Evolution API."""
    url = f"{settings.EVOLUTION_API_URL}/message/sendText/{settings.EVOLUTION_INSTANCE_NAME}"
    payload = {
        "number": remote_jid,
        "options": {"delay": 1200, "presence": "composing"},
        "textMessage": {"text": text},
    }
    headers = {"apikey": settings.EVOLUTION_API_KEY, "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code not in (200, 201):
            logger.error(f"Evolution API error: {resp.status_code} — {resp.text}")
        else:
            logger.info(f"WhatsApp message sent to {remote_jid}")


# ─── Telegram ─────────────────────────────────────────────────────────────

@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Receives updates from Telegram Bot API.
    Set webhook URL with: POST https://api.telegram.org/bot{TOKEN}/setWebhook?url=...

    Telegram sends a JSON "Update" object for each message.
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="Telegram not configured")

    try:
        update = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Telegram Update object structure
    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"status": "ignored"}

    chat_id = str(message.get("chat", {}).get("id", ""))
    text = (message.get("text") or "").strip()

    if not chat_id or not text:
        return {"status": "ignored"}

    # Find tenant by Telegram chat_id
    result = await db.execute(
        select(Tenant).where(Tenant.telegram_chat_id == chat_id)
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        logger.info(f"Unregistered Telegram chat_id: {chat_id}")
        # Send help message
        background_tasks.add_task(_send_telegram_message, chat_id, "Olá! Por favor, registre-se no FinAgent para começar. 😊")
        return {"status": "ignored", "reason": "unknown chat_id"}

    if not tenant.is_active:
        return {"status": "ignored"}

    background_tasks.add_task(
        _process_telegram_message,
        tenant_id=str(tenant.id),
        chat_id=chat_id,
        text=text,
    )

    return {"status": "accepted"}


async def _process_telegram_message(tenant_id: str, chat_id: str, text: str):
    """Background task: call agent and reply on Telegram."""
    try:
        agent_response = await _agent.respond(
            tenant_id=tenant_id,
            message=text,
            channel="telegram",
            session_id=f"tg_{chat_id}",
        )
        await _send_telegram_message(chat_id=chat_id, text=agent_response.content)
    except Exception as e:
        logger.error(f"Telegram processing error for {chat_id}: {e}", exc_info=True)


async def _send_telegram_message(chat_id: str, text: str):
    """Send a message via Telegram Bot API."""
    if not settings.TELEGRAM_BOT_TOKEN:
        return

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code != 200:
            logger.error(f"Telegram API error: {resp.status_code} — {resp.text}")
        else:
            logger.info(f"Telegram message sent to {chat_id}")
