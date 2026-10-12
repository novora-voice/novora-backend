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

DEFAULT_RESOLUTION_PATTERNS = [
    r"(?:ticket|case|reference)\s+(?:#|id|number)?\s*[:\s]?\s*[a-zA-Z0-9_-]+",
    r"(?:escalated|transferred|forwarded)\s+(?:to\s+)?(?:a\s+)?(?:specialist|manager|supervisor|human|team)",
    r"(?:we have|i have)\s+(?:submitted|resolved|completed|logged)\s+(?:your\s+)?(?:request|ticket|issue)",
    r"(?:you will receive|sent you)\s+(?:a\s+)?(?:confirmation|email|sms|update)",
    r"(?:is there anything else|happy to help|glad we could solve)",
]

DEFAULT_DANGLING_PATTERNS = [
    r"(?:wait|still waiting|nobody answered|you didn'?t help|not resolved|still don'?t know)",
    r"(?:hello\?|are you still there|didn'?t get an answer)",
]

class UnresolvedWorkRule(BaseRule):
    """Rule 5: Verifies that customer inquiries end with concrete resolution or escalation

    rather than dangling unresolved work.
    """

    @property
    def rule_type(self) -> RuleType:
        return RuleType.UNRESOLVED_WORK

    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        resolution_patterns = config.parameters.get("resolution_patterns", DEFAULT_RESOLUTION_PATTERNS)
        dangling_patterns = config.parameters.get("dangling_patterns", DEFAULT_DANGLING_PATTERNS)

        if not conversation.messages:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Unresolved Work Verification",
                rule_type=self.rule_type,
                status=RuleStatus.FAIL,
                explanation="Conversation is empty; no work was completed.",
                evidence=[],
            )

        # Check if the customer's last message indicates an unresolved issue
        last_customer_msg = None
        for msg in reversed(conversation.messages):
            if msg.role == MessageRole.CUSTOMER:
                last_customer_msg = msg
                break

        if last_customer_msg:
            for dang_p in dangling_patterns:
                m = re.search(dang_p, last_customer_msg.content, re.IGNORECASE)
                if m:
                    ev = self.extract_evidence(
                        last_customer_msg,
                        m,
                        note="Customer terminated call with unresolved frustration or confusion",
                    )
                    return RuleResult(
                        rule_id=config.id,
                        rule_name=config.name or "Unresolved Work Verification",
                        rule_type=self.rule_type,
                        status=RuleStatus.FAIL,
                        explanation="Conversation ended with explicit customer dissatisfaction or unresolved confusion.",
                        evidence=[ev],
                    )

        # Check if agent provided a resolution or escalation signal
        resolution_evidence: List[EvidenceReference] = []
        compiled_res = [re.compile(p, re.IGNORECASE) for p in resolution_patterns]

        for msg in conversation.messages:
            if msg.role == MessageRole.AGENT:
                for regex in compiled_res:
                    m = regex.search(msg.content)
                    if m:
                        resolution_evidence.append(
                            self.extract_evidence(
                                msg,
                                m,
                                note="Resolution, escalation, or handoff confirmed",
                            )
                        )
                        break

        if resolution_evidence:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Unresolved Work Verification",
                rule_type=self.rule_type,
                status=RuleStatus.PASS,
                explanation="Work concluded with verified resolution, formal escalation, or confirmed follow-up.",
                evidence=resolution_evidence[:2],
            )

        # No resolution signals found in agent messages
        last_msg = conversation.messages[-1]
        ev = self.message_as_evidence(last_msg, note="Conversation ended without confirmed resolution")
        return RuleResult(
            rule_id=config.id,
            rule_name=config.name or "Unresolved Work Verification",
            rule_type=self.rule_type,
            status=RuleStatus.FAIL,
            explanation="Conversation concluded without a detectable resolution, ticket creation, or escalation.",
            evidence=[ev],
        )
