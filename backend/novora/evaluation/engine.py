from typing import Dict, List, Optional
from novora.core.enums import OverallStatus, RuleStatus, RuleType
from novora.core.models import (
    Conversation,
    EvaluationReport,
    EvaluationScenario,
    RuleConfig,
    RuleResult,
)
from novora.evaluation.rules.base import BaseRule
from novora.evaluation.rules.policy_compliance import PolicyComplianceRule
from novora.evaluation.rules.prohibited_claims import ProhibitedClaimsRule
from novora.evaluation.rules.required_info import RequiredInfoRule
from novora.evaluation.rules.required_steps import RequiredStepsRule
from novora.evaluation.rules.unresolved_work import UnresolvedWorkRule
from novora.evaluation.rules.unsupported_completion import UnsupportedCompletionClaimsRule

class EvaluationEngine:
    """Orchestrates deterministic rule evaluations and generates traceable reports."""

    def __init__(self, evaluators: Optional[Dict[RuleType, BaseRule]] = None) -> None:
        if evaluators is not None:
            self._evaluators = evaluators
        else:
            self._evaluators = {
                RuleType.REQUIRED_INFORMATION: RequiredInfoRule(),
                RuleType.REQUIRED_STEPS: RequiredStepsRule(),
                RuleType.PROHIBITED_CLAIMS: ProhibitedClaimsRule(),
                RuleType.UNSUPPORTED_COMPLETION: UnsupportedCompletionClaimsRule(),
                RuleType.UNRESOLVED_WORK: UnresolvedWorkRule(),
                RuleType.POLICY_COMPLIANCE: PolicyComplianceRule(),
            }

    def register_evaluator(self, rule_type: RuleType, evaluator: BaseRule) -> None:
        """Register or override a rule evaluator strategy."""
        self._evaluators[rule_type] = evaluator

    def evaluate(
        self,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> EvaluationReport:
        """Execute all configured scenario rules against a conversation and produce a report."""
        rule_results: List[RuleResult] = []

        for rule_cfg in scenario.rules:
            evaluator = self._evaluators.get(rule_cfg.rule_type)
            if not evaluator:
                # Unregistered rule type treated as INCONCLUSIVE
                result = RuleResult(
                    rule_id=rule_cfg.id,
                    rule_name=rule_cfg.name or str(rule_cfg.rule_type.value),
                    rule_type=rule_cfg.rule_type,
                    status=RuleStatus.INCONCLUSIVE,
                    explanation=f"No evaluator registered for rule type '{rule_cfg.rule_type}'.",
                    evidence=[],
                )
            else:
                result = evaluator.evaluate(rule_cfg, conversation, scenario)
            rule_results.append(result)

        # Aggregate overall status
        failed_count = sum(1 for r in rule_results if r.status == RuleStatus.FAIL)
        inconclusive_count = sum(1 for r in rule_results if r.status == RuleStatus.INCONCLUSIVE)
        passed_count = sum(1 for r in rule_results if r.status == RuleStatus.PASS)
        total_count = len(rule_results)

        if failed_count > 0:
            overall = OverallStatus.FAIL
            summary = (
                f"Evaluation FAILED: {failed_count} of {total_count} rule(s) failed. "
                f"({passed_count} passed, {inconclusive_count} inconclusive)."
            )
        elif inconclusive_count > 0:
            overall = OverallStatus.INCONCLUSIVE
            summary = (
                f"Evaluation INCONCLUSIVE: {inconclusive_count} of {total_count} rule(s) lacked sufficient evidence. "
                f"({passed_count} passed, 0 failed)."
            )
        else:
            overall = OverallStatus.PASS
            summary = (
                f"Evaluation PASSED: All {total_count} business rule(s) satisfied with supporting evidence."
            )

        report = EvaluationReport(
            scenario_id=scenario.id,
            conversation_id=conversation.id,
            overall_status=overall,
            summary=summary,
            rule_results=rule_results,
        )
        return report
