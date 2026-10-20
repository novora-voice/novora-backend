from typing import Any, Dict, Optional
from novora.core.enums import OverallStatus, TestRunStatus
from novora.core.execution_models import (
    AgentConfig,
    TestCase,
    TestRun,
)
from novora.core.models import (
    Conversation,
    EvaluationReport,
    EvaluationScenario,
)
from novora.evaluation.engine import EvaluationEngine
from novora.evaluation.llm_judge.service import LLMJudgeService
from novora.evaluation.orchestration.aggregator import EvaluationAggregator
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
    ) -> tuple[TestRun, EvaluationReport, Conversation]:
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
                rule_results=[],
            )
            return test_run, failed_report, conversation

        # 2. Run deterministic checks
        deterministic_report = self.engine.evaluate(conversation, scenario)

        # 3. Run LLM judge if requested and available
        judge_result = None
        if enable_llm_judge:
            judge_result = self.judge.evaluate(conversation, scenario)

        # 4. Conservative aggregation
        final_report = EvaluationAggregator.aggregate_results(
            scenario_id=scenario.id,
            conversation_id=conversation.id,
            deterministic_results=deterministic_report.rule_results,
            judge_result=judge_result,
        )
        test_run.evaluation_id = final_report.id

        return test_run, final_report, conversation
