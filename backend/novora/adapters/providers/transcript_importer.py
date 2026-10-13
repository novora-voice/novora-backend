import re
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4
from novora.core.enums import ConversationSource, MessageRole
from novora.core.models import Conversation, ConversationMessage

ROLE_MAP = {
    "customer": MessageRole.CUSTOMER,
    "user": MessageRole.CUSTOMER,
    "caller": MessageRole.CUSTOMER,
    "client": MessageRole.CUSTOMER,
    "speaker 1": MessageRole.CUSTOMER,
    "speaker 2": MessageRole.AGENT,
    "speaker a": MessageRole.CUSTOMER,
    "speaker b": MessageRole.AGENT,
    "agent": MessageRole.AGENT,
    "assistant": MessageRole.AGENT,
    "bot": MessageRole.AGENT,
    "ai": MessageRole.AGENT,
    "system": MessageRole.SYSTEM,
}

class TranscriptImporter:
    """Parses raw text transcripts or structured payloads into normalized Conversation instances."""

    @classmethod
    def from_text(
        cls,
        text: str,
        scenario_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Conversation:
        """Parses multi-line dialogue text (e.g. 'Customer: ...\\nAgent: ...') into a Conversation."""
        conv_id = conversation_id or f"conv_import_{uuid4().hex[:8]}"
        lines = [line.strip() for line in text.strip().splitlines() if line.strip()]

        messages: List[ConversationMessage] = []
        seq = 0

        # Pattern for "Speaker: Message text"
        line_pattern = re.compile(r"^([A-Za-z0-9\s_-]+?)\s*:\s*(.+)$")

        for line in lines:
            match = line_pattern.match(line)
            if match:
                raw_speaker = match.group(1).strip().lower()
                content = match.group(2).strip()
                role = ROLE_MAP.get(raw_speaker, MessageRole.CUSTOMER)
            else:
                # If speaker prefix is absent, alternate between customer and agent starting with customer
                role = MessageRole.CUSTOMER if seq % 2 == 0 else MessageRole.AGENT
                content = line

            messages.append(
                ConversationMessage(
                    id=f"msg_{seq:03d}",
                    role=role,
                    content=content,
                    sequence=seq,
                )
            )
            seq += 1

        return Conversation(
            id=conv_id,
            scenario_id=scenario_id,
            source=ConversationSource.TRANSCRIPT_UPLOAD,
            messages=messages,
            metadata=metadata or {"imported_from": "text_dialogue"},
        )

    @classmethod
    def from_records(
        cls,
        records: List[Dict[str, Any]],
        scenario_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Conversation:
        """Parses a structured list of turn dictionaries."""
        conv_id = conversation_id or f"conv_rec_{uuid4().hex[:8]}"
        messages: List[ConversationMessage] = []

        for idx, rec in enumerate(records):
            raw_role = str(rec.get("role", rec.get("speaker", "customer"))).strip().lower()
            role = ROLE_MAP.get(raw_role, MessageRole.CUSTOMER)
            content = str(rec.get("content", rec.get("text", ""))).strip()
            msg_id = str(rec.get("id", f"msg_{idx:03d}"))

            messages.append(
                ConversationMessage(
                    id=msg_id,
                    role=role,
                    content=content,
                    sequence=idx,
                    timestamp=rec.get("timestamp"),
                    metadata=rec.get("metadata", {}),
                )
            )

        return Conversation(
            id=conv_id,
            scenario_id=scenario_id,
            source=ConversationSource.TRANSCRIPT_UPLOAD,
            messages=messages,
            metadata=metadata or {"imported_from": "structured_records"},
        )
