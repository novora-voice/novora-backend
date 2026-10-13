from typing import Any, Dict, List, Optional
from uuid import uuid4
from novora.core.enums import ConversationSource, MessageRole
from novora.core.models import Conversation, ConversationMessage
from novora.providers.base import VoiceAgentProvider
from novora.providers.capabilities import ProviderCapability, get_provider_manifest

class VapiAdapter(VoiceAgentProvider):
    """Adapter for Vapi voice-agent post-call webhook ingestion and normalization."""

    def __init__(self) -> None:
        self.manifest = get_provider_manifest("vapi")

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        signature: str,
        secret: str,
        timestamp: str = "",
    ) -> bool:
        # Vapi does not use standard HMAC header; uses secret bearer or header token
        return bool(signature and secret and signature == secret)

    def parse_conversation_webhook(
        self,
        payload: Dict[str, Any],
        scenario_id: Optional[str] = None,
    ) -> Conversation:
        """Parses Vapi end-of-call report or assistant conversation payload."""
        self.manifest.assert_supports(ProviderCapability.POST_CALL_TRANSCRIPT_WEBHOOK)

        message_obj = payload.get("message", payload)
        call_obj = message_obj.get("call", {})
        call_id = str(call_obj.get("id", payload.get("call_id", f"conv_vapi_{uuid4().hex[:8]}")))

        raw_messages = message_obj.get("messages", message_obj.get("transcript", []))
        normalized_messages: List[ConversationMessage] = []
        trusted_records: List[Dict[str, Any]] = []

        if isinstance(raw_messages, list):
            seq = 0
            for item in raw_messages:
                if not isinstance(item, dict):
                    continue

                raw_role = str(item.get("role", "")).lower()
                content = str(item.get("message", item.get("content", ""))).strip()

                if raw_role in {"user", "customer"}:
                    role = MessageRole.CUSTOMER
                elif raw_role in {"assistant", "bot"}:
                    role = MessageRole.AGENT
                elif raw_role == "tool_call_result":
                    role = MessageRole.TOOL
                    # Record tool results as potential trusted action records
                    tool_name = item.get("toolName", item.get("name", "tool"))
                    trusted_records.append({
                        "action_type": tool_name,
                        "status": "completed" if item.get("result") else "unknown",
                        "details": item.get("result"),
                    })
                else:
                    role = MessageRole.AGENT

                if content:
                    normalized_messages.append(
                        ConversationMessage(
                            id=f"msg_vapi_{seq:03d}",
                            role=role,
                            content=content,
                            sequence=seq,
                            metadata={"raw_role": raw_role, "secondsFromStart": item.get("secondsFromStart")},
                        )
                    )
                    seq += 1

        metadata = {
            "vapi_call_id": call_id,
            "cost": message_obj.get("cost"),
            "duration": message_obj.get("duration"),
            "ended_reason": message_obj.get("endedReason"),
        }

        return Conversation(
            id=call_id,
            scenario_id=scenario_id,
            source=ConversationSource.VAPI_WEBHOOK,
            messages=normalized_messages,
            trusted_action_records=trusted_records,
            metadata=metadata,
        )
