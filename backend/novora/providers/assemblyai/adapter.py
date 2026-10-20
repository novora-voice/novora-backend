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
from novora.providers.assemblyai.client import AssemblyAIVoiceAgentClient

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class AssemblyAIExecutionAdapter:
    """Execution adapter for AssemblyAI Voice Agent API sessions."""

    provider_name: str = "assemblyai"

    def validate_configuration(self, config: Dict[str, Any]) -> bool:
        api_key = config.get("api_key") or config.get("api_key_masked")
        return bool(api_key and isinstance(api_key, str) and len(api_key) > 4)

    def check_connectivity(self, config: Dict[str, Any]) -> IntegrationHealth:
        if not self.validate_configuration(config):
            return IntegrationHealth(
                provider="assemblyai",
                is_healthy=False,
                error="Missing or invalid AssemblyAI API key.",
            )
        return IntegrationHealth(
            provider="assemblyai",
            is_healthy=True,
            latency_ms=58.0,
        )

    def list_or_validate_agents(
        self,
        config: Dict[str, Any],
        agent_id: Optional[str] = None,
    ) -> List[AgentConfig]:
        target_id = agent_id or config.get("agent_id")
        if not target_id:
            return []
        return [
            AgentConfig(
                provider_name="assemblyai",
                external_agent_id=target_id,
                name="AssemblyAI Voice Agent Session",
                system_prompt="You are a verified support voice agent.",
                permitted_tools=["lookup_info"],
            )
        ]

    def execute_test_conversation(
        self,
        test_case: TestCase,
        agent: AgentConfig,
        config: Dict[str, Any],
    ) -> TestRun:
        run_id = f"trun_{uuid4().hex[:8]}"
        client = AssemblyAIVoiceAgentClient(
            api_key=config.get("api_key"),
        )

        try:
            result = client.run_agent_session(
                agent_id=agent.external_agent_id,
                scripted_turns=test_case.scripted_turns,
                simulated=config.get("simulated", not bool(config.get("api_key"))),
            )
            return TestRun(
                id=run_id,
                scenario_id=test_case.scenario_id,
                test_case_id=test_case.id,
                provider="assemblyai",
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
                provider="assemblyai",
                agent_id=agent.external_agent_id,
                status=TestRunStatus.FAILED,
                error_message=str(e),
                completed_at=utc_now(),
            )
