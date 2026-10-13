from typing import Any, Dict, List, Optional
from uuid import uuid4
from novora.core.enums import ConversationSource, MessageRole
from novora.core.models import Conversation, ConversationMessage
from novora.providers.base import VoiceAgentProvider
from novora.providers.capabilities import ProviderCapability, get_provider_manifest

class RetellAdapter(VoiceAgentProvider):
    """Adapter for Retell AI voice-agent post-call webhook normalization."""

    def __init__(self) -> None:
        self.manifest = get_provider_manifest("retell")

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        signature: str,
        secret: str,
        timestamp: str = "",
    ) -> bool:
        # Retell does not natively publish a webhook signature verification algorithm; uses auth header or bearer
        return bool(signature and secret and signature == secret)

    def parse_conversation_webhook(
        self,
        payload: Dict[str, Any],
        scenario_id: Optional[str] = None,
    ) -> Conversation:
        """Parses Retell call_analyzed or call_ended webhook."""
        self.manifest.assert_supports(ProviderCapability.POST_CALL_TRANSCRIPT_WEBHOOK)

        call_id = str(payload.get("call_id", f"conv_retell_{uuid4().hex[:8]}"))
        raw_turns = payload.get("transcript_object", payload.get("transcript", []))

        messages: List[ConversationMessage] = []

        if isinstance(raw_turns, list):
            for idx, turn in enumerate(raw_turns):
                if not isinstance(turn, dict):
                    continue

                raw_role = str(turn.get("role", "")).lower()
                role = MessageRole.AGENT if raw_role in {"agent", "assistant"} else MessageRole.CUSTOMER
                content = str(turn.get("content", turn.get("text", ""))).strip()

                messages.append(
                    ConversationMessage(
                        id=f"msg_retell_{idx:03d}",
                        role=role,
                        content=content,
                        sequence=idx,
                        metadata={
                            "words_count": len(turn.get("words", [])),
                            "raw_role": raw_role,
                        },
                    )
                )

        metadata = {
            "retell_call_id": call_id,
            "agent_id": payload.get("agent_id"),
            "call_status": payload.get("call_status"),
            "latency": payload.get("latency"),
            "call_analysis": payload.get("call_analysis", {}),
        }

        return Conversation(
            id=call_id,
            scenario_id=scenario_id,
            source=ConversationSource.RETELL_WEBHOOK,
            messages=messages,
            metadata=metadata,
        )
