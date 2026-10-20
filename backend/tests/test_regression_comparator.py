from novora.core.enums import OverallStatus, RuleStatus, RuleType, TestRunStatus
from novora.core.execution_models import AgentConfig, TestCase, TestRun
from novora.core.judge_models import RubricCriterion
from novora.core.models import (
    Conversation,
    ConversationMessage,
    EvaluationReport,
    EvaluationScenario,
    RuleConfig,
    RuleResult,
)
from novora.evaluation.comparator import EvaluationComparator
from novora.evaluation.orchestration.pipeline import CombinedEvaluationPipeline


def _rule(rule_id: str, status: RuleStatus, *, name: str = "Order ID") -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        rule_name=name,
        rule_type=RuleType.REQUIRED_INFORMATION,
        status=status,
        explanation=f"Observed {status.value.lower()} evidence.",
    )


def _report(
    report_id: str,
    rules: list[RuleResult],
    *,
    expected: list[str] | None = None,
    fingerprint: str | None = "scenario-v1",
    status: OverallStatus = OverallStatus.PASS,
) -> EvaluationReport:
    return EvaluationReport(
        id=report_id,
        scenario_id="scen_same",
        conversation_id=f"conv_{report_id}",
        scenario_fingerprint=fingerprint,
        expected_rule_ids=expected or [rule.rule_id for rule in rules],
        overall_status=status,
        summary=status.value,
        rule_results=rules,
    )


def test_genuine_pass_to_fail_is_a_regression():
    baseline = _report("base", [_rule("rule_order_id", RuleStatus.PASS)])
    candidate = _report("candidate", [_rule("rule_order_id", RuleStatus.FAIL)], status=OverallStatus.FAIL)

    diff = EvaluationComparator.compare(baseline, candidate)

    assert diff.comparison_status == OverallStatus.FAIL
    assert diff.coverage_complete is True
    assert diff.regression_detected is True
    assert diff.net_status_change == "regressed"
    assert diff.rule_comparisons[0].change == "regressed"


def test_missing_candidate_result_is_coverage_failure_not_regression():
    baseline = _report(
        "base",
        [_rule("rule_order_id", RuleStatus.PASS), _rule("rule_policy", RuleStatus.PASS, name="Policy")],
        expected=["rule_order_id", "rule_policy"],
    )
    candidate = _report(
        "candidate",
        [_rule("rule_order_id", RuleStatus.PASS)],
        expected=["rule_order_id", "rule_policy"],
    )

    diff = EvaluationComparator.compare(baseline, candidate)

    missing = next(item for item in diff.rule_comparisons if item.rule_id == "rule_policy")
    assert missing.baseline_status == RuleStatus.PASS
    assert missing.candidate_status == RuleStatus.NOT_EVALUATED
    assert missing.change == "not_evaluated"
    assert diff.comparison_status == OverallStatus.INCONCLUSIVE
    assert diff.coverage_complete is False
    assert diff.regression_detected is False
    assert diff.net_status_change == "inconclusive"


def test_mismatched_rule_ids_with_same_display_name_are_not_compared():
    baseline = _report("base", [_rule("rule_old_id", RuleStatus.PASS)])
    candidate = _report("candidate", [_rule("rule_new_id", RuleStatus.FAIL)], status=OverallStatus.FAIL)

    diff = EvaluationComparator.compare(baseline, candidate)

    assert diff.comparison_status == OverallStatus.INCONCLUSIVE
    assert diff.regression_detected is False
    assert all(item.change == "not_evaluated" for item in diff.rule_comparisons)


def test_changed_scenario_fingerprint_makes_comparison_inconclusive():
    baseline = _report("base", [_rule("rule_order_id", RuleStatus.PASS)], fingerprint="scenario-v1")
    candidate = _report("candidate", [_rule("rule_order_id", RuleStatus.FAIL)], fingerprint="scenario-v2")

    diff = EvaluationComparator.compare(baseline, candidate)

    assert diff.comparison_status == OverallStatus.INCONCLUSIVE
    assert diff.coverage_complete is False
    assert diff.regression_detected is False


def test_rule_configs_without_explicit_ids_get_stable_identifiers():
    attributes = {
        "rule_type": RuleType.REQUIRED_INFORMATION,
        "name": "Order ID",
        "description": "Collect an order identifier",
        "parameters": {"required_fields": ["order_id"]},
    }

    first = RuleConfig(**attributes)
    second = RuleConfig(**attributes)

    assert first.id == second.id


def test_failed_judge_execution_is_explicitly_not_evaluated():
    class GhostCaller:
        def execute_test(self, test_case, agent, provider_config):
            run = TestRun(
                scenario_id=test_case.scenario_id,
                test_case_id=test_case.id,
                provider=agent.provider_name,
                agent_id=agent.external_agent_id,
                status=TestRunStatus.COMPLETED,
            )
            conversation = Conversation(
                scenario_id=test_case.scenario_id,
                messages=[
                    ConversationMessage(role="customer", content="My order is ORD-1234", sequence=0),
                    ConversationMessage(role="agent", content="I can help with that", sequence=1),
                ],
            )
            return run, conversation

    class BrokenJudge:
        model_name = "test-judge"

        def evaluate(self, *args, **kwargs):
            raise RuntimeError("judge service unavailable")

    scenario = EvaluationScenario(
        id="scen_same",
        name="Customer support",
        business_goal="Collect order ID",
        rules=[],
    )
    rubric = RubricCriterion(
        criterion_id="tone",
        name="Tone",
        description="Polite language",
        rubric_guidance="Judge the agent tone.",
    )
    pipeline = CombinedEvaluationPipeline(ghost_caller=GhostCaller(), llm_judge=BrokenJudge())

    _, report, _ = pipeline.run_pipeline(
        scenario=scenario,
        test_case=TestCase(scenario_id=scenario.id, name="test", scripted_turns=[]),
        agent=AgentConfig(provider_name="elevenlabs", external_agent_id="agent-1", name="Agent"),
        provider_config={},
        enable_llm_judge=True,
        llm_rubrics=[rubric],
    )

    judge_result = next(result for result in report.rule_results if result.rule_id == "judge_tone")
    assert judge_result.status == RuleStatus.NOT_EVALUATED
    assert "Judge execution failed" in judge_result.explanation
    assert report.overall_status == OverallStatus.INCONCLUSIVE
    assert report.expected_rule_ids == ["judge_tone"]


def test_reports_without_saved_scenario_versions_are_inconclusive():
    baseline = _report("base", [_rule("same", RuleStatus.FAIL)], fingerprint=None, status=OverallStatus.FAIL)
    candidate = _report("candidate", [_rule("same", RuleStatus.FAIL)], fingerprint=None, status=OverallStatus.FAIL)

    diff = EvaluationComparator.compare(baseline, candidate)

    assert diff.rule_comparisons[0].change == "not_evaluated"
    assert diff.regression_detected is False
    assert diff.comparison_status == OverallStatus.INCONCLUSIVE
    assert any("Scenario versions are missing" in issue for issue in diff.coverage_issues)


def test_missing_candidate_transcript_cannot_be_reported_as_behavioral_regression():
    baseline = _report("base", [_rule("rule_order_id", RuleStatus.PASS)])
    candidate = _report("candidate", [_rule("rule_order_id", RuleStatus.FAIL)], status=OverallStatus.FAIL).model_copy(
        update={"integrity_issues": ["Candidate transcript is missing from persistence."]}
    )

    diff = EvaluationComparator.compare(baseline, candidate)

    assert diff.comparison_status == OverallStatus.INCONCLUSIVE
    assert diff.regression_detected is False
    assert diff.rule_comparisons[0].change == "not_evaluated"
    assert any("transcript is missing" in item.lower() for item in diff.coverage_issues)
