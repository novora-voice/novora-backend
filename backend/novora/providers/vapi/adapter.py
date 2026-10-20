from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from time import perf_counter
from uuid import uuid4
from novora.core.enums import TestRunStatus
from novora.core.execution_models import (
    AgentConfig,
    IntegrationHealth,
    TestCase,
    TestRun,
)
from novora.providers.vapi.client import VapiTestClient
from novora.providers.http import ProviderRequestError, request_json_value

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class VapiExecutionAdapter:
    """Execution adapter for Vapi assistants."""

    provider_name: str = "vapi"

    def validate_configuration(self, config: Dict[str, Any]) -> bool:
        api_key = config.get("api_key") or config.get("api_key_masked")
        return bool(api_key and isinstance(api_key, str) and len(api_key) > 4)

    def check_connectivity(self, config: Dict[str, Any]) -> IntegrationHealth:
        api_key = config.get("api_key") or config.get("api_key_masked")
        if not api_key or not isinstance(api_key, str) or len(api_key) <= 4:
            return IntegrationHealth(
                provider="vapi",
                is_healthy=False,
                error="Missing or invalid Vapi API key.",
            )
        started = perf_counter()
        try:
            assistants = request_json_value(
                "GET",
                "https://api.vapi.ai/assistant?limit=1",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=15,
            )
            if not isinstance(assistants, list):
                raise ProviderRequestError("Vapi returned an unexpected assistant list response.")
            return IntegrationHealth(
                provider="vapi",
                is_healthy=True,
                latency_ms=round((perf_counter() - started) * 1000, 2),
            )
        except ProviderRequestError as exc:
            return IntegrationHealth(
                provider="vapi",
                is_healthy=False,
                latency_ms=round((perf_counter() - started) * 1000, 2),
                error=str(exc),
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
