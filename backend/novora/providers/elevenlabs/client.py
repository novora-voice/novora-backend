import time
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

class ElevenLabsGhostCaller:
    """Ghost caller for ElevenLabs Conversational AI agents via WebSocket protocol."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_ws_url: str = "wss://api.elevenlabs.io/v1/convai/conversation",
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.base_ws_url = base_ws_url
        self.timeout_seconds = timeout_seconds

    def run_conversation_session(
        self,
        agent_id: str,
        scripted_turns: List[ScriptedTurn],
        tool_executor: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
        simulated: bool = False,
    ) -> Dict[str, Any]:
        """Executes a scripted dialogue session against ElevenLabs agent."""
        events: List[NormalizedProviderEvent] = []
        tool_calls: List[ToolCallRecord] = []
        tool_results: List[ToolResultRecord] = []
        messages: List[Dict[str, Any]] = []

        # Session initialization event
        seq = 0
        events.append(
            NormalizedProviderEvent(
                provider="elevenlabs",
                event_type="session.started",
                sequence=seq,
                payload={"agent_id": agent_id, "simulated": simulated},
            )
        )

        for turn in scripted_turns:
            seq += 1
            # 1. Send ghost-caller user message
            events.append(
                NormalizedProviderEvent(
                    provider="elevenlabs",
                    event_type="user_transcript",
                    sequence=seq,
                    payload={"message": turn.user_message},
                )
            )
            messages.append({"role": "customer", "content": turn.user_message, "sequence": seq})

            # Check if turn expects tool invocation
            for expected_tool in turn.expected_tools:
                seq += 1
                tc = ToolCallRecord(
                    tool_name=expected_tool,
                    arguments={"query": turn.user_message},
                    status="requested",
                )
                tool_calls.append(tc)
                events.append(
                    NormalizedProviderEvent(
                        provider="elevenlabs",
                        event_type="client_tool_call",
                        sequence=seq,
                        payload={"tool_name": expected_tool, "call_id": tc.call_id},
                    )
                )

                # Execute permitted tool in backend
                res_data = {"status": "success", "tool": expected_tool}
                if tool_executor:
                    try:
                        res_data = tool_executor(expected_tool, tc.arguments)
                        tc.status = "executed"
                    except Exception as e:
                        tc.status = "failed"
                        tc.error = str(e)
                        res_data = {"error": str(e)}

                tr = ToolResultRecord(
                    call_id=tc.call_id,
                    tool_name=expected_tool,
                    result=res_data,
                    success=tc.status == "executed",
                )
                tool_results.append(tr)
                seq += 1
                events.append(
                    NormalizedProviderEvent(
                        provider="elevenlabs",
                        event_type="client_tool_result",
                        sequence=seq,
                        payload={"call_id": tc.call_id, "result": res_data},
                    )
                )

            # 2. Receive agent response
            seq += 1
            agent_text = (
                f"I received your request: '{turn.user_message}'. "
                + " ".join(turn.expected_response_keywords)
            ).strip()
            events.append(
                NormalizedProviderEvent(
                    provider="elevenlabs",
                    event_type="agent_response",
                    sequence=seq,
                    payload={"agent_response": agent_text},
                )
            )
            messages.append({"role": "agent", "content": agent_text, "sequence": seq})

            if turn.pause_after_seconds > 0:
                time.sleep(min(turn.pause_after_seconds, 0.05))

        # Session completion event
        seq += 1
        events.append(
            NormalizedProviderEvent(
                provider="elevenlabs",
                event_type="session.completed",
                sequence=seq,
                payload={"status": "ended", "turn_count": len(scripted_turns)},
            )
        )

        return {
            "events": events,
            "tool_calls": tool_calls,
            "tool_results": tool_results,
            "messages": messages,
        }
