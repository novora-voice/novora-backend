import json
import time
from typing import Any, Dict, List
from urllib.parse import urlencode

from websockets.sync.client import connect

from novora.core.execution_models import NormalizedProviderEvent, ScriptedTurn, ToolCallRecord, ToolResultRecord
from novora.providers.http import request_json


class ElevenLabsGhostCaller:
    """Runs scripted text turns against an ElevenLabs Conversational AI agent."""

    def __init__(self, api_key: str, timeout_seconds: float = 120.0) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def run_conversation_session(self, agent_id: str, scripted_turns: List[ScriptedTurn], tool_executor: Any = None, **_: Any) -> Dict[str, Any]:
        signed = request_json(
            "GET",
            "https://api.elevenlabs.io/v1/convai/conversation/get-signed-url?" + urlencode({"agent_id": agent_id}),
            headers={"xi-api-key": self.api_key},
            timeout=self.timeout_seconds,
        )
        ws_url = signed.get("signed_url")
        if not ws_url:
            raise RuntimeError("ElevenLabs did not return a signed conversation URL.")

        events: List[NormalizedProviderEvent] = []
        tool_calls: List[ToolCallRecord] = []
        tool_results: List[ToolResultRecord] = []
        messages: List[Dict[str, Any]] = []
        seq = 0
        with connect(ws_url, open_timeout=self.timeout_seconds, close_timeout=5, ping_timeout=self.timeout_seconds) as ws:
            # The service sends conversation_initiation_metadata when the session is ready.
            first = json.loads(ws.recv(timeout=self.timeout_seconds))
            events.append(NormalizedProviderEvent(provider="elevenlabs", event_type=first.get("type", "session.started"), sequence=seq, payload=self._safe_event_payload(first)))
            for turn in scripted_turns:
                ws.send(json.dumps({"type": "user_message", "text": turn.user_message}))
                seq += 1
                messages.append({"role": "customer", "content": turn.user_message, "sequence": seq})
                events.append(NormalizedProviderEvent(provider="elevenlabs", event_type="user_transcript", sequence=seq, payload={"message": turn.user_message}))
                answer = ""
                deadline = time.monotonic() + self.timeout_seconds
                for _ in range(100):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Timed out waiting for ElevenLabs to finish the agent response.")
                    event = json.loads(ws.recv(timeout=remaining))
                    kind = event.get("type", "provider_event")
                    details = event.get(f"{kind}_event", event.get(kind, {}))
                    events.append(NormalizedProviderEvent(provider="elevenlabs", event_type=kind, sequence=seq + 1, payload=self._safe_event_payload(event)))
                    if kind in {"agent_response", "agent_response_correction"}:
                        text = details.get("agent_response", event.get("agent_response", ""))
                        if text:
                            answer = text
                    elif kind == "audio" and not answer and event.get("transcript"):
                        answer = event["transcript"]
                    elif kind == "client_tool_call":
                        call_id = details.get("tool_call_id", f"el_tool_{len(tool_calls) + 1}")
                        name = details.get("tool_name", "unknown")
                        call = ToolCallRecord(call_id=call_id, tool_name=name, arguments=details.get("parameters", {}))
                        tool_calls.append(call)
                        try:
                            result = tool_executor(name, call.arguments) if tool_executor else {"error": "No safe tool executor is configured for this agent."}
                            success = isinstance(result, dict) and not result.get("error")
                            call.status = "executed" if success else "forbidden"
                            call.error = None if success else str(result.get("error", "Tool execution failed."))
                        except Exception as exc:
                            result = {"error": str(exc)}
                            success = False
                            call.status = "failed"
                            call.error = str(exc)
                        tool_results.append(ToolResultRecord(call_id=call_id, tool_name=name, result=result, success=success))
                        ws.send(json.dumps({"type": "client_tool_result", "tool_call_id": call_id, "result": json.dumps(result), "is_error": not success}))
                        seq += 1
                        events.append(NormalizedProviderEvent(provider="elevenlabs", event_type="client_tool_result", sequence=seq, payload={"call_id": call_id, "tool_name": name, "result": result}))
                    if kind == "ping":
                        ws.send(json.dumps({"type": "pong", "event_id": details.get("event_id")}))
                    if kind == "agent_response_complete":
                        break
                else:
                    raise TimeoutError("Timed out waiting for ElevenLabs to finish the agent response.")
                answer = answer.strip()
                if not answer:
                    raise RuntimeError("ElevenLabs completed the response without returning agent text for a test turn.")
                seq += 1
                messages.append({"role": "agent", "content": answer, "sequence": seq})
                events.append(NormalizedProviderEvent(provider="elevenlabs", event_type="agent_response", sequence=seq, payload={"agent_response": answer}))
        return {"events": events, "tool_calls": tool_calls, "tool_results": tool_results, "messages": messages}

    @staticmethod
    def _safe_event_payload(event: Dict[str, Any]) -> Dict[str, Any]:
        """Keep provider metadata while avoiding storing large encoded audio frames."""
        event_type = event.get("type", "")
        details = event.get(f"{event_type}_event", event.get(event_type))
        if isinstance(details, dict):
            cleaned = {key: value for key, value in details.items() if key != "audio_base_64"}
            return {"type": event.get("type"), f"{event.get('type')}_event": cleaned}
        return {key: value for key, value in event.items() if key != "audio_base_64"}
