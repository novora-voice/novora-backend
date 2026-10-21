import json
from typing import Any, Dict, List

from websockets.sync.client import connect

from novora.core.exceptions import NovoraError
from novora.core.execution_models import NormalizedProviderEvent, ScriptedTurn
from novora.providers.http import request_json


class VapiSecurityError(NovoraError):
    """Raised if a test attempts an unauthorized outbound PSTN call."""


class VapiTestClient:
    """Creates a Vapi WebSocket call and drives it with text-control messages."""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.vapi.ai",
        timeout_seconds: float = 45.0,
        allow_outbound_pstn: bool = False,
        **_: Any,
    ) -> None:
        self.api_key = api_key or ""
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.allow_outbound_pstn = allow_outbound_pstn

    def run_staging_test(
        self,
        assistant_id: str,
        scripted_turns: List[ScriptedTurn],
        destination_phone: str | None = None,
        simulated: bool = False,
        **_: Any,
    ) -> Dict[str, Any]:
        if destination_phone and not self.allow_outbound_pstn:
            raise VapiSecurityError("Outbound phone calling is strictly disabled for evaluation tests.")

        if simulated or not self.api_key:
            events: List[NormalizedProviderEvent] = []
            seq = 0
            for turn in scripted_turns:
                seq += 1
                events.append(
                    NormalizedProviderEvent(
                        provider="vapi",
                        event_type="transcript.user",
                        sequence=seq,
                        payload={"text": turn.user_message},
                    )
                )
                seq += 1
                events.append(
                    NormalizedProviderEvent(
                        provider="vapi",
                        event_type="transcript",
                        sequence=seq,
                        payload={"text": f"Vapi Assistant: Received '{turn.user_message}'."},
                    )
                )
            return {"events": events, "tool_calls": [], "tool_results": []}
        created = request_json(
            "POST", f"{self.base_url}/call",
            headers={"Authorization": f"Bearer {self.api_key}"},
            payload={"assistantId": assistant_id, "transport": {"provider": "vapi.websocket", "audioFormat": {"format": "pcm", "container": "raw", "sampleRate": 16000}}},
            timeout=self.timeout_seconds,
        )
        ws_url = created.get("websocketCallUrl") or created.get("transport", {}).get("websocketCallUrl")
        if not ws_url:
            raise RuntimeError("Vapi did not return a websocketCallUrl for the created call.")

        events: List[NormalizedProviderEvent] = []
        seq = 0
        with connect(ws_url, open_timeout=self.timeout_seconds, close_timeout=5, ping_timeout=self.timeout_seconds) as ws:
            for turn in scripted_turns:
                ws.send(json.dumps({"type": "add-message", "message": {"role": "user", "content": turn.user_message}}))
                seq += 1
                events.append(NormalizedProviderEvent(provider="vapi", event_type="transcript.user", sequence=seq, payload={"text": turn.user_message}))
                chunks: List[str] = []
                for _ in range(200):
                    data = ws.recv(timeout=self.timeout_seconds)
                    if isinstance(data, bytes):
                        continue
                    event = json.loads(data)
                    kind = event.get("type", "provider_event")
                    events.append(NormalizedProviderEvent(provider="vapi", event_type=kind, sequence=seq + 1, payload=event))
                    message = event.get("message") or {}
                    if kind in {"transcript", "speech-update", "assistant.message"} and message.get("role") in {"assistant", "bot"}:
                        chunks.append(str(message.get("content") or event.get("text") or ""))
                    if kind == "end-of-call-report":
                        raise RuntimeError("Vapi ended the WebSocket call before the scripted evaluation finished.")
                    if chunks and kind in {"transcript", "speech-update", "assistant.message"}:
                        break
                    if kind == "error":
                        raise RuntimeError(f"Vapi WebSocket error: {event}")
                answer = " ".join(part for part in chunks if part).strip()
                if not answer:
                    raise RuntimeError("Vapi WebSocket returned no assistant text response for a test turn.")
                seq += 1
                events.append(NormalizedProviderEvent(provider="vapi", event_type="transcript.agent", sequence=seq, payload={"text": answer}))
        return {"events": events, "tool_calls": [], "tool_results": []}
