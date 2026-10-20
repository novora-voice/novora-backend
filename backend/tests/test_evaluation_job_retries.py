import asyncio

from novora.api.routes import test_runs
from novora.core.execution_models import AgentConfig, EvaluationJobState
from novora.core.models import EvaluationScenario


def test_cloudflare_owner_action_error_is_marked_non_retryable():
    message = (
        'Provider API returned HTTP 403: '
        '{"cloudflare_error":true,"retryable":false,"owner_action_required":true}'
    )

    assert test_runs._is_provider_owner_action_error(message)
    assert not test_runs._is_provider_owner_action_error(
        'Provider API returned HTTP 403: {"cloudflare_error":true,"retryable":true}'
    )


def test_owner_action_error_fails_job_without_arq_retry(monkeypatch):
    scenario = EvaluationScenario(
        id="scenario_retry_test",
        name="Retry test",
        business_goal="Test retries",
        success_criteria=[],
        rules=[],
    )
    agent = AgentConfig(
        provider_name="vapi",
        external_agent_id="assistant-test",
        name="Vapi assistant",
    )
    request = test_runs.TestRunExecutionRequest(scenario=scenario, agent=agent)
    state = EvaluationJobState(
        id="evaljob_no_retry",
        status="queued",
        request_data=request.model_dump(mode="json"),
    )

    class Repository:
        def __init__(self):
            self.current = state

        def get(self, _job_id):
            return self.current

        def save(self, value):
            self.current = value

    repository = Repository()
    monkeypatch.setattr(test_runs, "_evaluation_job_repository", lambda: repository)

    def fail_without_retry(_request):
        raise test_runs.NonRetryableEvaluationError(
            'Provider API returned HTTP 403: '
            '{"cloudflare_error":true,"retryable":false,"owner_action_required":true}'
        )

    monkeypatch.setattr(test_runs, "_execute_test_run", fail_without_retry)

    result = asyncio.run(test_runs.execute_test_run_job({"job_try": 1}, state.id, state.request_data))

    assert result["status"] == "failed"
    assert repository.current.status == "failed"
    assert repository.current.attempt == 1
    assert "owner_action_required" in repository.current.error
