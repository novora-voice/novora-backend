import re
from typing import List
from novora.core.models import Conversation

class UntrustedTranscriptSanitizer:
    """Sanitizes untrusted transcript text and defends against prompt injection."""

    ADVERSARIAL_PATTERNS = [
        re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
        re.compile(r"system\s*:\s*", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+(in|a)\s+", re.IGNORECASE),
        re.compile(r"override\s+system\s+prompt", re.IGNORECASE),
        re.compile(r"<\/?(system|instruction|prompt)>", re.IGNORECASE),
    ]

    @classmethod
    def sanitize_text(cls, text: str) -> str:
        sanitized = text
        for pat in cls.ADVERSARIAL_PATTERNS:
            sanitized = pat.sub("[SANITIZED_INSTRUCTION]", sanitized)
        # Escape XML-like delimiters
        sanitized = sanitized.replace("<", "&lt;").replace(">", "&gt;")
        return sanitized

    @classmethod
    def format_untrusted_transcript(cls, conversation: Conversation) -> str:
        lines: List[str] = [
            "<untrusted_conversation_evidence>",
            f"<conversation_id>{conversation.id}</conversation_id>",
        ]
        for msg in conversation.messages:
            safe_content = cls.sanitize_text(msg.content)
            lines.append(
                f'  <turn speaker="{msg.role.value}" seq="{msg.sequence}">{safe_content}</turn>'
            )
        lines.append("</untrusted_conversation_evidence>")
        return "\n".join(lines)
