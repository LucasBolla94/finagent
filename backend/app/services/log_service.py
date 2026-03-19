"""
Centralized system log service.

Usage anywhere in the backend:
    from app.services.log_service import syslog
    await syslog.error("whatsapp", "qr_fetch", "count:0 after 3 restarts", details={...})
    await syslog.info("auth", "login", "User logged in", user_id=str(tenant_id))

Logs are persisted to the `system_logs` table in PostgreSQL and can be
viewed at GET /api/admin/logs (requires X-Admin-Key header).

Design notes:
- All methods are async and fire-and-forget safe (errors are swallowed so
  logging never breaks the main request).
- Uses the global AsyncSessionLocal factory (no FastAPI DI needed).
- Also mirrors every entry to the standard Python logger so docker logs
  always show the same info even if DB is unavailable.
"""
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from app.database import AsyncSessionLocal
from sqlalchemy import text

_logger = logging.getLogger("syslog")

# SQL used by every write — keeps it in one place
_INSERT_SQL = text("""
    INSERT INTO system_logs (level, service, event, message, details, duration_ms, user_id, created_at)
    VALUES (:level, :service, :event, :message, :details::jsonb, :duration_ms, :user_id, NOW())
    RETURNING id
""")


class SystemLogService:
    """
    Async log writer.  All methods return the new row id (or None on error).
    """

    async def _write(
        self,
        level: str,
        service: str,
        event: Optional[str],
        message: str,
        details: Optional[Dict[str, Any]],
        duration_ms: Optional[int],
        user_id: Optional[str],
    ) -> Optional[int]:
        # Mirror to Python logger first (always works even if DB is down)
        log_fn = {
            "ERROR":   _logger.error,
            "WARNING": _logger.warning,
            "INFO":    _logger.info,
            "DEBUG":   _logger.debug,
        }.get(level, _logger.info)
        log_fn(f"[{service}] {event or '-'} | {message}" +
               (f" | {json.dumps(details)}" if details else ""))

        # Persist to DB
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    _INSERT_SQL,
                    {
                        "level":       level,
                        "service":     service,
                        "event":       event,
                        "message":     message,
                        "details":     json.dumps(details) if details else None,
                        "duration_ms": duration_ms,
                        "user_id":     user_id,
                    },
                )
                await db.commit()
                row = result.fetchone()
                return row[0] if row else None
        except Exception as exc:
            _logger.error(f"syslog DB write failed: {exc}")
            return None

    async def error(
        self,
        service: str,
        event: str,
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None,
        user_id: Optional[str] = None,
    ) -> Optional[int]:
        return await self._write("ERROR", service, event, message, details, duration_ms, user_id)

    async def warning(
        self,
        service: str,
        event: str,
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None,
        user_id: Optional[str] = None,
    ) -> Optional[int]:
        return await self._write("WARNING", service, event, message, details, duration_ms, user_id)

    async def info(
        self,
        service: str,
        event: str,
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None,
        user_id: Optional[str] = None,
    ) -> Optional[int]:
        return await self._write("INFO", service, event, message, details, duration_ms, user_id)

    async def debug(
        self,
        service: str,
        event: str,
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> Optional[int]:
        return await self._write("DEBUG", service, event, message, details, None, user_id)

    @asynccontextmanager
    async def timed(
        self,
        level: str,
        service: str,
        event: str,
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ):
        """
        Context manager that measures execution time and logs on exit.

        Usage:
            async with syslog.timed("INFO", "whatsapp", "qr_fetch", "Getting QR code"):
                qr = await _fetch_qr()
        """
        t0 = time.monotonic()
        try:
            yield
        except Exception as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            err_details = {**(details or {}), "exception": str(exc), "type": type(exc).__name__}
            await self._write("ERROR", service, event, f"{message} — {exc}", err_details, elapsed, user_id)
            raise
        else:
            elapsed = int((time.monotonic() - t0) * 1000)
            await self._write(level, service, event, message, details, elapsed, user_id)


# Singleton — import and use anywhere
syslog = SystemLogService()
