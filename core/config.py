"""
core/config.py — Cấu hình toàn cục (v4 — Zero-Setup)

Triết lý:
- Mọi external service đều MẶC ĐỊNH = OFF
- Chạy được ngay không cần config gì
- Bật dần lên khi cần tích hợp thật
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # === App ===
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_env: str = "development"

    # === Logging ===
    log_level: str = "INFO"

    # ─────────────────────────────────────────────────────────
    # ZERO-SETUP MASTER SWITCHES (tất cả OFF theo default)
    # ─────────────────────────────────────────────────────────

    use_llm: bool = False
    """False (default): skip LLM, dùng fallback parser deterministic → ZERO-SETUP.
    True: gọi Gemini API. Cần GEMINI_API_KEY."""

    use_firebase: bool = False
    """False (default): dùng in-memory dict storage → ZERO-SETUP.
    True: kết nối Firebase Firestore thật. Cần FIREBASE_PROJECT_ID + credentials."""

    use_google_services: bool = False
    """False (default): dùng mock Google Workspace (Chat/Calendar/Drive/Sheets) → ZERO-SETUP.
    True: gọi Google APIs thật. Cần GOOGLE_SERVICE_ACCOUNT_JSON."""

    llm_fallback_enabled: bool = True
    """Khi USE_LLM=true và LLM fail → tự động fallback (luôn bật)."""

    # === Google Gemini LLM (chỉ dùng khi USE_LLM=true) ===
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"

    # === Rate Limiter ===
    rate_limit_max_requests: int = 60
    rate_limit_window_seconds: int = 60

    # === Timeout ===
    request_timeout_seconds: float = 10.0
    step_timeout_seconds: float = 5.0

    # === LLM Retry ===
    llm_max_retries: int = 2  # Giảm xuống 2 để fail-fast hơn
    llm_retry_delay_seconds: float = 0.5

    # === Idempotency Cache ===
    idempotency_ttl_seconds: int = 300

    # ── Google Workspace (chỉ dùng khi USE_GOOGLE_SERVICES=true) ────────
    google_chat_webhook_url: str = ""
    google_service_account_json: str = ""

    # ── Firebase Firestore (chỉ dùng khi USE_FIREBASE=true) ─────────────
    firebase_project_id: str = ""

    # ── CORS ────────────────────────────────────────────────────────────
    cors_allowed_origins: str = "*"

    # ── Action Service ───────────────────────────────────────────────────
    action_timeout_seconds: float = 5.0
    actions_enabled: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS_ALLOWED_ORIGINS thành list."""
        if self.cors_allowed_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton settings — cached."""
    return Settings()


# Alias tiện dụng
settings = get_settings()
