import base64
import hashlib
import hmac
from novora.adapters.providers.twilio import TwilioAdapter

def generate_twilio_signature(url: str, params: dict, auth_token: str) -> str:
    data = url
    for k in sorted(params.keys()):
        data += f"{k}{params[k]}"
    mac = hmac.new(auth_token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode("utf-8")

def test_twilio_signature_verification():
    adapter = TwilioAdapter()
    url = "https://api.novora.ai/api/v1/webhooks/twilio"
    params = {"CallSid": "CA1234567890", "CallStatus": "completed"}
    token = "auth_token_secret_xyz"

    sig = generate_twilio_signature(url, params, token)
    assert adapter.verify_webhook_signature(url, params, sig, token) is True
    assert adapter.verify_webhook_signature(url, params, "invalid_sig", token) is False

def test_twilio_telephony_event_normalization():
    adapter = TwilioAdapter()
    payload = {
        "CallSid": "CA9988776655",
        "From": "+15551234567",
        "To": "+15559876543",
        "CallStatus": "completed",
        "CallDuration": "128",
        "RecordingSid": "RE11223344",
        "RecordingUrl": "https://api.twilio.com/recordings/RE11223344.wav",
        "AccountSid": "AC00112233",
    }

    record = adapter.parse_telephony_event(payload)
    assert record.provider == "twilio"
    assert record.call_sid == "CA9988776655"
    assert record.from_number == "+15551234567"
    assert record.to_number == "+15559876543"
    assert record.call_status == "completed"
    assert record.duration_seconds == 128
    assert record.recording_sid == "RE11223344"
    assert record.recording_url == "https://api.twilio.com/recordings/RE11223344.wav"
    assert record.metadata["account_sid"] == "AC00112233"
