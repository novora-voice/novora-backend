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

class ProhibitedClaimsRule(BaseRule):
    """Rule 3: Detects prohibited phrases or unauthorized promises made by the agent."""

    @property
    def rule_type(self) -> RuleType:
        return RuleType.PROHIBITED_CLAIMS

    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        patterns = config.parameters.get("prohibited_patterns", [])
        target_role = config.parameters.get("target_role", MessageRole.AGENT)

        if not patterns:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Prohibited Claims Detection",
                rule_type=self.rule_type,
                status=RuleStatus.PASS,
                explanation="No prohibited claim patterns configured.",
                evidence=[],
            )

        violations: List[EvidenceReference] = []
        violation_descriptions: List[str] = []

        compiled_patterns = [(p, re.compile(p if isinstance(p, str) else str(p), re.IGNORECASE)) for p in patterns]

        for msg in conversation.messages:
            if target_role and msg.role != target_role:
                continue

            for raw_pattern, regex in compiled_patterns:
                for match in regex.finditer(msg.content):
                    ev = self.extract_evidence(
                        msg,
                        match,
                        note=f"Prohibited pattern matched: '{raw_pattern}'",
                    )
                    violations.append(ev)
                    violation_descriptions.append(f"'{match.group(0)}' (rule: {raw_pattern})")

        if violations:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Prohibited Claims Detection",
                rule_type=self.rule_type,
                status=RuleStatus.FAIL,
                explanation=f"Agent made {len(violations)} prohibited claim(s): {', '.join(violation_descriptions)}.",
                evidence=violations,
                details={"violation_count": len(violations)},
            )

        return RuleResult(
            rule_id=config.id,
            rule_name=config.name or "Prohibited Claims Detection",
            rule_type=self.rule_type,
            status=RuleStatus.PASS,
            explanation="No prohibited claims or unapproved promises were detected.",
            evidence=[],
        )
