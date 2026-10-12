from novora.core.enums import OverallStatus, RuleStatus, RuleType
from novora.core.models import EvaluationReport, RuleResult
from novora.evaluation.comparator import EvaluationComparator

def test_regression_detected_when_passing_rule_fails():
    base_report = EvaluationReport(
        id="rep_base_001",
        scenario_id="scen_refund_01",
        conversation_id="conv_v1",
        overall_status=OverallStatus.PASS,
        summary="Passed",
        rule_results=[
            RuleResult(
                rule_id="r1",
                rule_name="Check Order ID",
                rule_type=RuleType.REQUIRED_INFORMATION,
                status=RuleStatus.PASS,
                explanation="Collected order ID #9821.",
            ),
            RuleResult(
                rule_id="r2",
                rule_name="Enforce $50 Limit",
                rule_type=RuleType.POLICY_COMPLIANCE,
                status=RuleStatus.PASS,
                explanation="Offered $25 credit <= $50.",
            ),
        ],
    )

    # Candidate run where agent offered $120, violating the $50 limit
    cand_report = EvaluationReport(
        id="rep_cand_002",
        scenario_id="scen_refund_01",
        conversation_id="conv_v2",
        overall_status=OverallStatus.FAIL,
        summary="Failed",
        rule_results=[
            RuleResult(
                rule_id="r1",
                rule_name="Check Order ID",
                rule_type=RuleType.REQUIRED_INFORMATION,
                status=RuleStatus.PASS,
                explanation="Collected order ID #9821.",
            ),
            RuleResult(
                rule_id="r2",
                rule_name="Enforce $50 Limit",
                rule_type=RuleType.POLICY_COMPLIANCE,
                status=RuleStatus.FAIL,
                explanation="Offered $120 credit exceeding $50 threshold.",
            ),
        ],
    )

    diff = EvaluationComparator.compare(baseline=base_report, candidate=cand_report)

    assert diff.regression_detected is True
    assert diff.net_status_change == "regressed"
    assert len(diff.rule_comparisons) == 2

    r1_cmp = next(c for c in diff.rule_comparisons if c.rule_name == "Check Order ID")
    assert r1_cmp.change == "unchanged"

    r2_cmp = next(c for c in diff.rule_comparisons if c.rule_name == "Enforce $50 Limit")
    assert r2_cmp.change == "regressed"
    assert r2_cmp.baseline_status == RuleStatus.PASS
    assert r2_cmp.candidate_status == RuleStatus.FAIL

def test_improvement_detected_when_failing_rule_passes():
    base_report = EvaluationReport(
        id="rep_base_fail",
        scenario_id="scen_01",
        conversation_id="conv_v1",
        overall_status=OverallStatus.FAIL,
        summary="Failed",
        rule_results=[
            RuleResult(
                rule_id="r1",
                rule_name="Greeting",
                rule_type=RuleType.REQUIRED_STEPS,
                status=RuleStatus.FAIL,
                explanation="Greeting omitted.",
            )
        ],
    )

    cand_report = EvaluationReport(
        id="rep_cand_pass",
        scenario_id="scen_01",
        conversation_id="conv_v2",
        overall_status=OverallStatus.PASS,
        summary="Passed",
        rule_results=[
            RuleResult(
                rule_id="r1",
                rule_name="Greeting",
                rule_type=RuleType.REQUIRED_STEPS,
                status=RuleStatus.PASS,
                explanation="Greeting delivered.",
            )
        ],
    )

    diff = EvaluationComparator.compare(baseline=base_report, candidate=cand_report)

    assert diff.regression_detected is False
    assert diff.net_status_change == "improved"
    assert diff.rule_comparisons[0].change == "improved"
