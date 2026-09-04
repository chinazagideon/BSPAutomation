"""Application configuration and environment settings using Pydantic Settings."""

from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # General Application
    APP_NAME: str = "Enterprise WhatsApp Platform"
    ENVIRONMENT: Literal["development", "staging", "production", "test"] = "development"
    DEBUG: bool = True
    # API & Route Prefixes
    API_V1_PREFIX: str = "/api/v1"
    CORE_PREFIX: str = "/core"
    AUTH_PREFIX: str = "/auth"
    INGRESS_PREFIX: str = "/ingress"
    LEDGER_PREFIX: str = "/ledger"
    RESERVATIONS_PREFIX: str = "/reservations"
    DESK_PREFIX: str = "/desk"
    COMPLIANCE_PREFIX: str = "/compliance"

    @property
    def auth_cookie_path(self) -> str:
        """Dynamic scoped path for refresh token cookie isolation."""
        return f"{self.API_V1_PREFIX}{self.CORE_PREFIX}{self.AUTH_PREFIX}"

    # Database & Redis Infrastructure
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/bsp_whatsapp_enterprise"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_ECHO: bool = False
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security & PII Encryption
    SECRET_KEY: str = "dev_insecure_secret_key_replace_in_production_with_strong_entropy_32char"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    REFRESH_TOKEN_GRACE_SECONDS: int = 5
    ACCOUNT_LOCKOUT_THRESHOLD: int = 5
    ACCOUNT_LOCKOUT_DURATION_MINUTES: int = 15
    AUTH_RATE_LIMIT_PER_MINUTE: int = 15
    MERCHANT_API_RATE_LIMIT_PER_MINUTE: int = 120
    WEBHOOK_RATE_LIMIT_PER_SECOND: int = 500
    PII_TOKEN_AES_KEY: str = "0123456789abcdef0123456789abcdef"

    # -------------------------------------------------------------
    # 3-STAGE CASCADING HYBRID NLU STATE CONTROLLERS & THRESHOLDS
    # -------------------------------------------------------------
    # Stage 1: Fast-Path Deterministic Trigram / Regex Engine
    USE_FAST_PATH: bool = True
    FAST_PATH_CONFIDENCE_THRESHOLD: float = 0.90

    # Stage 2: Custom Local Classifier (HuggingFace / ONNX)
    USE_CUSTOM_MODEL: bool = True
    CUSTOM_MODEL_TYPE: Literal["mock", "onnx", "transformers"] = "mock"
    CUSTOM_MODEL_PATH: str = "models/nigerian_pidgin_intent"
    CUSTOM_MODEL_CONFIDENCE_THRESHOLD: float = 0.75

    # Stage 3: LLM Escalation (Google Gemini 3.7 Flash)
    USE_LLM_ESCALATION: bool = True
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.7-flash"

    # -------------------------------------------------------------
    # EXTERNAL ADAPTER RAILS & MOCK HARNESSES
    # -------------------------------------------------------------
    USE_MOCK_PAYMENT_GATEWAY: bool = True
    MONIEPOINT_API_KEY: str = ""
    MONIEPOINT_BASE_URL: str = "https://api.moniepoint.com/v1"

    USE_MOCK_WHATSAPP_BSP: bool = True
    WHATSAPP_BSP_PROVIDER: Literal["META_CLOUD", "TERMII", "TWILIO_AFRICA", "INFOBIP_NG"] = "META_CLOUD"
    META_CLOUD_API_TOKEN: str = ""
    META_PHONE_NUMBER_ID: str = ""
    META_WEBHOOK_VERIFY_TOKEN: str = "enterprise_whatsapp_secret_webhook_token"
    META_APP_SECRET: str = "dev_meta_app_secret_placeholder"

    # Termii SMS Rail (Manager Outage Alerts & Fallback)
    TERMII_API_KEY: str = ""
    TERMII_BASE_URL: str = "https://api.ng.termii.com/api"
    TERMII_SENDER_ID: str = "SME-ALERT"

    # Timeouts & Cache TTLs
    DESK_HEARTBEAT_TIMEOUT_SECONDS: int = 60
    CATALOG_MANIFEST_TTL_SECONDS: int = 3600
    PROVIDER_CONTEXT_TTL_SECONDS: int = 3600

    # HTTP Connection Pool & Egress Limits
    HTTP_POOL_MAX_CONNECTIONS: int = 100
    HTTP_POOL_MAX_KEEPALIVE_CONNECTIONS: int = 25
    HTTP_POOL_KEEPALIVE_EXPIRY_SECONDS: float = 30.0
    HTTP_CONNECT_TIMEOUT_SECONDS: float = 5.0
    HTTP_READ_TIMEOUT_SECONDS: float = 15.0
    HTTP_WRITE_TIMEOUT_SECONDS: float = 5.0
    HTTP_POOL_TIMEOUT_SECONDS: float = 5.0

    # -------------------------------------------------------------
    # OPENTELEMETRY & STRUCTURED LOGGING TELEMETRY
    # -------------------------------------------------------------
    OTEL_ENABLED: bool = True
    OTEL_SERVICE_NAME: str = "bsp-whatsapp-backend"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"
    OTEL_SAMPLING_RATIO: float = 1.0  # 1.0 in dev/test/staging; override via env in prod
    LOG_LEVEL: str = "INFO"


settings = Settings()
