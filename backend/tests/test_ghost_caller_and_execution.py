import pytest
from novora.core.enums import TestRunStatus
from novora.core.execution_models import (
    AgentConfig,
    ScriptedTurn,
    TestCase,
)
from novora.execution.ghost_caller import GhostCallerOrchestrator
from novora.execution.tools import ToolRegistry
from novora.providers.assemblyai.client import AssemblyAIVoiceAgentClient
from novora.providers.elevenlabs.client import ElevenLabsGhostCaller
from novora.providers.vapi.client import VapiSecurityError, VapiTestClient
from novora.providers.retell.client import RetellTestClient

def test_elevenlabs_ghost_caller_session():
    caller = ElevenLabsGhostCaller()
    turns = [
        ScriptedTurn(
            sequence=1,
            user_message="Hello, where is my order?",
            expected_response_keywords=["order"],
            expected_tools=["check_order"],
        )
    ]
    res = caller.run_conversation_session("agent_el_01", turns, simulated=True)
    assert len(res["events"]) >= 3
    assert len(res["tool_calls"]) == 1
    assert res["tool_calls"][0].tool_name == "check_order"

def test_vapi_pstn_safety_guard():
    client = VapiTestClient(allow_outbound_pstn=False)
    turns = [ScriptedTurn(sequence=1, user_message="Call this number")]
    # Attempting to contact real telephone number without explicit authorization raises VapiSecurityError
    with pytest.raises(VapiSecurityError, match="Outbound phone calling is strictly disabled"):
        client.run_staging_test("asst_vapi_1", turns, destination_phone="+15551234567")

def test_assemblyai_voice_agent_accepts_scripted_text():
    client = AssemblyAIVoiceAgentClient(system_prompt="Support agent")
    turns = [
        ScriptedTurn(
            sequence=1,
            user_message="I have an inquiry about my plan.",
            expected_tools=[],
        )
    ]
    res = client.run_agent_session(turns)
    assert any(e.event_type == "transcript.user" for e in res["events"])
    assert any(e.event_type == "reply.started" for e in res["events"])
    assert any(e.event_type == "reply.done" for e in res["events"])

def test_retell_web_call_simulation():
    client = RetellTestClient()
    turns = [
        ScriptedTurn(
            sequence=1,
            user_message="Can I reschedule my appointment?",
            expected_tools=["booking_tool"],
        )
    ]
    res = client.run_web_call_simulation("agent_retell_9", turns)
    assert any(e.event_type == "call_started" for e in res["events"])
    assert len(res["tool_calls"]) == 1
    assert res["tool_calls"][0].tool_name == "booking_tool"

def test_ghost_caller_orchestrator_execution():
    orchestrator = GhostCallerOrchestrator()
    tc = TestCase(
        scenario_id="scen_test_01",
        name="Order Verification",
        scripted_turns=[
            ScriptedTurn(
                sequence=1,
                user_message="Check order status",
                expected_tools=["check_order"],
            )
        ],
    )
    agent = AgentConfig(
        provider_name="elevenlabs",
        external_agent_id="agent_123",
        name="ElevenLabs Agent",
        permitted_tools=["check_order"],
    )
    run, conv = orchestrator.execute_test(tc, agent, {"simulated": True})
    assert run.status == TestRunStatus.COMPLETED
    assert len(run.tool_calls) == 1
    assert run.tool_calls[0].status == "executed"
    assert len(conv.messages) >= 2
    assert len(conv.trusted_action_records) == 1
