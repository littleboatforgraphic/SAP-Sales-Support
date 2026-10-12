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

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"
TELEGRAM_MAX_MESSAGE_LENGTH = 4096


class TelegramClient:
    """Thin wrapper over the Telegram Bot API using async httpx."""

    def __init__(self, bot_token: Optional[str] = None, http_client: Optional[httpx.AsyncClient] = None):
        from config import settings

        self.bot_token = bot_token or (settings.telegram_bot_token.get_secret_value() if settings.telegram_bot_token else "")
        if not self.bot_token:
            logger.warning("Telegram bot token not configured - client will not be able to send messages")
        self._http_client = http_client

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token)

    async def _post(self, method: str, payload: dict) -> dict:
        """POST to the Telegram Bot API and return the parsed result."""
        if not self.bot_token:
            raise RuntimeError("Telegram bot token not configured")

        url = TELEGRAM_API_BASE.format(token=self.bot_token, method=method)
        client = self._http_client or httpx.AsyncClient(timeout=30.0)

        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                raise RuntimeError(f"Telegram API error for {method}: {data.get('description', 'unknown error')}")
            return data.get("result", {})
        except httpx.HTTPStatusError as e:
            # Handle 429 rate limiting
            if e.response.status_code == 429:
                retry_after = e.response.headers.get("retry-after", 5)
                logger.warning(f"Telegram rate limited, retry after {retry_after}s")
                raise RuntimeError(f"Telegram rate limited, retry after {retry_after}s") from e
            # Handle 5xx errors
            if e.response.status_code >= 500:
                logger.error(f"Telegram server error: {e.response.status_code}")
                raise RuntimeError(f"Telegram server error: {e.response.status_code}") from e
            # Re-raise other HTTP errors without exposing token in URL
            raise RuntimeError(f"Telegram API request failed with status {e.response.status_code}") from e
        except httpx.TimeoutException:
            raise RuntimeError("Telegram API request timed out") from None
        except Exception as e:
            # Sanitize any exception that might expose the token
            logger.error(f"Telegram API error for {method}: {str(e)}")
            raise RuntimeError(f"Telegram API error for {method}") from e
        finally:
            if not self._http_client:
                await client.aclose()

    async def send_message(self, chat_id: str, text: str) -> dict:
        """Send a text message to a chat. Automatically chunks messages > 4096 chars."""
        if len(text) > TELEGRAM_MAX_MESSAGE_LENGTH:
            logger.warning(f"Message exceeds {TELEGRAM_MAX_MESSAGE_LENGTH} chars, chunking")
            # Split into chunks
            chunks = [text[i:i+TELEGRAM_MAX_MESSAGE_LENGTH] for i in range(0, len(text), TELEGRAM_MAX_MESSAGE_LENGTH)]
            results = []
            for i, chunk in enumerate(chunks):
                if i > 0:
                    chunk = f"...[continued]\n{chunk}"
                result = await self._post("sendMessage", {
                    "chat_id": chat_id,
                    "text": chunk,
                })
                results.append(result)
            return {"sent": len(results), "chunks": results}
        else:
            return await self._post("sendMessage", {
                "chat_id": chat_id,
                "text": text,
            })

    async def set_webhook(self, webhook_url: str, secret_token: Optional[str] = None) -> dict:
        """
        Register this service's webhook URL with Telegram.
        If secret_token is set, Telegram includes it in the X-Telegram-Bot-Api-Secret-Token
        header on every webhook request.

        In production, secret_token is required for security.
        """
        from config import settings

        if settings.environment == "production" and not secret_token:
            raise RuntimeError("Webhook secret token is required in production")

        payload = {"url": webhook_url}
        if secret_token:
            payload["secret_token"] = secret_token
        return await self._post("setWebhook", payload)

    async def delete_webhook(self) -> dict:
        """Remove the registered webhook (switch back to polling)."""
        return await self._post("deleteWebhook", {})

    async def get_me(self) -> dict:
        """Get bot identity - useful for a connectivity smoke test."""
        return await self._post("getMe", {})

    async def get_webhook_info(self) -> dict:
        """Get current webhook information."""
        return await self._post("getWebhookInfo", {})


# Module-level client factory (creates client on demand to avoid capturing token at import)
def get_telegram_client() -> TelegramClient:
    """Get a Telegram client instance (reads token from settings at call time)."""
    return TelegramClient()
