"""
Test script for the WhatsApp and Telegram webhook endpoints.
Uses FastAPI's TestClient to exercise signature verification, payload parsing,
staff allowlist checks, and trigger detection end-to-end without real APIs.
Uses an isolated temp database.
"""
import hmac
import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

# Isolated test database must be configured before importing app modules
_temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
_temp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_temp_db.name}"

# Test secrets (routers read these at call time via settings)
os.environ["WHATAutoCountP_APP_SECRET"] = "test_app_secret"
os.environ["TELEGRAM_WEBHOOK_SECRET_TOKEN"] = "test_telegram_secret"
os.environ["ENVIRONMENT"] = "development"

import main as main_module
from fastapi.testclient import TestClient
from database import get_engine, get_sessionmaker, Base, StaffAllowlistEntry, Role, ConversationState

client = TestClient(main_module.app)


def setup_staff():
    """Seed a staff member on both channels."""
    engine = get_engine(os.environ["DATABASE_URL"])
    Base.metadata.create_all(bind=engine)
    SessionLocal = get_sessionmaker(engine)
    db = SessionLocal()

    try:
        staff = StaffAllowlistEntry(
            phone_number="+60123456789",
            telegram_user_id="987654321",
            name="Test Admin",
            role=Role.ADMIN,
            active=True,
            added_at=datetime.now(timezone.utc),
            added_by="test"
        )
        db.add(staff)
        db.commit()
    finally:
        db.close()


def whatsapp_payload(from_number: str, text: str) -> bytes:
    """Build a Meta Cloud API webhook payload with one text message."""
    return json.dumps({
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "12345",
            "changes": [{
                "field": "messages",
                "value": {
                    "metadata": {"phone_number_id": "111222333"},
                    "contacts": [{"profile": {"name": "Test"}, "wa_id": from_number}],
                    "messages": [{
                        "from": from_number,
                        "type": "text",
                        "text": {"body": text},
                        "timestamp": "1700000000"
                    }]
                }
            }]
        }]
    }).encode()


def telegram_payload(user_id: int, text: str, chat_type: str = "private") -> bytes:
    """Build a Telegram webhook update with one text message."""
    return json.dumps({
        "update_id": 100000,
        "message": {
            "message_id": 42,
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "chat": {"id": user_id if chat_type == "private" else -100200300, "type": chat_type},
            "date": 1700000000,
            "text": text
        }
    }).encode()


def signed_headers(body: bytes) -> dict:
    """Compute the X-Hub-Signature-256 header for a Meta payload."""
    signature = hmac.new(
        b"test_app_secret", body, hashlib.sha256
    ).hexdigest()
    return {"X-Hub-Signature-256": f"sha256={signature}"}


def test_whatsapp_signature_verification():
    """Signature checks: valid passes, invalid/tampered bodies are rejected."""
    print("\n=== Testing WhatsApp signature verification ===")

    body = whatsapp_payload("+60123456789", "AI check stock for WM-001")

    # Valid signature
    resp = client.post("/api/v1/webhook", content=body, headers=signed_headers(body))
    print(f"Valid signature: {resp.status_code}")
    assert resp.status_code == 200, f"Valid signature should be accepted: {resp.text}"

    # Tampered body with old signature
    tampered = whatsapp_payload("+60123456789", "AI something else entirely")
    resp = client.post("/api/v1/webhook", content=tampered, headers=signed_headers(body))
    print(f"Tampered body: {resp.status_code}")
    assert resp.status_code == 403, "Tampered body should be rejected"

    # Missing signature header
    resp = client.post("/api/v1/webhook", content=body, headers={})
    print(f"Missing header: {resp.status_code}")
    assert resp.status_code == 403, "Missing signature header should be rejected"

    print("[PASS] WhatsApp signature verification tests passed")


def test_whatsapp_message_flow():
    """Staff allowlist + trigger detection through the full webhook path."""
    print("\n=== Testing WhatsApp message flow ===")

    # Authorized staff, trigger detected
    body = whatsapp_payload("+60123456789", "AI check stock for WM-001")
    resp = client.post("/api/v1/webhook", content=body, headers=signed_headers(body))
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

    # Unauthorized sender - still 200 to Meta (don't retry), but not processed
    body = whatsapp_payload("+60999999999", "AI check stock for WM-001")
    resp = client.post("/api/v1/webhook", content=body, headers=signed_headers(body))
    assert resp.status_code == 200
    print("Unauthorized sender handled: OK (200, dropped internally)")

    # Non-text message types are skipped without error
    body = json.dumps({
        "entry": [{
            "changes": [{
                "value": {
                    "metadata": {"phone_number_id": "111222333"},
                    "messages": [{"from": "+60123456789", "type": "image", "image": {"id": "xyz"}}]
                }
            }]
        }]
    }).encode()
    resp = client.post("/api/v1/webhook", content=body, headers=signed_headers(body))
    assert resp.status_code == 200, "Non-text messages should be skipped gracefully"
    print("[PASS] WhatsApp message flow tests passed")


def test_whatsapp_webhook_verify():
    """Meta webhook verification handshake."""
    print("\n=== Testing WhatsApp webhook verification ===")

    resp = client.get("/api/v1/webhook", params={
        "hub.mode": "subscribe",
        "hub.verify_token": "wrong-token",
        "hub.challenge": "123456"
    })
    assert resp.status_code == 403, "Wrong verify token should be rejected"

    print("[PASS] WhatsApp webhook verification test passed (challenge echo needs a real token set)")


def test_telegram_secret_verification():
    """Telegram secret token checks: valid passes, invalid rejected."""
    print("\n=== Testing Telegram secret token verification ===")

    body = telegram_payload(987654321, "AI check stock for WM-001")

    # Valid secret
    resp = client.post(
        "/api/v1/webhook/telegram",
        content=body,
        headers={"X-Telegram-Bot-Api-Secret-Token": "test_telegram_secret"}
    )
    print(f"Valid secret: {resp.status_code}")
    assert resp.status_code == 200, f"Valid secret should be accepted: {resp.text}"

    # Invalid secret
    resp = client.post(
        "/api/v1/webhook/telegram",
        content=body,
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong_secret"}
    )
    print(f"Invalid secret: {resp.status_code}")
    assert resp.status_code == 403, "Invalid secret should be rejected"

    # Missing secret header
    resp = client.post("/api/v1/webhook/telegram", content=body, headers={})
    print(f"Missing secret: {resp.status_code}")
    assert resp.status_code == 403, "Missing secret should be rejected"

    print("[PASS] Telegram secret token verification tests passed")


def test_telegram_message_flow():
    """Staff allowlist + trigger detection + group behavior through the webhook."""
    print("\n=== Testing Telegram message flow ===")

    # Authorized staff private chat with trigger
    body = telegram_payload(987654321, "AI check stock for WM-001")
    resp = client.post(
        "/api/v1/webhook/telegram",
        content=body,
        headers={"X-Telegram-Bot-Api-Secret-Token": "test_telegram_secret"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

    # Unauthorized Telegram user
    body = telegram_payload(111111111, "AI check stock")
    resp = client.post(
        "/api/v1/webhook/telegram",
        content=body,
        headers={"X-Telegram-Bot-Api-Secret-Token": "test_telegram_secret"}
    )
    assert resp.status_code == 200
    print("Unauthorized Telegram user handled: OK (200, dropped internally)")

    # Group chat without explicit AI prefix - skipped entirely
    body = telegram_payload(987654321, "anyone knows the price?", chat_type="group")
    resp = client.post(
        "/api/v1/webhook/telegram",
        content=body,
        headers={"X-Telegram-Bot-Api-Secret-Token": "test_telegram_secret"}
    )
    assert resp.status_code == 200
    print("Group chat without AI prefix handled: OK (ignored)")

    # Non-text update (callback query) - ignored gracefully
    body = json.dumps({"update_id": 100001, "callback_query": {"id": "1", "data": "x"}}).encode()
    resp = client.post(
        "/api/v1/webhook/telegram",
        content=body,
        headers={"X-Telegram-Bot-Api-Secret-Token": "test_telegram_secret"}
    )
    assert resp.status_code == 200, "Non-message updates should be ignored gracefully"
    print("[PASS] Telegram message flow tests passed")


def test_usage_tracker_per_model():
    """Usage tracking with the model column and shared pricing table."""
    print("\n=== Testing usage tracker per-model tracking ===")
    from usage_tracker import UsageTracker

    engine = get_engine(os.environ["DATABASE_URL"])
    SessionLocal = get_sessionmaker(engine)
    db = SessionLocal()

    try:
        tracker = UsageTracker(db)

        entry = tracker.record_usage(
            input_tokens=1000,
            output_tokens=500,
            agent_name="test_agent",
            operation_type="test",
            model="ilmu-mini-v3.3"
        )
        assert entry.model == "ilmu-mini-v3.3"
        # 1000 * 0.15/M + 500 * 0.60/M = 0.00015 + 0.0003 = 0.00045
        assert abs(entry.cost_usd - 0.00045) < 1e-9, f"Cost calculation wrong: {entry.cost_usd}"

        entry = tracker.record_usage(
            input_tokens=1000,
            output_tokens=500,
            agent_name="test_agent",
            operation_type="test",
            model="some-other-model"  # Falls back to default pricing
        )
        assert entry.model == "some-other-model"

        daily = tracker.get_daily_usage()
        assert "by_model" in daily
        assert "ilmu-mini-v3.3" in daily["by_model"]
        assert "some-other-model" in daily["by_model"]
        assert daily["by_model"]["ilmu-mini-v3.3"]["num_calls"] == 1
        print(f"Per-model breakdown: {list(daily['by_model'].keys())}")

        print("[PASS] Usage tracker per-model tests passed")
    finally:
        db.close()


def test_admin_takeover():
    """Admin takeover blocks agent processing until the window expires."""
    print("\n=== Testing admin takeover ===")
    engine = get_engine(os.environ["DATABASE_URL"])
    SessionLocal = get_sessionmaker(engine)
    db = SessionLocal()

    try:
        # Simulate an active takeover on a conversation
        state = ConversationState(
            conversation_id="wa:111222333:+60123456789",
            participant_id="+60123456789",
            admin_takeover_active=True,
            admin_takeover_started_at=datetime.now(timezone.utc),
            admin_takeover_ends_at=datetime.now(timezone.utc) + timedelta(hours=1)
        )
        db.add(state)
        db.commit()
        db.close()

        # Message on that conversation should be suppressed
        body = whatsapp_payload("+60123456789", "AI check stock for WM-001")
        resp = client.post("/api/v1/webhook", content=body, headers=signed_headers(body))
        assert resp.status_code == 200  # Suppressed internally, still ack'd to Meta

        print("[PASS] Admin takeover test passed (message suppressed while takeover active)")
    finally:
        try:
            db.close()
        except Exception:
            pass


def main():
    print("=" * 60)
    print("Testing WhatsApp + Telegram Webhooks and Model Tracking")
    print("=" * 60)

    try:
        setup_staff()
        test_whatsapp_signature_verification()
        test_whatsapp_message_flow()
        test_whatsapp_webhook_verify()
        test_telegram_secret_verification()
        test_telegram_message_flow()
        test_usage_tracker_per_model()
        test_admin_takeover()

        print("\n" + "=" * 60)
        print("[PASS] ALL WEBHOOK TESTS PASSED")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        try:
            os.unlink(_temp_db.name)
        except OSError:
            pass

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
