from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.config import settings
from app.database import init_db

# ─── API Routers ───────────────────────────────────────────────────────────
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.webhooks import router as webhooks_router
from app.api.transactions import router as transactions_router
from app.api.accounts import router as accounts_router
from app.api.reports import router as reports_router
from app.api.alerts import router as alerts_router
from app.api.profile import router as profile_router

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🚀 Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    await init_db()
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="FinAgent — AI-powered personal financial assistant",
    lifespan=lifespan,
    docs_url="/api/docs",   # always on so Claude Code can inspect
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routes ────────────────────────────────────────────────────────────────
API_V1 = "/api/v1"

app.include_router(auth_router,         prefix=f"{API_V1}/auth",         tags=["🔐 Auth"])
app.include_router(profile_router,      prefix=f"{API_V1}/profile",      tags=["👤 Profile"])
app.include_router(chat_router,         prefix=f"{API_V1}/chat",         tags=["💬 Chat"])
app.include_router(webhooks_router,     prefix=f"{API_V1}/webhooks",     tags=["🔗 Webhooks"])
app.include_router(transactions_router, prefix=f"{API_V1}/transactions", tags=["💰 Transactions"])
app.include_router(accounts_router,     prefix=f"{API_V1}/accounts",     tags=["🏦 Accounts"])
app.include_router(reports_router,      prefix=f"{API_V1}/reports",      tags=["📊 Reports"])
app.include_router(alerts_router,       prefix=f"{API_V1}/alerts",       tags=["🔔 Alerts"])


# ─── Health check ──────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health():
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "service": settings.APP_NAME,
    }
