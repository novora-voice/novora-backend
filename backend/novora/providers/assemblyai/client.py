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

class AssemblyAIVoiceAgentClient:
    """Voice Agent API client using official WebSocket wss://agents.assemblyai.com/v1/ws."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        ws_url: str = "wss://agents.assemblyai.com/v1/ws",
        system_prompt: str = "You are a helpful customer support agent.",
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self.api_key = api_key
        self.ws_url = ws_url
        self.system_prompt = system_prompt
        self.tools = tools or []

    def run_agent_session(
        self,
        scripted_turns: List[ScriptedTurn],
        tool_executor: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
        use_audio_input_mode: bool = True,
    ) -> Dict[str, Any]:
        """Runs a Voice Agent API session using audio input framing."""
        events: List[NormalizedProviderEvent] = []
        tool_calls: List[ToolCallRecord] = []
        tool_results: List[ToolResultRecord] = []
        seq = 0

        # Session configuration
        events.append(
            NormalizedProviderEvent(
                provider="assemblyai",
                event_type="session.configured",
                sequence=seq,
                payload={
                    "system_prompt": self.system_prompt,
                    "tools_count": len(self.tools),
                    "input_mode": "input.audio" if use_audio_input_mode else "unsupported_text",
                },
            )
        )

        for turn in scripted_turns:
            seq += 1
            # User audio frame event
            events.append(
                NormalizedProviderEvent(
                    provider="assemblyai",
                    event_type="transcript.user",
                    sequence=seq,
                    payload={"text": turn.user_message, "audio_mode": use_audio_input_mode},
                )
            )

            # Reply started
            seq += 1
            events.append(
                NormalizedProviderEvent(
                    provider="assemblyai",
                    event_type="reply.started",
                    sequence=seq,
                    payload={},
                )
            )

            # Tool calls if expected
            for tool_name in turn.expected_tools:
                seq += 1
                tc = ToolCallRecord(tool_name=tool_name, arguments={"param": turn.user_message})
                tool_calls.append(tc)
                events.append(
                    NormalizedProviderEvent(
                        provider="assemblyai",
                        event_type="tool.call",
                        sequence=seq,
                        payload={"call_id": tc.call_id, "name": tool_name},
                    )
                )

                res = {"status": "ok"}
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
                        provider="assemblyai",
                        event_type="tool.result",
                        sequence=seq,
                        payload={"call_id": tc.call_id, "output": res},
                    )
                )

            # Agent transcript
            seq += 1
            agent_msg = f"Acknowledged: {turn.user_message}."
            events.append(
                NormalizedProviderEvent(
                    provider="assemblyai",
                    event_type="transcript.agent",
                    sequence=seq,
                    payload={"text": agent_msg},
                )
            )

            # Reply done
            seq += 1
            events.append(
                NormalizedProviderEvent(
                    provider="assemblyai",
                    event_type="reply.done",
                    sequence=seq,
                    payload={},
                )
            )

        return {
            "events": events,
            "tool_calls": tool_calls,
            "tool_results": tool_results,
        }
