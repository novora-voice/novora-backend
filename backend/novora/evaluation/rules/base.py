import re
from abc import ABC, abstractmethod
from typing import List, Optional
from novora.core.enums import MessageRole, RuleStatus, RuleType
from novora.core.models import (
    Conversation,
    ConversationMessage,
    EvaluationScenario,
    EvidenceReference,
    RuleConfig,
    RuleResult,
)

class BaseRule(ABC):
    """Abstract base class for deterministic rule evaluators."""

    @property
    @abstractmethod
    def rule_type(self) -> RuleType:
        """The rule type this evaluator handles."""
        pass

    @abstractmethod
    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        """Evaluate the rule against the conversation deterministically."""
        pass

    def extract_evidence(
        self,
        message: ConversationMessage,
        match: re.Match,
        note: Optional[str] = None,
    ) -> EvidenceReference:
        """Helper to create an EvidenceReference from a regex match."""
        return EvidenceReference(
            message_id=message.id,
            speaker=message.role,
            sequence=message.sequence,
            char_start=match.start(),
            char_end=match.end(),
            snippet=message.content[max(0, match.start() - 20) : min(len(message.content), match.end() + 20)].strip(),
            note=note,
        )

    def message_as_evidence(
        self,
        message: ConversationMessage,
        note: Optional[str] = None,
    ) -> EvidenceReference:
        """Helper to create an EvidenceReference for an entire message."""
        return EvidenceReference(
            message_id=message.id,
            speaker=message.role,
            sequence=message.sequence,
            char_start=0,
            char_end=len(message.content),
            snippet=message.content[:120].strip(),
            note=note,
        )
