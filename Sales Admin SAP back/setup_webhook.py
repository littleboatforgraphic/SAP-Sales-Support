"""
Setup script to register Telegram webhook.

This script helps configure the Telegram bot webhook for receiving messages.
Run this after setting up ngrok tunnel and before testing the bot.

Usage:
    python setup_webhook.py --webhook-url https://your-ngrok-url.ngrok-free.app/api/v1/webhook/telegram
    python setup_webhook.py --delete  # Remove webhook (switch back to polling)
    python setup_webhook.py --info  # Get current webhook info
"""

import argparse
import sys
from telegram_client import telegram_client
from config import settings


def setup_webhook(webhook_url: str, secret_token: str = None):
    """Register the webhook with Telegram."""
    if not settings.telegram_bot_token:
        print("ERROR: TELEGRAM_BOT_TOKEN not configured in .env file")
        sys.exit(1)

    if not webhook_url:
        print("ERROR: Webhook URL is required")
        sys.exit(1)

    print(f"Setting webhook to: {webhook_url}")
    if secret_token:
        print(f"Using secret token: {secret_token[:10]}...")

    try:
        result = telegram_client.set_webhook(webhook_url, secret_token)
        print("SUCCESS: Webhook registered")
        print(f"Result: {result}")
    except Exception as e:
        print(f"ERROR: Failed to set webhook: {e}")
        sys.exit(1)


def delete_webhook():
    """Remove the webhook (switch back to polling)."""
    if not settings.telegram_bot_token:
        print("ERROR: TELEGRAM_BOT_TOKEN not configured in .env file")
        sys.exit(1)

    print("Deleting webhook (switching back to polling)...")
    try:
        result = telegram_client.delete_webhook()
        print("SUCCESS: Webhook deleted")
        print(f"Result: {result}")
    except Exception as e:
        print(f"ERROR: Failed to delete webhook: {e}")
        sys.exit(1)


def get_webhook_info():
    """Get current webhook information."""
    if not settings.telegram_bot_token:
        print("ERROR: TELEGRAM_BOT_TOKEN not configured in .env file")
        sys.exit(1)

    print("Getting bot info...")
    try:
        result = telegram_client.get_me()
        print("Bot info:")
        print(f"  Bot ID: {result.get('id')}")
        print(f"  Bot name: {result.get('first_name')}")
        print(f"  Bot username: @{result.get('username')}")
        print(f"  Can join groups: {result.get('can_join_groups')}")
        print(f"  Can read all group messages: {result.get('can_read_all_group_messages')}")
    except Exception as e:
        print(f"ERROR: Failed to get bot info: {e}")
        sys.exit(1)

    print("\nGetting webhook info...")
    try:
        result = telegram_client.get_webhook_info()
        print("Webhook info:")
        print(f"  URL: {result.get('url', 'Not set')}")
        print(f"  Has custom certificate: {result.get('has_custom_certificate', False)}")
        print(f"  Pending update count: {result.get('pending_update_count', 0)}")
        print(f"  Last error date: {result.get('last_error_date', 'None')}")
        print(f"  Last error message: {result.get('last_error_message', 'None')}")
    except Exception as e:
        print(f"ERROR: Failed to get webhook info: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Setup Telegram webhook")
    parser.add_argument(
        "--webhook-url",
        type=str,
        help="Full webhook URL (e.g., https://your-domain.com/api/v1/webhook/telegram)"
    )
    parser.add_argument(
        "--secret-token",
        type=str,
        default=None,
        help="Secret token for webhook verification (optional, will use TELEGRAM_WEBHOOK_SECRET_TOKEN from .env if not provided)"
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete webhook (switch back to polling)"
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Get current webhook and bot information"
    )

    args = parser.parse_args()

    if args.info:
        get_webhook_info()
    elif args.delete:
        delete_webhook()
    elif args.webhook_url:
        secret_token = args.secret_token or settings.telegram_webhook_secret_token
        setup_webhook(args.webhook_url, secret_token)
    else:
        parser.print_help()
        print("\nExample usage:")
        print("  python setup_webhook.py --webhook-url https://your-ngrok-url.ngrok-free.app/api/v1/webhook/telegram")
        print("  python setup_webhook.py --delete")
        print("  python setup_webhook.py --info")


if __name__ == "__main__":
    main()
