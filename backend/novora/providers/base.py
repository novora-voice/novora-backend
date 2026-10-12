from typing import Any, Dict, Protocol
from novora.core.models import Conversation, TelephonyCallRecord

class VoiceAgentProvider(Protocol):
    """Protocol for AI voice-agent platforms (e.g. ElevenLabs, Retell, Vapi)."""

    def parse_conversation_webhook(self, payload: Dict[str, Any]) -> Conversation:
        ...

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        signature: str,
        secret: str,
        timestamp: str = "",
    ) -> bool:
        ...

class TelephonyProvider(Protocol):
    """Protocol for telephony/carrier providers (e.g. Twilio)."""

    def parse_telephony_event(self, payload: Dict[str, Any]) -> TelephonyCallRecord:
        ...

    def verify_webhook_signature(
        self,
        url: str,
        params: Dict[str, str],
        signature: str,
        auth_token: str,
    ) -> bool:
        ...

class TranscriptionProvider(Protocol):
    """Protocol for speech-to-text / audio transcription providers (e.g. AssemblyAI)."""

    def parse_transcription_result(
        self,
        payload: Dict[str, Any],
        scenario_id: str = "",
    ) -> Conversation:
        ...
