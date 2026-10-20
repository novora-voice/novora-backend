import json
import time
from typing import Any, Dict, List
from urllib.parse import urlencode

from websockets.sync.client import connect

from novora.core.execution_models import NormalizedProviderEvent, ScriptedTurn
from novora.providers.http import request_json


class AssemblyAIVoiceAgentClient:
    """Runs scripted caller turns against a stored AssemblyAI Voice Agent."""

    def __init__(
        self,
        api_key: str,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def run_agent_session(
        self,
        agent_id: str,
        scripted_turns: List[ScriptedTurn],
    ) -> Dict[str, Any]:
        token_response = request_json(
            "GET",
            "https://agents.assemblyai.com/v1/token?" + urlencode({
                "product": "voice_agent",
                "expires_in_seconds": 60,
            }),
            headers={"Authorization": self.api_key},
            timeout=self.timeout_seconds,
        )
        token = token_response.get("token")
        if not token:
            raise RuntimeError("AssemblyAI did not return a Voice Agent session token.")

        events: List[NormalizedProviderEvent] = []
        seq = 0
        ws_url = "wss://agents.assemblyai.com/v1/ws?" + urlencode({"token": token})
        with connect(
            ws_url,
            open_timeout=self.timeout_seconds,
            close_timeout=5,
            ping_timeout=self.timeout_seconds,
        ) as ws:
            ws.send(json.dumps({"type": "session.update", "session": {"agent_id": agent_id}}))
            self._receive_until(ws, {"session.ready"}, events, seq)

            for turn in scripted_turns:
                seq += 1
                scripted_user_event = NormalizedProviderEvent(
                    provider="assemblyai",
                    event_type="transcript.user",
                    sequence=seq,
                    payload={"text": turn.user_message},
                )
                events.append(scripted_user_event)
                # Voice Agent API supports text injection, followed by an explicit
                # reply.create to make the configured stored agent answer.
                ws.send(json.dumps({
                    "type": "conversation.message",
                    "role": "user",
                    "content": turn.user_message,
                }))
                ws.send(json.dumps({"type": "reply.create"}))
                response_events = self._receive_until(ws, {"reply.done"}, events, seq)
                complete_transcripts = [
                    str(item.get("text", "")).strip()
                    for item in response_events
                    if item.get("type") == "transcript.agent" and item.get("text")
                ]
                transcript_deltas = [
                    str(item.get("delta", ""))
                    for item in response_events
                    if item.get("type") == "transcript.agent.delta" and item.get("delta")
                ]
                reply_text = (
                    complete_transcripts[-1]
                    if complete_transcripts
                    else "".join(transcript_deltas)
                ).strip()
                if not reply_text:
                    raise RuntimeError("AssemblyAI completed the turn without an agent text transcript.")
                if not complete_transcripts:
                    events.append(NormalizedProviderEvent(
                        provider="assemblyai",
                        event_type="transcript.agent",
                        sequence=seq + 1,
                        payload={"text": reply_text},
                    ))
                seq += 1

            ws.send(json.dumps({"type": "session.end"}))
            self._receive_until(ws, {"session.ended"}, events, seq)

        return {"events": events, "tool_calls": [], "tool_results": []}

    def _receive_until(
        self,
        ws: Any,
        terminal_types: set[str],
        events: List[NormalizedProviderEvent],
        sequence: int,
    ) -> List[Dict[str, Any]]:
        received: List[Dict[str, Any]] = []
        deadline = time.monotonic() + self.timeout_seconds
        for _ in range(400):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"Timed out waiting for AssemblyAI event: {', '.join(sorted(terminal_types))}."
                )
            event = json.loads(ws.recv(timeout=remaining))
            received.append(event)
            kind = event.get("type", "provider_event")
            payload = {key: value for key, value in event.items() if key != "data"} if kind == "reply.audio" else event
            events.append(NormalizedProviderEvent(
                provider="assemblyai",
                event_type=kind,
                sequence=sequence + 1,
                payload=payload,
            ))
            if kind in {"error", "session.error"}:
                raise RuntimeError(
                    f"AssemblyAI session error: {event.get('message') or event.get('error') or event}"
                )
            if kind in terminal_types:
                return received
        raise TimeoutError(
            f"AssemblyAI did not emit an expected terminal event: {', '.join(sorted(terminal_types))}."
        )
