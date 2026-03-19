from pydantic_settings import BaseSettings
from pydantic import field_validator, model_validator
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────────────────────────
    APP_NAME: str = "FinAgent"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"  # "development" | "production"
    SECRET_KEY: str

    # Admin panel authentication
    # Single env var used everywhere — no more ADMIN_SECRET_KEY vs ADMIN_API_KEY confusion
    ADMIN_API_KEY: str = ""

    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str  # postgresql+asyncpg://user:pass@host/dbname
    DATABASE_SCHEMA_PREFIX: str = "tenant"

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ── OpenRouter ────────────────────────────────────────────────────────────
    OPENROUTER_API_KEY: str
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # Model routing (OpenRouter model strings)
    MODEL_FAST: str = "google/gemini-flash-1.5"
    MODEL_STANDARD: str = "anthropic/claude-haiku-4"
    MODEL_POWERFUL: str = "anthropic/claude-sonnet-4-5"
    MODEL_VISION: str = "openai/gpt-4o"
    MODEL_EMBEDDING: str = "openai/text-embedding-3-small"

    # ── Evolution API (WhatsApp) ──────────────────────────────────────────────
    EVOLUTION_API_URL: str = "http://localhost:8080"
    EVOLUTION_API_KEY: str
    EVOLUTION_INSTANCE_NAME: str = "finagent"

    # ── Telegram ─────────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: Optional[str] = None

    # ── CORS / Frontend ───────────────────────────────────────────────────────
    FRONTEND_URL: str = "http://localhost:3000"
    BACKEND_PUBLIC_URL: str = "http://localhost:8000"

    # CORS_ORIGINS: comma-separated string in .env, parsed to list automatically.
    # In production, set to your domain: CORS_ORIGINS=https://finance.bolla.network
    # In development: CORS_ORIGINS=http://localhost:3000,http://localhost:8000
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parsed CORS origins list. Always includes localhost for dev."""
        origins = [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]
        # In production, also add backend public URL to support same-domain setups
        if self.BACKEND_PUBLIC_URL and self.BACKEND_PUBLIC_URL not in origins:
            origins.append(self.BACKEND_PUBLIC_URL)
        # Always allow local dev
        for local in ["http://localhost:3000", "http://localhost:8000"]:
            if local not in origins:
                origins.append(local)
        return origins

    @model_validator(mode="after")
    def validate_required_keys(self) -> "Settings":
        """Fail fast on startup if critical config is missing."""
        if not self.ADMIN_API_KEY:
            logger.warning(
                "ADMIN_API_KEY is not set! Admin panel will be inaccessible. "
                "Set ADMIN_API_KEY in your .env file."
            )
        if len(self.SECRET_KEY) < 32:
            logger.warning("SECRET_KEY is too short (< 32 chars). Use openssl rand -hex 32.")
        return self

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
