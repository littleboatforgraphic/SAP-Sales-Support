"""
Telegram Bot API client.
Used as a lower-cost alternative to WhatsApp for agent replies.
Implements only what this system needs: sending text messages and
webhook management. Document/file sending can be added when the
Notifier layer is built.
"""
import logging
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramClient:
    """Thin wrapper over the Telegram Bot API using httpx."""

    def __init__(self, bot_token: Optional[str] = None):
        self.bot_token = bot_token or settings.telegram_bot_token
        if not self.bot_token:
            logger.warning("Telegram bot token not configured - client will not be able to send messages")

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token)

    def _post(self, method: str, payload: dict) -> dict:
        """POST to the Telegram Bot API and return the parsed result."""
        url = TELEGRAM_API_BASE.format(token=self.bot_token, method=method)
        response = httpx.post(url, json=payload, timeout=30.0)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error for {method}: {data.get('description', 'unknown error')}")
        return data.get("result", {})

    def send_message(self, chat_id: str, text: str) -> dict:
        """Send a text message to a chat."""
        return self._post("sendMessage", {
            "chat_id": chat_id,
            "text": text,
        })

    def set_webhook(self, webhook_url: str, secret_token: Optional[str] = None) -> dict:
        """
        Register this service's webhook URL with Telegram.
        If secret_token is set, Telegram includes it in the X-Telegram-Bot-Api-Secret-Token
        header on every webhook request.
        """
        payload = {"url": webhook_url}
        if secret_token:
            payload["secret_token"] = secret_token
        return self._post("setWebhook", payload)

    def delete_webhook(self) -> dict:
        """Remove the registered webhook (switch back to polling)."""
        return self._post("deleteWebhook", {})

    def get_me(self) -> dict:
        """Get bot identity - useful for a connectivity smoke test."""
        return self._post("getMe", {})

    def get_webhook_info(self) -> dict:
        """Get current webhook information."""
        return self._post("getWebhookInfo", {})


# Module-level client (token is read from settings at call time if not passed)
telegram_client = TelegramClient()
