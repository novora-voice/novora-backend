import time
from typing import Any, Dict, List

from novora.core.execution_models import NormalizedProviderEvent, ScriptedTurn, ToolCallRecord, ToolResultRecord
from novora.providers.http import request_json


class RetellTestClient:
    """Runs a real Retell batch simulation test for a deployed agent."""

    def __init__(self, api_key: str = "", base_url: str = "https://api.retellai.com", timeout_seconds: float = 300.0, **_: Any) -> None:
        self.api_key = api_key or ""
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def run_web_call_simulation(
        self,
        agent_id: str,
        scripted_turns: List[ScriptedTurn],
        tool_executor: Any = None,
        simulated: bool = False,
        **_: Any,
    ) -> Dict[str, Any]:
        if simulated or not self.api_key:
            events: List[NormalizedProviderEvent] = []
            tool_calls: List[ToolCallRecord] = []
            tool_results: List[ToolResultRecord] = []
            seq = 0
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
                events.append(
                    NormalizedProviderEvent(
                        provider="retell",
                        event_type="transcript_utterance",
                        sequence=seq,
                        payload={"role": "agent", "content": f"Retell Agent: I received '{turn.user_message}'."},
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
        headers = {"Authorization": f"Bearer {self.api_key}"}
        agent = request_json("GET", f"{self.base_url}/get-agent/{agent_id}", headers=headers)
        engine = agent.get("response_engine")
        if not isinstance(engine, dict) or not engine.get("type") or not (engine.get("llm_id") or engine.get("conversation_flow_id")):
            raise RuntimeError("Retell agent response_engine is missing or unsupported; cannot create a simulation test.")
        prompts = [turn.user_message for turn in scripted_turns]
        created = request_json(
            "POST", f"{self.base_url}/create-test-case-definition", headers=headers,
            payload={"name": f"Novora evaluation {agent_id}", "response_engine": engine, "user_prompt": "\n".join(prompts), "metrics": []},
            timeout=self.timeout_seconds,
        )
        case_id = created.get("test_case_definition_id")
        if not case_id:
            raise RuntimeError(f"Retell did not return a test_case_id: {created}")
        batch = request_json(
            "POST", f"{self.base_url}/create-batch-test", headers=headers,
            payload={"test_case_definition_ids": [case_id], "response_engine": engine},
            timeout=self.timeout_seconds,
        )
        batch_id = batch.get("test_case_batch_job_id")
        if not batch_id:
            raise RuntimeError(f"Retell did not return a batch_test_id: {batch}")

        deadline = time.monotonic() + self.timeout_seconds
        runs: List[Dict[str, Any]] = []
        while time.monotonic() < deadline:
            state = request_json("GET", f"{self.base_url}/get-batch-test/{batch_id}", headers=headers, timeout=30)
            status = str(state.get("status", "")).lower()
            if status in {"complete", "failed", "error"}:
                listing = request_json("GET", f"{self.base_url}/v2/list-test-runs/{batch_id}", headers=headers, timeout=30)
                jobs = listing.get("items", [])
                runs = [
                    request_json("GET", f"{self.base_url}/get-test-run/{item['test_case_job_id']}", headers=headers, timeout=30)
                    for item in jobs if item.get("test_case_job_id")
                ]
                break
            time.sleep(2)
        if not runs:
            raise TimeoutError("Retell batch simulation did not return completed test runs before timeout.")

        events: List[NormalizedProviderEvent] = []
        seq = 0
        transcript = runs[0].get("transcript_snapshot")
        for role, content in self._transcript_messages(transcript):
            seq += 1
            events.append(NormalizedProviderEvent(provider="retell", event_type="transcript.user" if role in {"user", "customer"} else "transcript.agent", sequence=seq, payload={"role": role, "text": content}))
        if not events:
            raise RuntimeError(f"Retell completed its simulation but returned no transcript: {runs[0]}")
        return {"events": events, "tool_calls": [], "tool_results": [], "provider_result": runs[0]}

    @staticmethod
    def _transcript_messages(snapshot: Any) -> List[tuple[str, str]]:
        messages: List[tuple[str, str]] = []
        def walk(value: Any) -> None:
            if isinstance(value, list):
                for item in value:
                    walk(item)
            elif isinstance(value, dict):
                role = value.get("role", value.get("speaker"))
                content = value.get("content", value.get("text"))
                if role and isinstance(content, str) and content.strip():
                    messages.append((str(role).lower(), content.strip()))
                else:
                    for item in value.values():
                        walk(item)
        walk(snapshot)
        return messages
