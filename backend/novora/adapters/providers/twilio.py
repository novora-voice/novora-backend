import base64
import hashlib
import hmac
from typing import Any, Dict, Optional
from novora.core.models import TelephonyCallRecord
from novora.providers.base import TelephonyProvider

class TwilioAdapter(TelephonyProvider):
    """Adapter for Twilio telephony call-status and recording callbacks."""

    def verify_webhook_signature(
        self,
        url: str,
        params: Dict[str, str],
        signature: str,
        auth_token: str,
    ) -> bool:
        """Verifies Twilio's X-Twilio-Signature header using HMAC-SHA1 and URL + sorted POST params."""
        if not signature or not auth_token:
            return False

        # Twilio algorithm: URL + key1 + val1 + key2 + val2 (sorted by key)
        data = url
        for key in sorted(params.keys()):
            data += f"{key}{params[key]}"

        mac = hmac.new(
            auth_token.encode("utf-8"),
            data.encode("utf-8"),
            hashlib.sha1,
        )
        computed_sig = base64.b64encode(mac.digest()).decode("utf-8")
        return hmac.compare_digest(computed_sig, signature)

    def parse_telephony_event(self, payload: Dict[str, Any]) -> TelephonyCallRecord:
        """Parses Twilio webhook payload into a normalized TelephonyCallRecord."""
        call_sid = str(payload.get("CallSid", payload.get("call_sid", "")))
        from_num = payload.get("From", payload.get("Caller", payload.get("from_number")))
        to_num = payload.get("To", payload.get("Called", payload.get("to_number")))
        status = str(payload.get("CallStatus", payload.get("call_status", "unknown"))).lower()

        duration = None
        raw_dur = payload.get("CallDuration", payload.get("Duration", payload.get("RecordingDuration")))
        if raw_dur is not None:
            try:
                duration = int(raw_dur)
            except (ValueError, TypeError):
                duration = None

        rec_sid = payload.get("RecordingSid", payload.get("recording_sid"))
        rec_url = payload.get("RecordingUrl", payload.get("recording_url"))

        return TelephonyCallRecord(
            provider="twilio",
            call_sid=call_sid,
            from_number=str(from_num) if from_num else None,
            to_number=str(to_num) if to_num else None,
            call_status=status,
            duration_seconds=duration,
            recording_sid=str(rec_sid) if rec_sid else None,
            recording_url=str(rec_url) if rec_url else None,
            metadata={
                "account_sid": payload.get("AccountSid"),
                "direction": payload.get("Direction"),
                "api_version": payload.get("ApiVersion"),
                "raw_event": {k: v for k, v in payload.items() if k not in {"CallSid", "From", "To"}},
            },
        )
