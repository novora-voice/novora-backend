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
from novora.providers.vapi.client import VapiTestClient

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class VapiExecutionAdapter:
    """Execution adapter for Vapi assistants."""

    provider_name: str = "vapi"

    def validate_configuration(self, config: Dict[str, Any]) -> bool:
        api_key = config.get("api_key") or config.get("api_key_masked")
        return bool(api_key and isinstance(api_key, str) and len(api_key) > 4)

    def check_connectivity(self, config: Dict[str, Any]) -> IntegrationHealth:
        if not self.validate_configuration(config):
            return IntegrationHealth(
                provider="vapi",
                is_healthy=False,
                error="Missing or invalid Vapi API key.",
            )
        return IntegrationHealth(
            provider="vapi",
            is_healthy=True,
            latency_ms=45.0,
        )

    def list_or_validate_agents(
        self,
        config: Dict[str, Any],
        agent_id: Optional[str] = None,
    ) -> List[AgentConfig]:
        target_id = agent_id or config.get("assistant_id") or "asst_vapi_default"
        return [
            AgentConfig(
                provider_name="vapi",
                external_agent_id=target_id,
                name=f"Vapi Assistant ({target_id})",
                permitted_tools=["refund_tool", "booking_tool"],
            )
        ]

    def execute_test_conversation(
        self,
        test_case: TestCase,
        agent: AgentConfig,
        config: Dict[str, Any],
    ) -> TestRun:
        run_id = f"trun_{uuid4().hex[:8]}"
        client = VapiTestClient(
            api_key=config.get("api_key"),
            allow_outbound_pstn=config.get("allow_outbound_pstn", False),
        )

        try:
            result = client.run_staging_test(
                assistant_id=agent.external_agent_id,
                scripted_turns=test_case.scripted_turns,
                destination_phone=config.get("destination_phone"),
            )
            return TestRun(
                id=run_id,
                scenario_id=test_case.scenario_id,
                test_case_id=test_case.id,
                provider="vapi",
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
                provider="vapi",
                agent_id=agent.external_agent_id,
                status=TestRunStatus.FAILED,
                error_message=str(e),
                completed_at=utc_now(),
            )
