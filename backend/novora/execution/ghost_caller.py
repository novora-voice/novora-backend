from datetime import datetime, timezone
from typing import Any, Dict, Optional
from novora.core.enums import TestRunStatus
from novora.core.execution_models import (
    AgentConfig,
    TestCase,
    TestRun,
)
from novora.core.models import Conversation
from novora.execution.tools import ToolRegistry
from novora.normalization.normalizer import EventNormalizer
from novora.providers.registry import ProviderRegistry, global_provider_registry

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class GhostCallerOrchestrator:
    """Orchestrates programmatic test conversations against provider agents."""

    def __init__(
        self,
        provider_registry: Optional[ProviderRegistry] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ) -> None:
        self.providers = provider_registry or global_provider_registry
        self.tools = tool_registry or ToolRegistry(sandbox_mode=True)

    def execute_test(
        self,
        test_case: TestCase,
        agent: AgentConfig,
        provider_config: Dict[str, Any],
    ) -> tuple[TestRun, Conversation]:
        """Runs the ghost caller, executes permitted tools, and normalizes conversation."""
        adapter = self.providers.get_adapter(agent.provider_name)
        if not adapter:
            run = TestRun(
                scenario_id=test_case.scenario_id,
                test_case_id=test_case.id,
                provider=agent.provider_name,
                agent_id=agent.external_agent_id,
                status=TestRunStatus.FAILED,
                error_message=f"No provider adapter registered for '{agent.provider_name}'.",
                completed_at=utc_now(),
            )
            return run, Conversation(scenario_id=test_case.scenario_id, messages=[])

        execution_config = dict(provider_config)
        execution_config["_tool_executor"] = lambda name, arguments: self._execute_live_tool(
            name, arguments, agent.permitted_tools
        )

        test_run: TestRun = adapter.execute_test_conversation(
            test_case=test_case,
            agent=agent,
            config=execution_config,
        )

        # Execute and validate any requested tool calls through ToolRegistry
        for tc in test_run.tool_calls:
            if tc.status == "requested":
                self.tools.execute_tool(tc, permitted_list=agent.permitted_tools)

        # Normalize events into domain Conversation
        conversation = EventNormalizer.events_to_conversation(
            events=test_run.events,
            scenario_id=test_case.scenario_id,
            provider_name=agent.provider_name,
        )
        test_run.conversation_id = conversation.id

        return test_run, conversation

    def _execute_live_tool(
        self, name: str, arguments: Dict[str, Any], permitted_tools: list[str]
    ) -> Dict[str, Any]:
        from novora.core.execution_models import ToolCallRecord

        call = ToolCallRecord(tool_name=name, arguments=arguments)
        result = self.tools.execute_tool(call, permitted_list=permitted_tools)
        if result.success:
            return result.result
        return {"error": result.result.get("error", "Tool execution failed.")}
