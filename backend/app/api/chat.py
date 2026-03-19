"""
Chat endpoints — web interface to talk to the FinAgent.

POST /api/v1/chat/message  — send one message, get response (HTTP)
WS   /api/v1/chat/ws       — real-time WebSocket chat
"""
import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.tenant import Tenant
from app.middleware.auth import get_current_tenant
from app.core.security import decode_token
from app.agent.core import FinAgent

logger = logging.getLogger(__name__)
router = APIRouter()

# One shared FinAgent instance (stateless — all state is in DB)
agent = FinAgent()


# ─── Schemas ──────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None  # pass to maintain conversation context


class ChatResponse(BaseModel):
    response: str
    session_id: str


# ─── HTTP endpoint ────────────────────────────────────────────────────────

@router.post("/message", response_model=ChatResponse)
async def send_message(
    body: ChatRequest,
    tenant: Tenant = Depends(get_current_tenant),
):
    """
    Send a message to the agent and get a response.

    - If no session_id is provided, a new conversation session is started.
    - Use the same session_id to continue a conversation.
    - The agent remembers everything across sessions through its memory system.
    """
    session_id = body.session_id or str(uuid.uuid4())

    try:
        response = await agent.respond(
            tenant_id=str(tenant.id),
            message=body.message,
            channel="web",
            session_id=session_id,
        )
    except Exception as e:
        logger.error(f"Agent error for tenant {tenant.id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Agent temporarily unavailable")

    return ChatResponse(response=response, session_id=session_id)


# ─── WebSocket endpoint ───────────────────────────────────────────────────

@router.websocket("/ws")
async def websocket_chat(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
    db: AsyncSession = Depends(get_db),
):
    """
    Real-time WebSocket chat.

    Connect: ws://host/api/v1/chat/ws?token=YOUR_JWT_TOKEN

    Client sends: {"message": "...", "session_id": "optional-uuid"}
    Server sends: {"response": "...", "session_id": "uuid", "type": "message"}
                  {"type": "error", "detail": "..."}
                  {"type": "ping"}  (keepalive every 30s)
    """
    # Validate JWT token from query param
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        await websocket.close(code=4001, reason="Invalid token")
        return

    tenant_id_str = payload.get("sub", "")
    if not tenant_id_str:
        await websocket.close(code=4001, reason="Invalid token")
        return

    import uuid as _uuid
    try:
        tenant_uuid = _uuid.UUID(tenant_id_str)
    except ValueError:
        await websocket.close(code=4001, reason="Invalid token")
        return

    result = await db.execute(select(Tenant).where(Tenant.id == tenant_uuid))
    tenant = result.scalar_one_or_none()

    if not tenant or not tenant.is_active:
        await websocket.close(code=4003, reason="Forbidden")
        return

    await websocket.accept()
    logger.info(f"WebSocket connected: tenant={tenant.id}")

    # Each WebSocket connection = one conversation session
    session_id = str(uuid.uuid4())

    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "").strip()

            if not message:
                await websocket.send_json({"type": "error", "detail": "Empty message"})
                continue

            # Use provided session_id if given (allows resuming a session)
            session_id = data.get("session_id") or session_id

            try:
                response = await agent.respond(
                    tenant_id=str(tenant.id),
                    message=message,
                    channel="web",
                    session_id=session_id,
                )
                await websocket.send_json({
                    "type": "message",
                    "response": response,
                    "session_id": session_id,
                })
            except Exception as e:
                logger.error(f"Agent error in WS for tenant {tenant.id}: {e}", exc_info=True)
                await websocket.send_json({
                    "type": "error",
                    "detail": "Agent temporarily unavailable, try again",
                })

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: tenant={tenant.id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        await websocket.close(code=1011)
