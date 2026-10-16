import re
from novora.core.enums import MessageRole, RuleStatus, RuleType
from novora.core.models import (
    Conversation,
    EvaluationScenario,
    RuleConfig,
    RuleResult,
)
from novora.evaluation.rules.base import BaseRule

class RequiredEscalationRule(BaseRule):
    """Verifies that the agent escalated to a human supervisor or tier 2 agent."""

    @property
    def rule_type(self) -> RuleType:
        return RuleType.REQUIRED_ESCALATION

    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        patterns = config.parameters.get("escalation_keywords", [
            "transfer you", "human agent", "supervisor", "representative", "escalat"
        ])
        agent_msgs = [m for m in conversation.messages if m.role == MessageRole.AGENT]

        for m in agent_msgs:
            for pat in patterns:
                if re.search(re.escape(pat), m.content, re.IGNORECASE):
                    return RuleResult(
                        rule_id=config.id,
                        rule_name=config.name or "Required Escalation",
                        rule_type=self.rule_type,
                        status=RuleStatus.PASS,
                        explanation="Agent properly escalated the conversation to a human representative.",
                        evidence=[self.message_as_evidence(m, note="Escalation utterance")],
                    )

        return RuleResult(
            rule_id=config.id,
            rule_name=config.name or "Required Escalation",
            rule_type=self.rule_type,
            status=RuleStatus.FAIL,
            explanation="Agent failed to escalate when escalation criteria were triggered.",
        )

class RequiredConfirmationRule(BaseRule):
    """Verifies agent asked for customer confirmation before taking an irreversible or sensitive action."""

    @property
    def rule_type(self) -> RuleType:
        return RuleType.REQUIRED_CONFIRMATION

    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        patterns = config.parameters.get("confirmation_patterns", [
            "would you like me to proceed", "can you confirm", "should i go ahead", "please confirm"
        ])
        agent_msgs = [m for m in conversation.messages if m.role == MessageRole.AGENT]

        for m in agent_msgs:
            for pat in patterns:
                if re.search(re.escape(pat), m.content, re.IGNORECASE):
                    return RuleResult(
                        rule_id=config.id,
                        rule_name=config.name or "Required Confirmation",
                        rule_type=self.rule_type,
                        status=RuleStatus.PASS,
                        explanation="Agent verified user confirmation prior to taking action.",
                        evidence=[self.message_as_evidence(m)],
                    )

        return RuleResult(
            rule_id=config.id,
            rule_name=config.name or "Required Confirmation",
            rule_type=self.rule_type,
            status=RuleStatus.FAIL,
            explanation="Agent proceeded without obtaining explicit customer confirmation.",
        )

class TurnConstraintsRule(BaseRule):
    """Enforces minimum and maximum turn limits."""

    @property
    def rule_type(self) -> RuleType:
        return RuleType.TURN_CONSTRAINTS

    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        min_turns = config.parameters.get("min_turns", 1)
        max_turns = config.parameters.get("max_turns", 50)
        actual = len(conversation.messages)

        if actual < min_turns:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Turn Constraints Check",
                rule_type=self.rule_type,
                status=RuleStatus.FAIL,
                explanation=f"Conversation had {actual} turns, below required minimum of {min_turns}.",
            )
        if actual > max_turns:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Turn Constraints Check",
                rule_type=self.rule_type,
                status=RuleStatus.FAIL,
                explanation=f"Conversation exceeded maximum limit: {actual} turns > {max_turns}.",
            )

        return RuleResult(
            rule_id=config.id,
            rule_name=config.name or "Turn Constraints Check",
            rule_type=self.rule_type,
            status=RuleStatus.PASS,
            explanation=f"Turn count ({actual}) within valid bounds [{min_turns}, {max_turns}].",
        )

class EvidenceAvailabilityRule(BaseRule):
    """Checks that conversation evidence is complete; returns INCONCLUSIVE if missing."""

    @property
    def rule_type(self) -> RuleType:
        return RuleType.EVIDENCE_AVAILABILITY

    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        if not conversation.messages:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Evidence Availability Check",
                rule_type=self.rule_type,
                status=RuleStatus.INCONCLUSIVE,
                explanation="No conversation messages available to evaluate.",
            )
        return RuleResult(
            rule_id=config.id,
            rule_name=config.name or "Evidence Availability Check",
            rule_type=self.rule_type,
            status=RuleStatus.PASS,
            explanation=f"Evidence complete with {len(conversation.messages)} message(s).",
        )
