import time
from typing import Any, Dict, List

from novora.core.execution_models import NormalizedProviderEvent, ScriptedTurn
from novora.providers.http import request_json


class RetellTestClient:
    """Runs a real Retell batch simulation test for a deployed agent."""

    def __init__(self, api_key: str, base_url: str = "https://api.retellai.com", timeout_seconds: float = 300.0) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def run_web_call_simulation(self, agent_id: str, scripted_turns: List[ScriptedTurn], **_: Any) -> Dict[str, Any]:
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
