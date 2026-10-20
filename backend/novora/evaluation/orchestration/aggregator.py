from typing import List, Optional
from uuid import uuid4
from novora.core.enums import MessageRole, OverallStatus, RuleSeverity, RuleStatus, RuleType
from novora.core.judge_models import LLMJudgeResult
from novora.core.models import EvaluationReport, EvidenceReference, RuleResult


class EvaluationAggregator:
    """Aggregates deterministic and LLM judge outcomes with strict safety precedence."""

    @staticmethod
    def aggregate_results(
        scenario_id: str,
        conversation_id: str,
        deterministic_results: List[RuleResult],
        judge_result: Optional[LLMJudgeResult] = None,
        rule_severities: Optional[dict[str, RuleSeverity]] = None,
    ) -> EvaluationReport:
        severities = rule_severities or {}
        combined_rule_results: List[RuleResult] = list(deterministic_results)

        # Incorporate judge verdicts as semantic rule results
        if judge_result:
            for verdict in judge_result.verdicts:
                combined_rule_results.append(
                    RuleResult(
                        rule_id=f"judge_{verdict.criterion_id}",
                        rule_name=f"LLM Judge: {verdict.criterion_id.replace('_', ' ').title()}",
                        rule_type=RuleType.LLM_SEMANTIC_RUBRIC,
                        status=verdict.status,
                        explanation=f"[Confidence {verdict.confidence:.2f}] {verdict.rationale}",
                        evidence=[
                            EvidenceReference(
                                message_id=cid,
                                speaker=MessageRole.SYSTEM,
                                sequence=0,
                                snippet="Grounded dialogue evidence",
                            )
                            for cid in verdict.evidence_citations
                        ],

                        details={
                            "confidence": verdict.confidence,
                            "model": judge_result.model_name,
                            **({"judge_error": judge_result.error_message} if judge_result.error_message else {}),
                        },
                    )
                )

        # Deterministic precedence: check for critical failures
        critical_failure = False
        for dr in deterministic_results:
            sev = severities.get(dr.rule_id, RuleSeverity.HIGH)
            if sev == RuleSeverity.CRITICAL and dr.status == RuleStatus.FAIL:
                critical_failure = True
                break

        failed_count = sum(1 for r in combined_rule_results if r.status == RuleStatus.FAIL)
        inconclusive_count = sum(1 for r in combined_rule_results if r.status == RuleStatus.INCONCLUSIVE)
        not_evaluated_count = sum(1 for r in combined_rule_results if r.status == RuleStatus.NOT_EVALUATED)
        passed_count = sum(1 for r in combined_rule_results if r.status == RuleStatus.PASS)
        total_count = len(combined_rule_results)

        if critical_failure or failed_count > 0:
            overall = OverallStatus.FAIL
            summary = (
                f"Evaluation FAILED: {failed_count} rule(s) failed out of {total_count}. "
                f"Critical safety enforcement active. ({passed_count} passed, {inconclusive_count} inconclusive)."
            )
        elif inconclusive_count > 0 or not_evaluated_count > 0:
            overall = OverallStatus.INCONCLUSIVE
            summary = (
                f"Evaluation INCONCLUSIVE: {inconclusive_count} criterion/criteria lacked evidence and "
                f"{not_evaluated_count} were not evaluated out of {total_count}. "
                f"({passed_count} passed, 0 failed)."
            )
        else:
            overall = OverallStatus.PASS
            summary = (
                f"Evaluation PASSED: All {total_count} deterministic and semantic criteria satisfied."
            )

        return EvaluationReport(
            id=f"eval_{uuid4().hex[:8]}",
            scenario_id=scenario_id,
            conversation_id=conversation_id,
            overall_status=overall,
            summary=summary,
            rule_results=combined_rule_results,
        )
