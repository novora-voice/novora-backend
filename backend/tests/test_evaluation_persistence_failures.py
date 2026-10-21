import pytest

from novora.api.routes import test_runs
from novora.core.enums import OverallStatus, RuleType, TestRunStatus
from novora.core.execution_models import AgentConfig, TestRun
from novora.core.models import Conversation, EvaluationReport, EvaluationScenario
from novora.api.routes.test_runs import TestRunExecutionRequest as ExecutionRequest, _execute_test_run


class _SaveRepository:
    def __init__(self, failure=None):
        self.saved = []
        self.failure = failure

    def save(self, item):
        if self.failure:
            raise self.failure
        self.saved.append(item)
        return item


def test_report_persistence_failure_does_not_save_run_as_success(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(test_runs, "get_database_session_manager", lambda _: object())

    class CompletedPipeline:
        def run_pipeline(self, scenario, test_case, agent, provider_config, enable_llm_judge, llm_rubrics=None):
            run = TestRun(
                id="trun_test",
                scenario_id=scenario.id,
                provider=agent.provider_name,
                agent_id=agent.external_agent_id,
                status=TestRunStatus.COMPLETED,
                conversation_id="conv_test",
                evaluation_id="eval_test",
            )
            report = EvaluationReport(
                id="eval_test",
                scenario_id=scenario.id,
                conversation_id="conv_test",
                overall_status=OverallStatus.PASS,
                summary="Passed",
                scenario_fingerprint="version-1",
                expected_rule_ids=[],
                test_run_id=run.id,
            )
            return run, report, Conversation(id="conv_test", scenario_id=scenario.id)

    monkeypatch.setattr(test_runs, "pipeline", CompletedPipeline())
    scenario_repo = _SaveRepository()
    agent_repo = _SaveRepository()
    case_repo = _SaveRepository()
    conversation_repo = _SaveRepository()
    evaluation_repo = _SaveRepository(RuntimeError("evaluation commit failed"))
    run_repo = _SaveRepository()

    request = ExecutionRequest(
        scenario=EvaluationScenario(id="scen_test", name="Test", business_goal="Verify result"),
        agent=AgentConfig(provider_name="elevenlabs", external_agent_id="agent_test", name="Agent"),
    )

    with pytest.raises(RuntimeError, match="evaluation commit failed"):
        _execute_test_run(
            request,
            scenario_repository=scenario_repo,
            agent_repository=agent_repo,
            integration_repository=_SaveRepository(),
            test_case_repository=case_repo,
            test_run_repository=run_repo,
            evaluation_repository=evaluation_repo,
            conversation_repository=conversation_repo,
        )

    assert conversation_repo.saved
    assert not run_repo.saved
