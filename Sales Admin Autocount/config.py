from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr
from typing import Literal, Optional


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
    # Vision model used ONLY for OCR of scanned PDF attachments (no text layer).
    # Text-layer PDFs still go through pypdf for free. Empty = scanned docs blocked.
    ilmu_vision_model: str = ""
    ilmu_vision_key: str = ""  # separate API key if the vision model uses one; falls back to ilmu_api_key
    # LLM gateway (littleboatforgraphic/llm-gateway). When set, all LLM calls go through the gateway with this
    # client's gateway key (`gw add-key <client> sales-support`) and are metered for billing there;
    # the Ilmu API keys then live only on the gateway. Leave empty to call Ilmu directly.
    llm_gateway_url: str = ""  # e.g. https://llm.example.com/v1
    llm_gateway_key: str = ""

    # Telegram Configuration (alternative channel - lower messaging cost)
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_webhook_secret_token: SecretStr = SecretStr("")

    # Email Webhook Configuration
    email_webhook_secret_token: SecretStr = SecretStr("")

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

    # Email Order Processing Capability Flags
    email_enabled: bool = True
    email_can_draft: bool = True
    email_can_reply: bool = False
    email_outbound_allowlist: str = ""  # Comma-separated list of allowed recipient emails

    # Email Agent Autonomy Mode
    # shadow: Agent drafts but admin handles manually (measure accuracy)
    # assisted: Admin approves with one click, agent executes
    # selective_autonomy: Agent auto-submits safe orders
    email_autonomy_mode: str = "shadow"

    # Selective Autonomy Criteria
    email_auto_submit_max_amount: float = 10000.0  # RM threshold for auto-submit
    email_auto_submit_repeat_customer: bool = True  # Only repeat customers
    email_auto_submit_trading_house_allowed: bool = False  # Exclude trading houses

    # Microsoft Graph (Outlook) Configuration
    ms_client_id: str = ""  # Azure AD app registration client ID
    ms_tenant_id: str = "consumers"  # Azure AD tenant ID (or 'consumers' for personal accounts)
    ms_client_secret: Optional[SecretStr] = SecretStr("")  # Azure AD app client secret (for service principal)
    ms_poll_interval: int = 300  # Polling interval in seconds (default: 5 minutes)

    # Gmail Configuration
    # Gmail API (OAuth 2.0 - Recommended)
    gmail_client_id: str = ""  # Google Cloud OAuth 2.0 client ID
    gmail_client_secret: Optional[SecretStr] = SecretStr("")  # Google Cloud OAuth 2.0 client secret
    gmail_refresh_token: str = ""  # OAuth 2.0 refresh token (long-lived)
    # Gmail IMAP (Alternative - simpler setup)
    gmail_imap_username: str = ""  # Gmail address
    gmail_imap_password: Optional[SecretStr] = SecretStr("")  # App password (not regular password!)
    gmail_imap_port: int = 993  # IMAP port (default: 993)
    gmail_poll_interval: int = 300  # Polling interval in seconds (default: 5 minutes)

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

