import hashlib
import hmac
import time
from novora.adapters.providers.elevenlabs import ElevenLabsAdapter
from novora.adapters.repositories import InMemoryWebhookEventRepository
from novora.core.enums import ConversationSource, MessageRole

def generate_elevenlabs_signature(secret: str, body: bytes, timestamp: str) -> str:
    payload = f"{timestamp}.".encode("utf-8") + body
    sig_hex = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig_hex}"

def test_elevenlabs_signature_verification():
    adapter = ElevenLabsAdapter()
    secret = "secret_key_12345"
    body = b'{"conversation_id": "conv_el_1"}'
    ts = str(int(time.time()))

    valid_sig = generate_elevenlabs_signature(secret, body, ts)
    assert adapter.verify_webhook_signature(body, valid_sig, secret) is True

    # Bad signature
    assert adapter.verify_webhook_signature(body, "t=123,v1=bad_signature", secret) is False

    # Expired timestamp (timestamp older than 300 seconds)
    old_ts = str(int(time.time()) - 500)
    old_sig = generate_elevenlabs_signature(secret, body, old_ts)
    assert adapter.verify_webhook_signature(body, old_sig, secret) is False

def test_elevenlabs_payload_normalization():
    adapter = ElevenLabsAdapter()
    payload = {
        "conversation_id": "conv_el_9988",
        "agent_id": "agent_voice_pro",
        "call_duration_secs": 45,
        "transcript": [
            {"role": "user", "message": "Where is my refund for #5512?", "time_in_call_secs": 2},
            {"role": "agent", "message": "I am reviewing your refund request.", "time_in_call_secs": 6},
        ],
    }

    conv = adapter.parse_conversation_webhook(payload, scenario_id="scen_refund")
    assert conv.id == "conv_el_9988"
    assert conv.source == ConversationSource.ELEVENLABS_WEBHOOK
    assert conv.scenario_id == "scen_refund"
    assert len(conv.messages) == 2

    assert conv.messages[0].role == MessageRole.CUSTOMER
    assert conv.messages[0].content == "Where is my refund for #5512?"
    assert conv.messages[0].sequence == 0

    assert conv.messages[1].role == MessageRole.AGENT
    assert conv.messages[1].content == "I am reviewing your refund request."
    assert conv.messages[1].sequence == 1

def test_elevenlabs_idempotency_deduplication():
    webhook_repo = InMemoryWebhookEventRepository()
    adapter = ElevenLabsAdapter(webhook_repo=webhook_repo)
    payload = {
        "conversation_id": "conv_el_unique_01",
        "transcript": [{"role": "user", "message": "Hello"}],
    }

    # First event
    is_dup, conv = adapter.process_webhook_idempotent(
        event_id="conv_el_unique_01",
        payload=payload,
        signature_verified=True,
    )
    assert is_dup is False
    assert conv is not None
    assert conv.id == "conv_el_unique_01"

    # Repeated event with identical event_id
    is_dup_second, conv_second = adapter.process_webhook_idempotent(
        event_id="conv_el_unique_01",
        payload=payload,
        signature_verified=True,
    )
    assert is_dup_second is True
    assert conv_second is None
