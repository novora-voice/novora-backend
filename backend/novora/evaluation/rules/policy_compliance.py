import re
from typing import Optional
from novora.core.enums import MessageRole, RuleStatus, RuleType
from novora.core.models import (
    Conversation,
    EvaluationScenario,
    RuleConfig,
    RuleResult,
)
from novora.evaluation.rules.base import BaseRule

class PolicyComplianceRule(BaseRule):
    """Rule 6: Evaluates concrete machine-checkable operational policies

    (e.g., maximum refund amount, approval thresholds).
    """

    @property
    def rule_type(self) -> RuleType:
        return RuleType.POLICY_COMPLIANCE

    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        max_refund = config.parameters.get("max_refund_amount")
        amount_regex = config.parameters.get("amount_regex", r"\$(\d+(?:\.\d{2})?)")

        if max_refund is None:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Policy Compliance Verification",
                rule_type=self.rule_type,
                status=RuleStatus.PASS,
                explanation="No specific quantitative policy limits configured.",
                evidence=[],
            )

        regex = re.compile(amount_regex)
        detected_amount: Optional[float] = None
        evidence_item = None

        for msg in conversation.messages:
            if msg.role == MessageRole.AGENT:
                m = regex.search(msg.content)
                if m:
                    try:
                        detected_amount = float(m.group(1))
                        evidence_item = self.extract_evidence(
                            msg,
                            m,
                            note=f"Detected financial amount offered: ${detected_amount:.2f}",
                        )
                        break
                    except (ValueError, IndexError):
                        continue

        if detected_amount is None:
            # Policy check was configured, but no monetary amount was stated in dialogue
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Policy Compliance Verification",
                rule_type=self.rule_type,
                status=RuleStatus.INCONCLUSIVE,
                explanation=(
                    f"Policy limits refunds to ${max_refund:.2f}, but no monetary amount "
                    "could be extracted from the agent's statements."
                ),
                evidence=[],
                details={"max_refund_limit": max_refund, "detected_amount": None},
            )

        if detected_amount <= float(max_refund):
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Policy Compliance Verification",
                rule_type=self.rule_type,
                status=RuleStatus.PASS,
                explanation=f"Offered amount (${detected_amount:.2f}) complies with policy limit of ${max_refund:.2f}.",
                evidence=[evidence_item] if evidence_item else [],
                details={"max_refund_limit": max_refund, "detected_amount": detected_amount},
            )
        else:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Policy Compliance Verification",
                rule_type=self.rule_type,
                status=RuleStatus.FAIL,
                explanation=(
                    f"Offered amount (${detected_amount:.2f}) violates policy limit "
                    f"of ${max_refund:.2f} without manager authorization."
                ),
                evidence=[evidence_item] if evidence_item else [],
                details={"max_refund_limit": max_refund, "detected_amount": detected_amount},
            )
