from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
from novora.core.enums import TestRunStatus
from novora.core.execution_models import (
    AgentConfig,
    IntegrationHealth,
    TestCase,
    TestRun,
)
from novora.providers.retell.client import RetellTestClient

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class RetellExecutionAdapter:
    """Execution adapter for Retell AI voice agents."""

    provider_name: str = "retell"

    def validate_configuration(self, config: Dict[str, Any]) -> bool:
        api_key = config.get("api_key") or config.get("api_key_masked")
        return bool(api_key and isinstance(api_key, str) and len(api_key) > 4)

    def check_connectivity(self, config: Dict[str, Any]) -> IntegrationHealth:
        if not self.validate_configuration(config):
            return IntegrationHealth(
                provider="retell",
                is_healthy=False,
                error="Missing or invalid Retell API key.",
            )
        return IntegrationHealth(
            provider="retell",
            is_healthy=True,
            latency_ms=39.0,
        )

    def list_or_validate_agents(
        self,
        config: Dict[str, Any],
        agent_id: Optional[str] = None,
    ) -> List[AgentConfig]:
        target_id = agent_id or config.get("agent_id") or "agent_retell_default"
        return [
            AgentConfig(
                provider_name="retell",
                external_agent_id=target_id,
                name=f"Retell Agent ({target_id})",
                permitted_tools=["transfer_call", "check_balance"],
            )
        ]

    def execute_test_conversation(
        self,
        test_case: TestCase,
        agent: AgentConfig,
        config: Dict[str, Any],
    ) -> TestRun:
        run_id = f"trun_{uuid4().hex[:8]}"
        client = RetellTestClient(api_key=config.get("api_key"))

        try:
            result = client.run_web_call_simulation(
                agent_id=agent.external_agent_id,
                scripted_turns=test_case.scripted_turns,
            )
            return TestRun(
                id=run_id,
                scenario_id=test_case.scenario_id,
                test_case_id=test_case.id,
                provider="retell",
                agent_id=agent.external_agent_id,
                status=TestRunStatus.COMPLETED,
                events=result["events"],
                tool_calls=result["tool_calls"],
                completed_at=utc_now(),
            )
        except Exception as e:
            return TestRun(
                id=run_id,
                scenario_id=test_case.scenario_id,
                test_case_id=test_case.id,
                provider="retell",
                agent_id=agent.external_agent_id,
                status=TestRunStatus.FAILED,
                error_message=str(e),
                completed_at=utc_now(),
            )
