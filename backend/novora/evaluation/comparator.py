from typing import Dict, List
from novora.core.enums import OverallStatus, RuleStatus
from novora.core.models import (
    EvaluationReport,
    RegressionReport,
    RuleComparison,
    RuleResult,
)

class EvaluationComparator:
    """Compares baseline vs candidate evaluation reports to detect regressions and improvements."""

    @classmethod
    def compare(
        cls,
        baseline: EvaluationReport,
        candidate: EvaluationReport,
    ) -> RegressionReport:
        """Computes rule-by-rule diff between two evaluation runs."""
        base_rules: Dict[str, RuleResult] = {r.rule_name: r for r in baseline.rule_results}
        cand_rules: Dict[str, RuleResult] = {r.rule_name: r for r in candidate.rule_results}

        all_rule_names = list(dict.fromkeys(list(base_rules.keys()) + list(cand_rules.keys())))
        comparisons: List[RuleComparison] = []
        regressions_count = 0
        improvements_count = 0

        for r_name in all_rule_names:
            base_r = base_rules.get(r_name)
            cand_r = cand_rules.get(r_name)

            base_status = base_r.status if base_r else RuleStatus.INCONCLUSIVE
            cand_status = cand_r.status if cand_r else RuleStatus.INCONCLUSIVE
            rule_type = (cand_r or base_r).rule_type

            if base_status == RuleStatus.PASS and cand_status != RuleStatus.PASS:
                change = "regressed"
                regressions_count += 1
            elif base_status != RuleStatus.PASS and cand_status == RuleStatus.PASS:
                change = "improved"
                improvements_count += 1
            else:
                change = "unchanged"

            cand_exp = cand_r.explanation if cand_r else "Rule not evaluated in candidate run."
            base_exp = base_r.explanation if base_r else "Rule not evaluated in baseline run."

            diff_note = (
                f"Candidate: [{cand_status.value}] {cand_exp} | Baseline: [{base_status.value}] {base_exp}"
            )

            comparisons.append(
                RuleComparison(
                    rule_name=r_name,
                    rule_type=rule_type,
                    baseline_status=base_status,
                    candidate_status=cand_status,
                    change=change,
                    explanation_diff=diff_note,
                )
            )

        regression_detected = (
            regressions_count > 0
            or (baseline.overall_status == OverallStatus.PASS and candidate.overall_status != OverallStatus.PASS)
        )

        if regressions_count > improvements_count or (baseline.overall_status == OverallStatus.PASS and candidate.overall_status == OverallStatus.FAIL):
            net_change = "regressed"
        elif improvements_count > regressions_count:
            net_change = "improved"
        else:
            net_change = "neutral"

        summary = (
            f"Comparison completed: {regressions_count} rule regression(s), "
            f"{improvements_count} rule improvement(s). "
            f"Overall baseline: {baseline.overall_status.value} -> candidate: {candidate.overall_status.value}."
        )

        return RegressionReport(
            scenario_id=candidate.scenario_id or baseline.scenario_id,
            baseline_id=baseline.id,
            candidate_id=candidate.id,
            baseline_status=baseline.overall_status,
            candidate_status=candidate.overall_status,
            regression_detected=regression_detected,
            net_status_change=net_change,
            rule_comparisons=comparisons,
            summary=summary,
        )
