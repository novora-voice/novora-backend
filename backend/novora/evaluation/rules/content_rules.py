import re
from typing import List
from novora.core.enums import MessageRole, RuleStatus, RuleType
from novora.core.models import (
    Conversation,
    EvaluationScenario,
    EvidenceReference,
    RuleConfig,
    RuleResult,
)
from novora.evaluation.rules.base import BaseRule

class RequiredPhraseRule(BaseRule):
    """Checks that the agent uttered required phrases or regex concepts."""

    @property
    def rule_type(self) -> RuleType:
        return RuleType.REQUIRED_PHRASE

    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        phrases = config.parameters.get("phrases", [])
        case_sensitive = config.parameters.get("case_sensitive", False)
        flags = 0 if case_sensitive else re.IGNORECASE

        agent_messages = [m for m in conversation.messages if m.role == MessageRole.AGENT]
        if not agent_messages:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Required Phrase Check",
                rule_type=self.rule_type,
                status=RuleStatus.INCONCLUSIVE,
                explanation="No agent messages present to evaluate.",
                evidence=[],
            )

        missing = []
        evidence: List[EvidenceReference] = []

        for p in phrases:
            matched = False
            for m in agent_messages:
                match = re.search(re.escape(p), m.content, flags)
                if match:
                    evidence.append(self.extract_evidence(m, match, note=f"Found phrase '{p}'"))
                    matched = True
                    break
            if not matched:
                missing.append(p)

        if missing:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Required Phrase Check",
                rule_type=self.rule_type,
                status=RuleStatus.FAIL,
                explanation=f"Missing required phrase(s): {', '.join(missing)}",
                evidence=evidence,
            )

        return RuleResult(
            rule_id=config.id,
            rule_name=config.name or "Required Phrase Check",
            rule_type=self.rule_type,
            status=RuleStatus.PASS,
            explanation="All required phrases were spoken by the agent.",
            evidence=evidence,
        )

class ProhibitedPhraseRule(BaseRule):
    """Checks that the agent did not utter forbidden words or make unauthorized commitments."""

    @property
    def rule_type(self) -> RuleType:
        return RuleType.PROHIBITED_PHRASE

    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        prohibited = config.parameters.get("prohibited_patterns", [])
        evidence: List[EvidenceReference] = []

        for m in conversation.messages:
            if m.role == MessageRole.AGENT:
                for pat in prohibited:
                    match = re.search(re.escape(pat), m.content, re.IGNORECASE)
                    if match:
                        evidence.append(
                            self.extract_evidence(m, match, note=f"Prohibited pattern '{pat}' detected")
                        )

        if evidence:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Prohibited Phrase Check",
                rule_type=self.rule_type,
                status=RuleStatus.FAIL,
                explanation=f"Agent uttered {len(evidence)} prohibited phrase(s).",
                evidence=evidence,
            )

        return RuleResult(
            rule_id=config.id,
            rule_name=config.name or "Prohibited Phrase Check",
            rule_type=self.rule_type,
            status=RuleStatus.PASS,
            explanation="No prohibited phrases or unauthorized claims detected.",
            evidence=[],
        )

class RequiredQuestionRule(BaseRule):
    """Ensures the agent asked specific clarifying questions."""

    @property
    def rule_type(self) -> RuleType:
        return RuleType.REQUIRED_QUESTION

    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        questions = config.parameters.get("questions", [])
        agent_msgs = [m for m in conversation.messages if m.role == MessageRole.AGENT]
        missing = []
        evidence: List[EvidenceReference] = []

        for q in questions:
            found = False
            for m in agent_msgs:
                if re.search(re.escape(q), m.content, re.IGNORECASE):
                    evidence.append(self.message_as_evidence(m, note=f"Asked: '{q}'"))
                    found = True
                    break
            if not found:
                missing.append(q)

        if missing:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Required Question Check",
                rule_type=self.rule_type,
                status=RuleStatus.FAIL,
                explanation=f"Agent failed to ask required question(s): {', '.join(missing)}",
                evidence=evidence,
            )

        return RuleResult(
            rule_id=config.id,
            rule_name=config.name or "Required Question Check",
            rule_type=self.rule_type,
            status=RuleStatus.PASS,
            explanation="All required clarifying questions were asked.",
            evidence=evidence,
        )

class RequiredClosingRule(BaseRule):
    """Checks that the agent provided proper closing or next steps."""

    @property
    def rule_type(self) -> RuleType:
        return RuleType.REQUIRED_CLOSING

    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        expected = config.parameters.get("closing_patterns", ["have a great day", "thank you", "anything else", "take care"])
        agent_msgs = [m for m in conversation.messages if m.role == MessageRole.AGENT]
        if not agent_msgs:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Required Closing Check",
                rule_type=self.rule_type,
                status=RuleStatus.INCONCLUSIVE,
                explanation="No agent messages to check for closing.",
                evidence=[],
            )

        last_agent_msg = agent_msgs[-1]
        for pat in expected:
            if re.search(re.escape(pat), last_agent_msg.content, re.IGNORECASE):
                return RuleResult(
                    rule_id=config.id,
                    rule_name=config.name or "Required Closing Check",
                    rule_type=self.rule_type,
                    status=RuleStatus.PASS,
                    explanation="Agent provided polite closing and next steps.",
                    evidence=[self.message_as_evidence(last_agent_msg, note=f"Closing phrase: '{pat}'")],
                )

        return RuleResult(
            rule_id=config.id,
            rule_name=config.name or "Required Closing Check",
            rule_type=self.rule_type,
            status=RuleStatus.FAIL,
            explanation="Conversation ended abruptly without clear closing or next steps.",
            evidence=[self.message_as_evidence(last_agent_msg, note="Last agent utterance")],
        )
