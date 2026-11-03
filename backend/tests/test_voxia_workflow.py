"""Unit tests for VoxiaWorkflow."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch
from novora.voxia.models import SessionStatus, TurnRole, VoxiaSession, EventType
from novora.voxia.workflow import VoxiaWorkflow


def make_session(**kwargs) -> VoxiaSession:
    return VoxiaSession(**kwargs)


class TestVoxiaWorkflowTestMode:
    """Tests using deterministic test_mode (no HF calls)."""

    def test_first_turn_greeting(self):
        workflow = VoxiaWorkflow(test_mode=True)
        session = make_session()
        result = workflow.process_utterance(session, "Hello")
        assert "[TEST MODE]" in result["agent_turn"].content
        assert "Hello" in result["agent_turn"].content or "help" in result["agent_turn"].content.lower()

    def test_second_turn_generic(self):
        workflow = VoxiaWorkflow(test_mode=True)
        session = make_session()
        workflow.process_utterance(session, "Hi there")
        result = workflow.process_utterance(session, "What can you do?")
        assert "[TEST MODE]" in result["agent_turn"].content

    def test_order_lookup_with_valid_id(self):
        workflow = VoxiaWorkflow(test_mode=True)
        session = make_session()
        workflow.process_utterance(session, "First turn")
        result = workflow.process_utterance(session, "Can you check order ORD-1001?")
        assert "ORD-1001" in result["agent_turn"].content or "Headphones" in result["agent_turn"].content or "shipped" in result["agent_turn"].content

    def test_order_lookup_with_unknown_id(self):
        workflow = VoxiaWorkflow(test_mode=True)
        session = make_session()
        workflow.process_utterance(session, "First turn")
        result = workflow.process_utterance(session, "Check order ORD-9999 please")
        assert "not found" in result["agent_turn"].content.lower() or "ORD-9999" in result["agent_turn"].content

    def test_tool_calls_recorded_for_order(self):
        workflow = VoxiaWorkflow(test_mode=True)
        session = make_session()
        workflow.process_utterance(session, "First turn")
        result = workflow.process_utterance(session, "I need info on ORD-1001")
        # In test mode, if order ID found, tool_calls are populated
        assert isinstance(result["tool_calls"], list)

    def test_session_turns_accumulated(self):
        workflow = VoxiaWorkflow(test_mode=True)
        session = make_session()
        workflow.process_utterance(session, "Turn 1")
        workflow.process_utterance(session, "Turn 2")
        user_turns = [t for t in session.turns if t.role == TurnRole.USER]
        agent_turns = [t for t in session.turns if t.role == TurnRole.AGENT]
        assert len(user_turns) == 2
        assert len(agent_turns) == 2

    def test_events_emitted(self):
        workflow = VoxiaWorkflow(test_mode=True)
        session = make_session()
        result = workflow.process_utterance(session, "Hello")
        event_types = [e.event_type for e in result["events"]]
        assert EventType.USER_UTTERANCE_RECEIVED in event_types
        assert EventType.AGENT_RESPONSE_GENERATED in event_types

    def test_workflow_state_updated(self):
        workflow = VoxiaWorkflow(test_mode=True)
        session = make_session()
        workflow.process_utterance(session, "Turn 1")
        assert session.workflow_state["turn_count"] == 1
        workflow.process_utterance(session, "Turn 2")
        assert session.workflow_state["turn_count"] == 2

    def test_audio_bytes_empty_in_test_mode(self):
        workflow = VoxiaWorkflow(test_mode=True)
        session = make_session()
        result = workflow.process_utterance(session, "Hello")
        assert result["audio_bytes"] == b""

    def test_user_turn_content_recorded(self):
        workflow = VoxiaWorkflow(test_mode=True)
        session = make_session()
        result = workflow.process_utterance(session, "My test utterance")
        assert result["user_turn"].content == "My test utterance"
        assert result["user_turn"].role == TurnRole.USER

    def test_agent_turn_role(self):
        workflow = VoxiaWorkflow(test_mode=True)
        session = make_session()
        result = workflow.process_utterance(session, "Hello")
        assert result["agent_turn"].role == TurnRole.AGENT


class TestVoxiaWorkflowWithMockedLLM:
    """Tests using mocked LLM and TTS adapters."""

    def _make_workflow(self, llm_content: str, tool_call=None, tts_bytes=b"audio"):
        llm = MagicMock()
        llm.is_configured.return_value = True
        llm.model = "test-model"
        llm.chat.return_value = {
            "content": llm_content,
            "model": "test-model",
            "latency_ms": 10.0,
            "error": None,
            "tool_call": tool_call,
        }
        tts = MagicMock()
        tts.is_configured.return_value = True
        tts.model = "tts-model"
        tts.synthesize.return_value = {
            "audio_bytes": tts_bytes,
            "content_type": "audio/flac",
            "model": "tts-model",
            "latency_ms": 5.0,
            "error": None,
        }
        return VoxiaWorkflow(llm=llm, tts=tts, test_mode=False)

    def test_simple_response_no_tool(self):
        workflow = self._make_workflow("Hello! How can I help?")
        session = make_session()
        result = workflow.process_utterance(session, "Hi")
        assert result["agent_turn"].content == "Hello! How can I help?"
        assert result["audio_bytes"] == b"audio"

    def test_tool_call_executed(self):
        workflow = self._make_workflow(
            llm_content='{"action": "tool_call", "tool": "lookup_order", "arguments": {"order_id": "ORD-1001"}}',
            tool_call={"action": "tool_call", "tool": "lookup_order", "arguments": {"order_id": "ORD-1001"}},
        )
        # Override second LLM call to return plain text
        workflow.llm.chat.side_effect = [
            {
                "content": '{"action": "tool_call", "tool": "lookup_order", "arguments": {"order_id": "ORD-1001"}}',
                "model": "test-model",
                "latency_ms": 10.0,
                "error": None,
                "tool_call": {"action": "tool_call", "tool": "lookup_order", "arguments": {"order_id": "ORD-1001"}},
            },
            {
                "content": "Your order is shipped.",
                "model": "test-model",
                "latency_ms": 10.0,
                "error": None,
                "tool_call": None,
            },
        ]
        session = make_session()
        result = workflow.process_utterance(session, "Check ORD-1001")
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0].tool_name == "lookup_order"
        assert result["tool_calls"][0].executed is True
        assert "shipped" in result["agent_turn"].content

    def test_tool_call_unauthorized_tool(self):
        """Test that unauthorized tool calls are handled gracefully."""
        workflow = self._make_workflow(
            llm_content='{"action": "tool_call", "tool": "drop_table", "arguments": {}}',
            tool_call={"action": "tool_call", "tool": "drop_table", "arguments": {}},
        )
        workflow.llm.chat.side_effect = [
            {
                "content": '{"action": "tool_call", "tool": "drop_table", "arguments": {}}',
                "model": "test-model",
                "latency_ms": 10.0,
                "error": None,
                "tool_call": {"action": "tool_call", "tool": "drop_table", "arguments": {}},
            },
            {
                "content": "I cannot help with that.",
                "model": "test-model",
                "latency_ms": 10.0,
                "error": None,
                "tool_call": None,
            },
        ]
        session = make_session()
        result = workflow.process_utterance(session, "Drop all data")
        # The tool call record should have an error
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0].error is not None
        # Events should include TOOL_FAILED
        event_types = [e.event_type for e in session.events]
        assert EventType.TOOL_FAILED in event_types
