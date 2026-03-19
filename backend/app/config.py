from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    APP_NAME: str = "FinAgent"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Database
    DATABASE_URL: str  # postgresql+asyncpg://user:pass@host/dbname
    DATABASE_SCHEMA_PREFIX: str = "tenant"  # each client: tenant_{id}_financial / tenant_{id}_context

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # OpenRouter
    OPENROUTER_API_KEY: str
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # Models (OpenRouter model strings)
    MODEL_FAST: str = "google/gemini-flash-1.5"         # Simple queries
    MODEL_STANDARD: str = "anthropic/claude-haiku-4"    # Standard tasks
    MODEL_POWERFUL: str = "anthropic/claude-sonnet-4-5" # Complex analysis
    MODEL_VISION: str = "openai/gpt-4o"                 # PDF/image reading
    MODEL_EMBEDDING: str = "openai/text-embedding-3-small"

    # Evolution API (WhatsApp)
    EVOLUTION_API_URL: str = "http://localhost:8080"
    EVOLUTION_API_KEY: str
    EVOLUTION_INSTANCE_NAME: str = "finagent"

    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = None

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Frontend
    FRONTEND_URL: str = "http://localhost:3000"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
