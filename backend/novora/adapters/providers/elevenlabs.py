import hashlib
import hmac
import time
from typing import Any, Dict, List, Optional, Tuple
from novora.core.enums import ConversationSource, MessageRole
from novora.core.interfaces import WebhookEventRepository
from novora.core.models import Conversation, ConversationMessage, WebhookEventRecord
from novora.providers.base import VoiceAgentProvider

class ElevenLabsAdapter(VoiceAgentProvider):
    """Adapter for ElevenLabs Conversational AI post-call webhook ingestion and normalization."""

    def __init__(self, webhook_repo: Optional[WebhookEventRepository] = None) -> None:
        self.webhook_repo = webhook_repo

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        signature: str,
        secret: str,
        timestamp: str = "",
        max_drift_seconds: int = 300,
    ) -> bool:
        """Verifies HMAC-SHA256 signature for ElevenLabs webhooks.

        Supports both header formats:
        1. 't=1234567890,v1=abcdef...'
        2. Direct hex digest with optional timestamp argument
        """
        if not signature or not secret:
            return False

        header_ts = ""
        header_sig = signature.strip()

        if "t=" in signature and "v1=" in signature:
            parts = dict(item.split("=", 1) for item in signature.split(",") if "=" in item)
            header_ts = parts.get("t", "")
            header_sig = parts.get("v1", "")

        ts_to_use = header_ts or timestamp

        # Anti-replay check if timestamp is provided
        if ts_to_use:
            try:
                ts_int = int(ts_to_use)
                current_ts = int(time.time())
                if abs(current_ts - ts_int) > max_drift_seconds:
                    return False
            except ValueError:
                return False

        # Generate expected digest
        # ElevenLabs signature standard: HMAC-SHA256 of timestamp + '.' + body (or body alone if no ts)
        if ts_to_use:
            payload_to_sign = f"{ts_to_use}.".encode("utf-8") + raw_body
        else:
            payload_to_sign = raw_body

        expected = hmac.new(
            secret.encode("utf-8"),
            payload_to_sign,
            hashlib.sha256,
        ).hexdigest()

        # Compare constant-time
        return hmac.compare_digest(expected.lower(), header_sig.lower())

    def parse_conversation_webhook(
        self,
        payload: Dict[str, Any],
        scenario_id: Optional[str] = None,
    ) -> Conversation:
        """Normalizes ElevenLabs post-call conversation webhook into a Novora Conversation."""
        conv_id = str(payload.get("conversation_id", payload.get("id", "")))
        if not conv_id:
            conv_id = f"conv_el_{int(time.time())}"

        raw_transcript = payload.get("transcript", [])
        messages: List[ConversationMessage] = []

        for idx, turn in enumerate(raw_transcript):
            raw_role = str(turn.get("role", "")).lower()
            role = MessageRole.AGENT if raw_role in {"agent", "assistant", "bot"} else MessageRole.CUSTOMER
            content = str(turn.get("message", turn.get("text", ""))).strip()
            msg_id = str(turn.get("id", f"msg_el_{idx:03d}"))

            messages.append(
                ConversationMessage(
                    id=msg_id,
                    role=role,
                    content=content,
                    sequence=idx,
                    metadata={
                        "time_in_call_secs": turn.get("time_in_call_secs"),
                        "raw_role": raw_role,
                    },
                )
            )

        metadata = {
            "agent_id": payload.get("agent_id"),
            "call_duration_secs": payload.get("call_duration_secs"),
            "status": payload.get("status"),
            "analysis": payload.get("analysis", {}),
        }

        return Conversation(
            id=conv_id,
            scenario_id=scenario_id,
            source=ConversationSource.ELEVENLABS_WEBHOOK,
            messages=messages,
            metadata=metadata,
        )

    def process_webhook_idempotent(
        self,
        event_id: str,
        payload: Dict[str, Any],
        signature_verified: bool,
        scenario_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[Conversation]]:
        """Processes an ElevenLabs event idempotently.

        Returns: (is_duplicate: bool, normalized_conversation: Optional[Conversation])
        """
        if self.webhook_repo and self.webhook_repo.is_processed("elevenlabs", event_id):
            return True, None

        conv = self.parse_conversation_webhook(payload, scenario_id=scenario_id)

        if self.webhook_repo:
            self.webhook_repo.record_event(
                WebhookEventRecord(
                    provider="elevenlabs",
                    event_id=event_id,
                    signature_verified=signature_verified,
                    payload={"conversation_id": conv.id},
                    status="processed",
                )
            )

        return False, conv
