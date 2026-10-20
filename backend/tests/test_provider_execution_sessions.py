import json

from novora.core.enums import OverallStatus, TestRunStatus
from novora.core.execution_models import AgentConfig, ScriptedTurn, TestCase, TestRun
from novora.core.models import Conversation, EvaluationReport
from novora.providers.assemblyai import client as assemblyai_client
from novora.providers.assemblyai.adapter import AssemblyAIExecutionAdapter
from novora.providers.elevenlabs import client as elevenlabs_client
from novora.api.routes import test_runs
from novora.scenarios.templates import create_customer_support_template


class FakeWebSocket:
    def __init__(self, incoming_events):
        self.incoming_events = iter(incoming_events)
        self.sent = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def recv(self, timeout=None):
        try:
            event = next(self.incoming_events)
        except StopIteration as exc:
            raise TimeoutError("No more fake WebSocket events.") from exc
        return json.dumps(event)

    def send(self, message):
        self.sent.append(json.loads(message))


def test_elevenlabs_waits_for_response_complete(monkeypatch):
    websocket = FakeWebSocket(
        [
            {"type": "conversation_initiation_metadata", "conversation_initiation_metadata_event": {}},
            {"type": "agent_response", "agent_response_event": {"agent_response": "Your order is on its way."}},
            {"type": "audio", "audio_event": {"audio_base_64": "encoded"}},
            {"type": "agent_response_complete", "agent_response_complete_event": {"event_id": 4}},
        ]
    )
    monkeypatch.setattr(
        elevenlabs_client,
        "request_json",
        lambda *args, **kwargs: {"signed_url": "wss://example.invalid/session"},
    )
    monkeypatch.setattr(elevenlabs_client, "connect", lambda *args, **kwargs: websocket)

    result = elevenlabs_client.ElevenLabsGhostCaller(api_key="test-key").run_conversation_session(
        agent_id="agent_test",
        scripted_turns=[ScriptedTurn(sequence=1, user_message="Where is my order?")],
    )

    assert websocket.closed
    assert result["messages"][-1]["content"] == "Your order is on its way."
    assert any(event.event_type == "agent_response_complete" for event in result["events"])


def test_elevenlabs_fails_if_response_never_completes(monkeypatch):
    websocket = FakeWebSocket(
        [
            {"type": "conversation_initiation_metadata", "conversation_initiation_metadata_event": {}},
            {"type": "agent_response", "agent_response_event": {"agent_response": "One moment."}},
        ]
    )
    monkeypatch.setattr(
        elevenlabs_client,
        "request_json",
        lambda *args, **kwargs: {"signed_url": "wss://example.invalid/session"},
    )
    monkeypatch.setattr(elevenlabs_client, "connect", lambda *args, **kwargs: websocket)

    try:
        elevenlabs_client.ElevenLabsGhostCaller(api_key="test-key", timeout_seconds=1).run_conversation_session(
            agent_id="agent_test",
            scripted_turns=[ScriptedTurn(sequence=1, user_message="Hello.")],
        )
    except TimeoutError:
        pass
    else:
        raise AssertionError("The WebSocket must continue reading until response completion.")


def test_elevenlabs_surfaces_guardrail_and_session_errors(monkeypatch):
    monkeypatch.setattr(
        elevenlabs_client,
        "request_json",
        lambda *args, **kwargs: {"signed_url": "wss://example.invalid/session"},
    )

    for event, expected in [
        ({"type": "guardrail_triggered"}, "guardrail was triggered"),
        ({"type": "client_error", "client_error_event": {"message": "agent unavailable"}}, "agent unavailable"),
    ]:
        websocket = FakeWebSocket([
            {"type": "conversation_initiation_metadata", "conversation_initiation_metadata_event": {}},
            event,
        ])
        monkeypatch.setattr(elevenlabs_client, "connect", lambda *args, **kwargs: websocket)
        try:
            elevenlabs_client.ElevenLabsGhostCaller(api_key="test-key").run_conversation_session(
                agent_id="agent_test",
                scripted_turns=[ScriptedTurn(sequence=1, user_message="Hello.")],
            )
        except RuntimeError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError("Provider error events must end the evaluation with a clear reason.")


def test_assemblyai_sends_text_and_waits_for_agent_turn(monkeypatch):
    websocket = FakeWebSocket(
        [
            {"type": "session.ready"},
            {"type": "transcript.agent.delta", "delta": "The order "},
            {"type": "transcript.agent.delta", "delta": "is on its way."},
            {"type": "transcript.agent", "text": "The order is on its way."},
            {"type": "reply.done"},
            {"type": "session.ended"},
        ]
    )
    request_args = []
    monkeypatch.setattr(
        assemblyai_client,
        "request_json",
        lambda *args, **kwargs: {"token": "test-token"},
    )
    def record_connect(url, **kwargs):
        request_args.append((url, kwargs))
        return websocket

    monkeypatch.setattr(assemblyai_client, "connect", record_connect)
    client = assemblyai_client.AssemblyAIVoiceAgentClient(api_key="assembly-test-key")
    result = client.run_agent_session(
        agent_id="stored-assembly-agent",
        scripted_turns=[ScriptedTurn(sequence=1, user_message="Where is my order?")],
    )

    sent = websocket.sent
    assert sent[0] == {
        "type": "session.update",
        "session": {"agent_id": "stored-assembly-agent"},
    }
    assert {"type": "conversation.message", "role": "user", "content": "Where is my order?"} in sent
    assert {"type": "reply.create"} in sent
    assert not any(message["type"] == "input.audio" for message in sent)
    assert sent[-1] == {"type": "session.end"}
    assert "token=test-token" in request_args[0][0]
    assert any(event.event_type == "reply.done" for event in result["events"])
    assert any(
        event.event_type == "transcript.agent" and event.payload.get("text") == "The order is on its way."
        for event in result["events"]
    )
    assert sum(event.event_type == "transcript.agent" for event in result["events"]) == 1


def test_assemblyai_adapter_uses_the_selected_agent_id(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured["config"] = kwargs

        def run_agent_session(self, **kwargs):
            captured["session"] = kwargs
            return {"events": [], "tool_calls": []}

    monkeypatch.setattr(
        "novora.providers.assemblyai.adapter.AssemblyAIVoiceAgentClient",
        FakeClient,
    )
    agent = AgentConfig(
        provider_name="assemblyai",
        external_agent_id="stored-agent-id",
        name="AssemblyAI agent",
    )
    test_case = TestCase(
        scenario_id="scenario-test",
        name="Agent test",
        scripted_turns=[ScriptedTurn(sequence=1, user_message="Hello.")],
    )

    run = AssemblyAIExecutionAdapter().execute_test_conversation(
        test_case,
        agent,
        {"api_key": "assembly-key"},
    )

    assert run.status == TestRunStatus.COMPLETED
    assert captured["config"]["api_key"] == "assembly-key"
    assert set(captured["config"]) == {"api_key"}
    assert captured["session"]["agent_id"] == "stored-agent-id"


def test_assemblyai_execution_resolves_credentials_on_backend(monkeypatch):
    class Repository:
        def save(self, _value):
            pass

    class IntegrationRepository:
        def get_by_provider(self, _provider):
            return None

    class FakePipeline:
        def run_pipeline(self, scenario, test_case, agent, provider_config, enable_llm_judge=True, llm_rubrics=None):
            self.provider_config = provider_config
            conversation = Conversation(scenario_id=scenario.id)
            report = EvaluationReport(
                scenario_id=scenario.id,
                conversation_id=conversation.id,
                overall_status=OverallStatus.PASS,
                summary="Provider execution completed.",
            )
            run = TestRun(
                scenario_id=scenario.id,
                test_case_id=test_case.id,
                provider=agent.provider_name,
                agent_id=agent.external_agent_id,
                status=TestRunStatus.COMPLETED,
                conversation_id=conversation.id,
            )
            return run, report, conversation

    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "server-assembly-key")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "unused-elevenlabs-key")
    monkeypatch.setenv("ELEVENLABS_TTS_VOICE_ID", "unused-voice-id")
    pipeline = FakePipeline()
    monkeypatch.setattr(test_runs, "pipeline", pipeline)

    scenario = create_customer_support_template()
    request = test_runs.TestRunExecutionRequest(
        scenario=scenario,
        agent=AgentConfig(
            provider_name="assemblyai",
            external_agent_id="stored-agent-id",
            name="AssemblyAI agent",
        ),
        provider_config={
            "api_key": "untrusted-request-key",
            "elevenlabs_tts_api_key": "untrusted-tts-key",
            "elevenlabs_tts_voice_id": "untrusted-voice-id",
        },
    )
    test_runs._execute_test_run(
        request,
        scenario_repository=Repository(),
        agent_repository=Repository(),
        integration_repository=IntegrationRepository(),
        test_case_repository=Repository(),
        test_run_repository=Repository(),
        evaluation_repository=Repository(),
        conversation_repository=Repository(),
    )

    assert pipeline.provider_config["api_key"] == "server-assembly-key"
    assert "elevenlabs_tts_api_key" not in pipeline.provider_config
    assert "elevenlabs_tts_voice_id" not in pipeline.provider_config
