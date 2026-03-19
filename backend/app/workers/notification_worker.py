"""
Notification worker — sends messages via WhatsApp or Telegram.
Used by all other workers when they need to notify a client.
"""
import asyncio
import logging

import httpx

from app.workers.celery_app import celery
from app.config import settings

logger = logging.getLogger(__name__)


async def _send_whatsapp(phone_number: str, message: str) -> bool:
    """Send WhatsApp message via Evolution API."""
    jid = f"{phone_number}@s.whatsapp.net"
    url = f"{settings.EVOLUTION_API_URL}/message/sendText/{settings.EVOLUTION_INSTANCE_NAME}"
    payload = {
        "number": jid,
        "options": {"delay": 1000, "presence": "composing"},
        "textMessage": {"text": message},
    }
    headers = {"apikey": settings.EVOLUTION_API_KEY, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            return resp.status_code in (200, 201)
    except Exception as e:
        logger.error(f"WhatsApp send error: {e}")
        return False


async def _send_telegram(chat_id: str, message: str) -> bool:
    """Send Telegram message."""
    if not settings.TELEGRAM_BOT_TOKEN:
        return False
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"})
            return resp.status_code == 200
    except Exception as e:
        logger.error(f"Telegram send error: {e}")
        return False


@celery.task(name="app.workers.notification_worker.send_notification", bind=True, max_retries=3)
def send_notification(self, tenant_data: dict, message: str, channels: list = None):
    """
    Send a notification to a client on their connected channels.

    tenant_data: {
        "whatsapp_number": "5511...",
        "telegram_chat_id": "123456...",
    }
    channels: ["whatsapp", "telegram"] — defaults to all connected
    """
    if channels is None:
        channels = ["whatsapp", "telegram"]

    async def _run():
        tasks = []
        if "whatsapp" in channels and tenant_data.get("whatsapp_number"):
            tasks.append(_send_whatsapp(tenant_data["whatsapp_number"], message))
        if "telegram" in channels and tenant_data.get("telegram_chat_id"):
            tasks.append(_send_telegram(tenant_data["telegram_chat_id"], message))
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return all(r is True for r in results if not isinstance(r, Exception))
        return False

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error(f"Notification failed: {exc}")
        raise self.retry(exc=exc, countdown=60)
