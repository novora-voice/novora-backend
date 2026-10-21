from typing import Any, Dict, List, Optional
from novora.core.enums import OverallStatus, RuleStatus, RuleType, TestRunStatus
from novora.core.execution_models import (
    AgentConfig,
    TestCase,
    TestRun,
)
from novora.core.models import (
    Conversation,
    EvaluationReport,
    EvaluationScenario,
    RuleResult,
)
from novora.core.judge_models import LLMJudgeResult, LLMJudgeVerdict, RubricCriterion
from novora.evaluation.engine import EvaluationEngine
from novora.evaluation.llm_judge.service import LLMJudgeService
from novora.evaluation.orchestration.aggregator import EvaluationAggregator
from novora.evaluation.llm_judge.rubrics import get_rubrics_for_scenario
from novora.evaluation.scenario_identity import fingerprint_scenario
from novora.execution.ghost_caller import GhostCallerOrchestrator

class CombinedEvaluationPipeline:
    """Executes the complete test run, deterministic rules, and LLM-as-judge pipeline."""

    def __init__(
        self,
        ghost_caller: Optional[GhostCallerOrchestrator] = None,
        deterministic_engine: Optional[EvaluationEngine] = None,
        llm_judge: Optional[LLMJudgeService] = None,
    ) -> None:
        self.ghost_caller = ghost_caller or GhostCallerOrchestrator()
        self.engine = deterministic_engine or EvaluationEngine()
        self.judge = llm_judge or LLMJudgeService()

    def run_pipeline(
        self,
        scenario: EvaluationScenario,
        test_case: TestCase,
        agent: AgentConfig,
        provider_config: Dict[str, Any],
        enable_llm_judge: bool = True,
        llm_rubrics: Optional[List[RubricCriterion]] = None,
    ) -> tuple[TestRun, EvaluationReport, Conversation]:
        active_rubrics = llm_rubrics if llm_rubrics is not None else get_rubrics_for_scenario(scenario.name)
        expected_rule_ids = [rule.id for rule in scenario.rules]
        if enable_llm_judge:
            expected_rule_ids.extend(f"judge_{rubric.criterion_id}" for rubric in active_rubrics)
        scenario_version = fingerprint_scenario(
            scenario,
            active_rubrics,
            judge_enabled=enable_llm_judge,
        )
        # 1. Execute ghost caller test
        test_run, conversation = self.ghost_caller.execute_test(
            test_case=test_case,
            agent=agent,
            provider_config=provider_config,
        )

        if test_run.status == TestRunStatus.FAILED:
            # Short-circuit on provider execution crash
            failed_report = EvaluationReport(
                scenario_id=scenario.id,
                conversation_id=conversation.id,
                overall_status=OverallStatus.INCONCLUSIVE,
                summary=f"Execution Failed: {test_run.error_message}",
                test_run_id=test_run.id,
                scenario_fingerprint=scenario_version,
                expected_rule_ids=expected_rule_ids,
                rule_results=[
                    RuleResult(
                        rule_id=rule.id,
                        rule_name=rule.name or rule.rule_type.value,
                        rule_type=rule.rule_type,
                        status=RuleStatus.NOT_EVALUATED,
                        explanation="Provider execution failed before this rule could be evaluated.",
                    )
                    for rule in scenario.rules
                ] + [
                    RuleResult(
                        rule_id=f"judge_{rubric.criterion_id}",
                        rule_name=f"LLM Judge: {rubric.name}",
                        rule_type=RuleType.LLM_SEMANTIC_RUBRIC,
                        status=RuleStatus.NOT_EVALUATED,
                        explanation="Provider execution failed before this judge criterion could be evaluated.",
                    )
                    for rubric in (active_rubrics if enable_llm_judge else [])
                ],
            )
            test_run.evaluation_id = failed_report.id
            return test_run, failed_report, conversation

        # 2. Run deterministic checks
        deterministic_report = self.engine.evaluate(conversation, scenario)

        # 3. Run LLM judge if requested and available
        judge_result = None
        if enable_llm_judge:
            try:
                judge_result = self.judge.evaluate(conversation, scenario, rubrics=active_rubrics)
            except Exception as exc:
                judge_result = LLMJudgeResult(
                    model_name=getattr(self.judge, "model_name", "unknown"),
                    is_available=False,
                    error_message=f"Judge execution failed: {type(exc).__name__}: {exc}",
                    verdicts=[
                        LLMJudgeVerdict(
                            criterion_id=rubric.criterion_id,
                            status=RuleStatus.NOT_EVALUATED,
                            confidence=0.0,
                            rationale="Judge execution failed before this criterion could be evaluated.",
                        )
                        for rubric in active_rubrics
                    ],
                )

        # 4. Conservative aggregation
        final_report = EvaluationAggregator.aggregate_results(
            scenario_id=scenario.id,
            conversation_id=conversation.id,
            deterministic_results=deterministic_report.rule_results,
            judge_result=judge_result,
        )
        test_run.evaluation_id = final_report.id
        final_report.test_run_id = test_run.id
        final_report.test_run_id = test_run.id
        final_report.scenario_fingerprint = scenario_version
        final_report.expected_rule_ids = expected_rule_ids

        return test_run, final_report, conversation
