import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
from novora.core.enums import ConversationSource, MessageRole
from novora.core.exceptions import (
    PayloadSizeLimitError,
    PayloadValidationError,
)
from novora.core.models import Conversation, ConversationMessage

MAX_PAYLOAD_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_MESSAGES_COUNT = 1000
MAX_MESSAGE_CONTENT_LEN = 50000

ROLE_MAPPING = {
    "customer": MessageRole.CUSTOMER,
    "user": MessageRole.CUSTOMER,
    "caller": MessageRole.CUSTOMER,
    "client": MessageRole.CUSTOMER,
    "human": MessageRole.CUSTOMER,
    "agent": MessageRole.AGENT,
    "assistant": MessageRole.AGENT,
    "bot": MessageRole.AGENT,
    "ai": MessageRole.AGENT,
    "system": MessageRole.SYSTEM,
    "tool": MessageRole.TOOL,
}

class NeutralIngestionAdapter:
    """Validates and normalizes raw external transcript/conversation payloads

    into Novora's canonical Conversation model with strict security limits.
    """

    @classmethod
    def ingest(
        cls,
        payload: Dict[str, Any],
        scenario_id: Optional[str] = None,
        source: ConversationSource = ConversationSource.TRANSCRIPT_UPLOAD,
    ) -> Conversation:
        """Validates payload structure, checks security limits, and normalizes into Conversation."""
        # 1. Payload size check
        raw_json_str = json.dumps(payload)
        if len(raw_json_str.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise PayloadSizeLimitError(
                f"Payload size ({len(raw_json_str)} bytes) exceeds the maximum limit of {MAX_PAYLOAD_BYTES} bytes."
            )

        if not isinstance(payload, dict):
            raise PayloadValidationError("Payload must be a JSON object (dictionary).")

        raw_messages = payload.get("messages")
        if raw_messages is None:
            raise PayloadValidationError("Payload missing required 'messages' field.")

        if not isinstance(raw_messages, list):
            raise PayloadValidationError("'messages' field must be a list of turn records.")

        if len(raw_messages) > MAX_MESSAGES_COUNT:
            raise PayloadSizeLimitError(
                f"Message count ({len(raw_messages)}) exceeds maximum allowed limit of {MAX_MESSAGES_COUNT} messages."
            )

        conv_id = str(payload.get("conversation_id", payload.get("id", f"conv_{uuid4().hex[:8]}"))).strip()
        if not conv_id:
            conv_id = f"conv_{uuid4().hex[:8]}"

        normalized_messages: List[ConversationMessage] = []

        for idx, item in enumerate(raw_messages):
            if not isinstance(item, dict):
                raise PayloadValidationError(f"Message at index {idx} must be a JSON object.")

            raw_content = item.get("content", item.get("text", item.get("message")))
            if raw_content is None:
                raise PayloadValidationError(f"Message at index {idx} is missing content or text field.")

            content_str = str(raw_content).strip()
            if not content_str:
                raise PayloadValidationError(f"Message at index {idx} has empty content.")

            if len(content_str) > MAX_MESSAGE_CONTENT_LEN:
                raise PayloadSizeLimitError(
                    f"Message at index {idx} exceeds maximum content length of {MAX_MESSAGE_CONTENT_LEN} characters."
                )

            raw_role = str(item.get("role", item.get("speaker", "customer"))).strip().lower()
            role = ROLE_MAPPING.get(raw_role, MessageRole.CUSTOMER)

            # Sequence verification or safe assignment
            seq = item.get("sequence", idx)
            if not isinstance(seq, int) or seq < 0:
                seq = idx

            msg_id = str(item.get("id", f"msg_{idx:03d}"))

            # Safe timestamp handling
            timestamp_val: Optional[datetime] = None
            raw_ts = item.get("timestamp")
            if raw_ts:
                if isinstance(raw_ts, (int, float)):
                    # Unix timestamp
                    try:
                        timestamp_val = datetime.fromtimestamp(raw_ts, tz=timezone.utc)
                    except (ValueError, OSError):
                        timestamp_val = None
                elif isinstance(raw_ts, str):
                    try:
                        timestamp_val = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                    except ValueError:
                        timestamp_val = None

            # Retain non-standard source metadata safely
            metadata_dict = item.get("metadata", {})
            if not isinstance(metadata_dict, dict):
                metadata_dict = {}

            metadata_dict["raw_role"] = raw_role

            normalized_messages.append(
                ConversationMessage(
                    id=msg_id,
                    role=role,
                    content=content_str,
                    sequence=seq,
                    timestamp=timestamp_val,
                    metadata=metadata_dict,
                )
            )

        # Enforce sequence monotonicity
        normalized_messages.sort(key=lambda m: m.sequence)
        # Re-index if there were collisions or arbitrary sequence numbers
        for i, m in enumerate(normalized_messages):
            m.sequence = i

        trusted_actions = payload.get("trusted_action_records", [])
        if not isinstance(trusted_actions, list):
            trusted_actions = []

        return Conversation(
            id=conv_id,
            scenario_id=scenario_id or payload.get("scenario_id"),
            source=source,
            messages=normalized_messages,
            trusted_action_records=trusted_actions,
            metadata=payload.get("metadata", {}),
        )
