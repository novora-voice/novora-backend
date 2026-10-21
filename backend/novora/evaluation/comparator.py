from typing import Dict, List

from novora.core.enums import OverallStatus, RuleStatus
from novora.core.models import EvaluationReport, RegressionReport, RuleComparison, RuleResult


class EvaluationComparator:
    """Compare only checks that have stable, compatible identities and executed results."""

    @classmethod
    def compare(cls, baseline: EvaluationReport, candidate: EvaluationReport) -> RegressionReport:
        issues: List[str] = []
        issues.extend(f"Baseline report integrity: {item}" for item in baseline.integrity_issues)
        issues.extend(f"Candidate report integrity: {item}" for item in candidate.integrity_issues)
        if baseline.scenario_id != candidate.scenario_id:
            issues.append("Baseline and candidate use different scenarios.")
        if not baseline.scenario_fingerprint or not candidate.scenario_fingerprint:
            issues.append("Scenario versions are missing from one or both reports; compatibility cannot be verified.")
        elif baseline.scenario_fingerprint != candidate.scenario_fingerprint:
            issues.append("Baseline and candidate were evaluated against different scenario or rubric versions.")

        scenario_compatible = (
            baseline.scenario_id == candidate.scenario_id
            and bool(baseline.scenario_fingerprint)
            and baseline.scenario_fingerprint == candidate.scenario_fingerprint
            and not baseline.integrity_issues
            and not candidate.integrity_issues
        )

        base_rules = cls._unique_rules(baseline.rule_results, "baseline", issues)
        cand_rules = cls._unique_rules(candidate.rule_results, "candidate", issues)
        base_expected = set(baseline.expected_rule_ids) or set(base_rules)
        cand_expected = set(candidate.expected_rule_ids) or set(cand_rules)

        missing_baseline = base_expected - set(base_rules)
        missing_candidate = cand_expected - set(cand_rules)
        if missing_baseline:
            issues.append(f"Baseline did not produce results for {len(missing_baseline)} expected check(s).")
        if missing_candidate:
            issues.append(f"Candidate did not produce results for {len(missing_candidate)} expected check(s).")

        all_ids = list(dict.fromkeys([*base_expected, *cand_expected, *base_rules, *cand_rules]))
        comparisons: List[RuleComparison] = []
        regressions = 0
        improvements = 0
        for rule_id in all_ids:
            base_result = base_rules.get(rule_id)
            candidate_result = cand_rules.get(rule_id)
            representative = candidate_result or base_result
            if representative is None:
                # An expected rule missing from both runs has no safe display metadata.
                continue

            compatible = bool(base_result and candidate_result and scenario_compatible)
            if compatible and (
                base_result.rule_type != candidate_result.rule_type
                or base_result.rule_version != candidate_result.rule_version
            ):
                issues.append(f"Check '{rule_id}' changed type or rule version between runs.")
                compatible = False

            base_status = base_result.status if base_result else RuleStatus.NOT_EVALUATED
            candidate_status = candidate_result.status if candidate_result else RuleStatus.NOT_EVALUATED
            if not compatible or RuleStatus.NOT_EVALUATED in (base_status, candidate_status):
                change = "not_evaluated"
                issues.append(f"Check '{representative.rule_name}' lacks comparable results in both runs.")
            elif RuleStatus.INCONCLUSIVE in (base_status, candidate_status):
                change = "inconclusive"
                issues.append(f"Check '{representative.rule_name}' has inconclusive evidence in at least one run.")
            elif base_status == RuleStatus.PASS and candidate_status == RuleStatus.FAIL:
                change = "regressed"
                regressions += 1
            elif base_status == RuleStatus.FAIL and candidate_status == RuleStatus.PASS:
                change = "improved"
                improvements += 1
            else:
                change = "unchanged"

            base_explanation = base_result.explanation if base_result else "No result was saved for the baseline check."
            candidate_explanation = candidate_result.explanation if candidate_result else "No result was saved for the candidate check."
            comparisons.append(
                RuleComparison(
                    rule_id=rule_id,
                    baseline_rule_id=base_result.rule_id if base_result else None,
                    candidate_rule_id=candidate_result.rule_id if candidate_result else None,
                    rule_name=representative.rule_name,
                    rule_type=representative.rule_type,
                    baseline_status=base_status,
                    candidate_status=candidate_status,
                    change=change,
                    explanation_diff=(
                        f"Candidate: [{candidate_status.value}] {candidate_explanation} | "
                        f"Baseline: [{base_status.value}] {base_explanation}"
                    ),
                )
            )

        coverage_complete = not issues
        if not coverage_complete:
            comparison_status = OverallStatus.INCONCLUSIVE
            net_change = "inconclusive"
        elif regressions:
            comparison_status = OverallStatus.FAIL
            net_change = "regressed"
        elif improvements:
            comparison_status = OverallStatus.PASS
            net_change = "improved"
        else:
            comparison_status = OverallStatus.PASS
            net_change = "neutral"

        if coverage_complete:
            summary = (
                f"Comparable checks completed: {regressions} behavioral regression(s), "
                f"{improvements} improvement(s)."
            )
        else:
            summary = (
                f"Evaluation coverage is incomplete; overall comparison is INCONCLUSIVE. "
                f"{regressions} comparable regression(s) and {improvements} improvement(s) were observed. "
                + " ".join(dict.fromkeys(issues))
            )

        return RegressionReport(
            scenario_id=candidate.scenario_id or baseline.scenario_id,
            baseline_id=baseline.id,
            candidate_id=candidate.id,
            baseline_status=baseline.overall_status,
            candidate_status=candidate.overall_status,
            comparison_status=comparison_status,
            coverage_complete=coverage_complete,
            coverage_issues=list(dict.fromkeys(issues)),
            regression_detected=regressions > 0,
            net_status_change=net_change,
            rule_comparisons=comparisons,
            summary=summary,
        )

    @staticmethod
    def _unique_rules(results: List[RuleResult], run_label: str, issues: List[str]) -> Dict[str, RuleResult]:
        indexed: Dict[str, RuleResult] = {}
        for result in results:
            if result.rule_id in indexed:
                issues.append(f"{run_label.title()} contains duplicate result IDs for check '{result.rule_id}'.")
                continue
            indexed[result.rule_id] = result
        return indexed
