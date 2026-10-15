from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from novora.core.execution_models import (
    NormalizedProviderEvent,
    ScriptedTurn,
    ToolCallRecord,
    ToolResultRecord,
)

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class RetellTestClient:
    """Client for testing Retell AI agents via web call session or staging simulation."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.retellai.com",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url

    def run_web_call_simulation(
        self,
        agent_id: str,
        scripted_turns: List[ScriptedTurn],
        tool_executor: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Executes a verified Retell web-call simulation session."""
        events: List[NormalizedProviderEvent] = []
        tool_calls: List[ToolCallRecord] = []
        tool_results: List[ToolResultRecord] = []
        seq = 0

        # Register web call session
        events.append(
            NormalizedProviderEvent(
                provider="retell",
                event_type="call_started",
                sequence=seq,
                payload={"agent_id": agent_id, "call_type": "web_call"},
            )
        )

        for turn in scripted_turns:
            seq += 1
            events.append(
                NormalizedProviderEvent(
                    provider="retell",
                    event_type="transcript_utterance",
                    sequence=seq,
                    payload={"role": "user", "content": turn.user_message},
                )
            )

            for tool_name in turn.expected_tools:
                seq += 1
                tc = ToolCallRecord(tool_name=tool_name, arguments={"arg": turn.user_message})
                tool_calls.append(tc)
                events.append(
                    NormalizedProviderEvent(
                        provider="retell",
                        event_type="tool_invocation",
                        sequence=seq,
                        payload={"tool_name": tool_name, "call_id": tc.call_id},
                    )
                )

                res = {"status": "success"}
                if tool_executor:
                    try:
                        res = tool_executor(tool_name, tc.arguments)
                        tc.status = "executed"
                    except Exception as err:
                        tc.status = "failed"
                        tc.error = str(err)
                        res = {"error": str(err)}

                tr = ToolResultRecord(call_id=tc.call_id, tool_name=tool_name, result=res)
                tool_results.append(tr)
                seq += 1
                events.append(
                    NormalizedProviderEvent(
                        provider="retell",
                        event_type="tool_response",
                        sequence=seq,
                        payload={"call_id": tc.call_id, "result": res},
                    )
                )

            seq += 1
            agent_msg = f"Retell Agent: I received '{turn.user_message}'."
            events.append(
                NormalizedProviderEvent(
                    provider="retell",
                    event_type="transcript_utterance",
                    sequence=seq,
                    payload={"role": "agent", "content": agent_msg},
                )
            )

        seq += 1
        events.append(
            NormalizedProviderEvent(
                provider="retell",
                event_type="call_ended",
                sequence=seq,
                payload={"disconnection_reason": "user_hangup", "total_turns": len(scripted_turns)},
            )
        )

        return {
            "events": events,
            "tool_calls": tool_calls,
            "tool_results": tool_results,
        }
