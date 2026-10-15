from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
from novora.core.enums import ConversationSource, MessageRole
from novora.core.execution_models import (
    NormalizedProviderEvent,
    TestRun,
    ToolCallRecord,
)
from novora.core.models import Conversation, ConversationMessage

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class EventNormalizer:
    """Normalizes raw provider events into Novora Conversation and trusted records."""

    @staticmethod
    def events_to_conversation(
        events: List[NormalizedProviderEvent],
        scenario_id: Optional[str] = None,
        provider_name: str = "custom",
    ) -> Conversation:
        conv_id = f"conv_{uuid4().hex[:8]}"
        messages: List[ConversationMessage] = []
        trusted_actions: List[Dict[str, Any]] = []
        seq = 0

        for evt in sorted(events, key=lambda e: e.sequence):
            etype = evt.event_type.lower()
            payload = evt.payload

            # ElevenLabs / AssemblyAI / Vapi / Retell transcript events
            if etype in ("user_transcript", "transcript.user", "speech-update", "transcript_utterance"):
                role_val = payload.get("role")
                if role_val == "assistant" or role_val == "agent":
                    role = MessageRole.AGENT
                    content = payload.get("text") or payload.get("content") or payload.get("agent_response", "")
                else:
                    role = MessageRole.CUSTOMER
                    content = payload.get("message") or payload.get("text") or payload.get("content", "")

                if content:
                    messages.append(
                        ConversationMessage(
                            id=f"msg_{seq}",
                            role=role,
                            content=content,
                            sequence=seq,
                            timestamp=evt.timestamp,
                        )
                    )
                    seq += 1

            elif etype in ("agent_response", "transcript.agent"):
                content = payload.get("agent_response") or payload.get("text") or payload.get("content", "")
                if content:
                    messages.append(
                        ConversationMessage(
                            id=f"msg_{seq}",
                            role=MessageRole.AGENT,
                            content=content,
                            sequence=seq,
                            timestamp=evt.timestamp,
                        )
                    )
                    seq += 1

            # Tool result events mapped to trusted action records
            elif etype in ("client_tool_result", "tool.result", "tool-result", "tool_response"):
                res = payload.get("result") or payload.get("output", {})
                if isinstance(res, dict) and not res.get("error"):
                    trusted_actions.append({
                        "action_type": payload.get("tool_name") or "executed_tool",
                        "call_id": payload.get("call_id"),
                        "result": res,
                        "timestamp": evt.timestamp.isoformat(),
                    })

        source_map = {
            "elevenlabs": ConversationSource.ELEVENLABS_WEBHOOK,
            "assemblyai": ConversationSource.ASSEMBLYAI_WEBHOOK,
            "vapi": ConversationSource.VAPI_WEBHOOK,
            "retell": ConversationSource.RETELL_WEBHOOK,
        }
        src = source_map.get(provider_name.lower(), ConversationSource.SYNTHETIC_FIXTURE)

        return Conversation(
            id=conv_id,
            scenario_id=scenario_id,
            source=src,
            messages=messages,
            trusted_action_records=trusted_actions,
            metadata={"normalized_event_count": len(events), "provider": provider_name},
            created_at=utc_now(),
        )
