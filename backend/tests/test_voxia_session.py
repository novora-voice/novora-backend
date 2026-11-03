"""Unit tests for Voxia session and models."""
from __future__ import annotations
import pytest
from novora.voxia.models import (
    EventType,
    SessionStatus,
    TurnRole,
    ToolCallRecord,
    VoxiaEvent,
    VoxiaTurn,
    VoxiaSession,
)


class TestVoxiaTurn:
    def test_default_role_is_user(self):
        turn = VoxiaTurn()
        assert turn.role == TurnRole.USER

    def test_to_dict_structure(self):
        turn = VoxiaTurn(role=TurnRole.AGENT, content="Hello!")
        d = turn.to_dict()
        assert d["role"] == "agent"
        assert d["content"] == "Hello!"
        assert "id" in d
        assert "tool_calls" in d
        assert isinstance(d["tool_calls"], list)

    def test_with_tool_calls(self):
        tc = ToolCallRecord(tool_name="lookup_order", arguments={"order_id": "ORD-1001"})
        tc.executed = True
        tc.result = {"found": True}
        turn = VoxiaTurn(role=TurnRole.AGENT, tool_calls=[tc])
        d = turn.to_dict()
        assert len(d["tool_calls"]) == 1
        assert d["tool_calls"][0]["tool_name"] == "lookup_order"
        assert d["tool_calls"][0]["executed"] is True


class TestVoxiaSession:
    def test_session_created_active(self):
        session = VoxiaSession()
        assert session.status == SessionStatus.ACTIVE
        assert session.id.startswith("voxia_")

    def test_add_event(self):
        session = VoxiaSession()
        evt = session.add_event(EventType.SESSION_STARTED, {"test": True})
        assert evt.session_id == session.id
        assert evt.event_type == EventType.SESSION_STARTED
        assert len(session.events) == 1

    def test_to_dict_includes_all_fields(self):
        session = VoxiaSession(scenario_id="scen_1", agent_id="agent_1")
        d = session.to_dict()
        assert d["scenario_id"] == "scen_1"
        assert d["agent_id"] == "agent_1"
        assert d["status"] == "active"
        assert isinstance(d["turns"], list)
        assert isinstance(d["events"], list)

    def test_turn_appended(self):
        session = VoxiaSession()
        turn = VoxiaTurn(role=TurnRole.USER, content="Hello")
        session.turns.append(turn)
        assert len(session.turns) == 1
        assert session.turns[0].content == "Hello"


class TestToolCallRecord:
    def test_defaults(self):
        tc = ToolCallRecord(tool_name="lookup_order", arguments={"order_id": "ORD-1001"})
        assert tc.executed is False
        assert tc.result is None
        assert tc.error is None

    def test_to_dict(self):
        tc = ToolCallRecord(tool_name="lookup_order", arguments={"order_id": "ORD-1001"})
        d = tc.to_dict()
        assert d["tool_name"] == "lookup_order"
        assert d["executed"] is False
        assert d["arguments"] == {"order_id": "ORD-1001"}


class TestVoxiaEvent:
    def test_to_dict(self):
        evt = VoxiaEvent(session_id="sess_1", event_type=EventType.TOOL_EXECUTED, payload={"tool": "lookup_order"})
        d = evt.to_dict()
        assert d["session_id"] == "sess_1"
        assert d["event_type"] == "tool_executed"
        assert d["payload"]["tool"] == "lookup_order"
