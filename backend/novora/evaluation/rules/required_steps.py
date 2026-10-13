import re
from typing import Dict, List, Optional
from novora.core.enums import MessageRole, RuleStatus, RuleType
from novora.core.models import (
    Conversation,
    EvaluationScenario,
    EvidenceReference,
    RuleConfig,
    RuleResult,
)
from novora.evaluation.rules.base import BaseRule

class RequiredStepsRule(BaseRule):
    """Rule 2: Verifies that expected workflow steps occurred in correct sequence."""

    @property
    def rule_type(self) -> RuleType:
        return RuleType.REQUIRED_STEPS

    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        steps_config = config.parameters.get("steps", [])
        ordered = config.parameters.get("ordered", True)
        default_target_role = config.parameters.get("target_role", MessageRole.AGENT)

        if not steps_config:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Required Workflow Steps Verification",
                rule_type=self.rule_type,
                status=RuleStatus.PASS,
                explanation="No required workflow steps configured.",
                evidence=[],
            )

        step_evidence: Dict[str, EvidenceReference] = {}
        missing_steps: List[str] = []
        observed_sequences: List[int] = []

        min_seq = -1
        for step in steps_config:
            if isinstance(step, dict):
                step_name = step.get("name", "unnamed_step")
                pattern_str = step.get("pattern", rf"\b{re.escape(step_name)}\b")
                step_role = step.get("role", default_target_role)
            else:
                step_name = str(step)
                pattern_str = rf"\b{re.escape(step_name)}\b"
                step_role = default_target_role

            regex = re.compile(pattern_str, re.IGNORECASE)
            found: Optional[EvidenceReference] = None

            for msg in conversation.messages:
                # If step_role is specified and not "any", filter by role
                if step_role and step_role != "any" and msg.role != step_role:
                    continue

                # If ordered is required, we want matching messages that occur after the previous step
                if ordered and msg.sequence <= min_seq:
                    continue

                m = regex.search(msg.content)
                if m:
                    found = self.extract_evidence(
                        msg,
                        m,
                        note=f"Workflow step '{step_name}' detected",
                    )
                    break

            if found:
                step_evidence[step_name] = found
                observed_sequences.append(found.sequence)
                if ordered:
                    min_seq = found.sequence
            else:
                missing_steps.append(step_name)

        if missing_steps:
            return RuleResult(
                rule_id=config.id,
                rule_name=config.name or "Required Workflow Steps Verification",
                rule_type=self.rule_type,
                status=RuleStatus.FAIL,
                explanation=f"Missing mandatory workflow step(s): {', '.join(missing_steps)}.",
                evidence=list(step_evidence.values()),
                details={"completed_steps": list(step_evidence.keys()), "missing_steps": missing_steps},
            )

        return RuleResult(
            rule_id=config.id,
            rule_name=config.name or "Required Workflow Steps Verification",
            rule_type=self.rule_type,
            status=RuleStatus.PASS,
            explanation=f"All {len(step_evidence)} workflow steps were executed successfully in proper sequence.",
            evidence=list(step_evidence.values()),
            details={"completed_steps": list(step_evidence.keys()), "step_order_observed": observed_sequences},
        )
