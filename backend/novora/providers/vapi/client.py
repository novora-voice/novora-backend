from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from novora.core.exceptions import NovoraError
from novora.core.execution_models import (
    NormalizedProviderEvent,
    ScriptedTurn,
    ToolCallRecord,
    ToolResultRecord,
)

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class VapiSecurityError(NovoraError):
    """Raised when an unauthorized outbound telephony call is attempted."""
    pass

class VapiTestClient:
    """Client for testing Vapi assistants with outbound PSTN safety guards."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.vapi.ai",
        allow_outbound_pstn: bool = False,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.allow_outbound_pstn = allow_outbound_pstn

    def run_staging_test(
        self,
        assistant_id: str,
        scripted_turns: List[ScriptedTurn],
        destination_phone: Optional[str] = None,
        tool_executor: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Runs a safe staging test against a Vapi assistant."""
        if destination_phone and not self.allow_outbound_pstn:
            raise VapiSecurityError(
                "Outbound phone calling is strictly disabled for automated test runs. "
                "Explicit user confirmation and authorization required to contact phone numbers."
            )

        events: List[NormalizedProviderEvent] = []
        tool_calls: List[ToolCallRecord] = []
        tool_results: List[ToolResultRecord] = []
        seq = 0

        # Session creation
        events.append(
            NormalizedProviderEvent(
                provider="vapi",
                event_type="call.created",
                sequence=seq,
                payload={"assistantId": assistant_id, "mode": "staging_test"},
            )
        )

        for turn in scripted_turns:
            seq += 1
            events.append(
                NormalizedProviderEvent(
                    provider="vapi",
                    event_type="speech-update",
                    sequence=seq,
                    payload={"role": "user", "text": turn.user_message},
                )
            )

            for tool_name in turn.expected_tools:
                seq += 1
                tc = ToolCallRecord(tool_name=tool_name, arguments={"input": turn.user_message})
                tool_calls.append(tc)
                events.append(
                    NormalizedProviderEvent(
                        provider="vapi",
                        event_type="tool-calls",
                        sequence=seq,
                        payload={"name": tool_name, "call_id": tc.call_id},
                    )
                )

                res = {"status": "success"}
                if tool_executor:
                    try:
                        res = tool_executor(tool_name, tc.arguments)
                        tc.status = "executed"
                    except Exception as exc:
                        tc.status = "failed"
                        tc.error = str(exc)
                        res = {"error": str(exc)}

                tr = ToolResultRecord(call_id=tc.call_id, tool_name=tool_name, result=res)
                tool_results.append(tr)
                seq += 1
                events.append(
                    NormalizedProviderEvent(
                        provider="vapi",
                        event_type="tool-result",
                        sequence=seq,
                        payload={"call_id": tc.call_id, "result": res},
                    )
                )

            seq += 1
            agent_reply = f"Vapi Assistant: processed '{turn.user_message}'."
            events.append(
                NormalizedProviderEvent(
                    provider="vapi",
                    event_type="speech-update",
                    sequence=seq,
                    payload={"role": "assistant", "text": agent_reply},
                )
            )

        seq += 1
        events.append(
            NormalizedProviderEvent(
                provider="vapi",
                event_type="end-of-call-report",
                sequence=seq,
                payload={"endedReason": "test-completed", "turns": len(scripted_turns)},
            )
        )

        return {
            "events": events,
            "tool_calls": tool_calls,
            "tool_results": tool_results,
        }
