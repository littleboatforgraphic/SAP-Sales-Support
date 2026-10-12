from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Database
    database_url: str = "sqlite:///./sales_admin_autocount.db"

    # Ilmu Claw API (OpenAI-compatible)
    ilmu_api_key: str = ""  # Optional for webhook-only dev runs
    ilmu_base_url: str = "https://api.ilmu.ai/v1"
    ilmu_model: str = "ilmu-mini-v3.3"

    # Telegram Configuration (alternative channel - lower messaging cost)
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_webhook_secret_token: SecretStr = SecretStr("")

    # LLM pricing (USD per million tokens), keyed by model name.
    # "default" is the fallback for models not listed here.
    # Can be overridden via the LLM_PRICING environment variable (JSON) so
    # pricing updates don't require code changes.
    llm_pricing: dict = {
        "default": {"input_per_m": 0.15, "output_per_m": 0.60},
        "ilmu-mini-v3.3": {"input_per_m": 0.15, "output_per_m": 0.60},
    }

    def get_llm_pricing(self, model: str) -> dict:
        """Return per-million-token pricing for a model, falling back to default."""
        pricing = self.llm_pricing.get(model) or self.llm_pricing.get("default")
        if not pricing:
            raise ValueError(f"No pricing configured for model '{model}' and no default set")
        return pricing

    def calculate_llm_cost(self, input_tokens: int, output_tokens: int, model: str = "default") -> float:
        """Calculate cost (USD) for an LLM call using the pricing table."""
        pricing = self.get_llm_pricing(model)
        input_cost = (input_tokens / 1_000_000) * pricing["input_per_m"]
        output_cost = (output_tokens / 1_000_000) * pricing["output_per_m"]
        return input_cost + output_cost

    # WhatsApp Configuration
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: SecretStr = SecretStr("")
    whatsapp_webhook_verify_token: str = ""
    whatsapp_app_secret: SecretStr = SecretStr("")  # For webhook signature verification

    # AOTG API Configuration (AutoCount Cloud Bridge)
    aotg_base_url: str = "https://aotgapi.autocountcloud.com"
    aotg_username: str = ""
    aotg_password: SecretStr = SecretStr("")
    aotg_api_key: SecretStr = SecretStr("")

    # AutoCount SQL Server Configuration (for stock/inventory queries - READ ONLY)
    autocount_sql_server: str = ""
    autocount_sql_database: str = ""
    autocount_sql_username: str = ""
    autocount_sql_password: SecretStr = SecretStr("")
    autocount_sql_driver: str = "ODBC Driver 17 for SQL Server"

    # Email Configuration
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = ""
    smtp_use_tls: bool = True

    # Usage / Cost Control
    token_budget_per_day: int = 100000
    token_budget_per_month: int = 3000000
    cost_alert_threshold_usd: float = 50.0

    # Admin Takeover Configuration
    admin_takeover_window_minutes: int = 30
    admin_takeover_auto_extend: bool = True
    notify_on_takeover: bool = True

    # WhatsApp Rate Limiting
    whatsapp_max_mps: int = 50
    whatsapp_burst_window_seconds: int = 10
    whatsapp_burst_limit: int = 200

    # AOTG API Rate Limiting
    aotg_max_concurrent_requests: int = 10
    aotg_requests_per_second: int = 20

    # Environment
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"


settings = Settings()


# Validate pricing table structure at startup
def _validate_llm_pricing():
    for model, pricing in settings.llm_pricing.items():
        if "input_per_m" not in pricing or "output_per_m" not in pricing:
            raise ValueError(
                f"Invalid LLM_PRICING entry for '{model}': "
                "each entry needs 'input_per_m' and 'output_per_m'"
            )


_validate_llm_pricing()
