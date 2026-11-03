"""Tests for Voxia API endpoints and Novora evaluation bridge."""
import base64
from unittest.mock import MagicMock, patch
import pytest
from starlette.testclient import TestClient

from novora.api.main import create_app
from novora.adapters.repositories import (
    InMemoryConversationRepository,
    InMemoryEvaluationRepository,
    InMemoryScenarioRepository,
)
from novora.core.enums import ConversationSource, MessageRole
from novora.voxia.models import SessionStatus, VoxiaSession, VoxiaTurn, TurnRole, ToolCallRecord
from novora.voxia.novora_bridge import session_to_conversation
import novora.api.routes.voxia as voxia_module


@pytest.fixture
def test_client():
    conv_repo = InMemoryConversationRepository()
    scen_repo = InMemoryScenarioRepository(seed_defaults=False)
    eval_repo = InMemoryEvaluationRepository()
    app = create_app(
        scenario_repo=scen_repo,
        evaluation_repo=eval_repo,
        conversation_repo=conv_repo,
    )
    # Put workflow in test mode for deterministic responses
    voxia_module._workflow.test_mode = True
    with TestClient(app) as client:
        yield client
    voxia_module._workflow.test_mode = False


def test_voxia_status_endpoint(test_client):
    response = test_client.get("/api/v1/voxia/status")
    assert response.status_code == 200
    data = response.json()
    assert "active_sessions" in data
    assert "stt_configured" in data
    assert "tts_configured" in data
    assert "stt_model" in data
    assert "tts_model" in data
    assert "llm_model" in data


def test_session_lifecycle_end_to_end(test_client):
    # 1. Start session
    start_resp = test_client.post(
        "/api/v1/voxia/sessions",
        json={"scenario_id": "scen_test_01", "agent_id": "agent_voxia_01"},
    )
    assert start_resp.status_code == 201
    start_data = start_resp.json()
    session_id = start_data["session_id"]
    assert start_data["status"] == "active"

    # 2. Get session
    get_resp = test_client.get(f"/api/v1/voxia/sessions/{session_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == session_id
    assert get_resp.json()["status"] == "active"

    # 3. Submit turn 1 (greeting)
    turn1_resp = test_client.post(
        f"/api/v1/voxia/sessions/{session_id}/turns",
        json={"text": "Hello, I need some help."},
    )
    assert turn1_resp.status_code == 200
    turn1_data = turn1_resp.json()
    assert turn1_data["session_id"] == session_id
    assert "Voxia" in turn1_data["agent_text"]
    assert turn1_data["user_turn"]["content"] == "Hello, I need some help."

    # 4. Submit turn 2 (order lookup)
    turn2_resp = test_client.post(
        f"/api/v1/voxia/sessions/{session_id}/turns",
        json={"text": "Can you check order ORD-1001 for me?"},
    )
    assert turn2_resp.status_code == 200
    turn2_data = turn2_resp.json()
    assert "ORD-1001" in turn2_data["agent_text"]
    assert "Wireless Headphones Pro" in turn2_data["agent_text"]
    assert len(turn2_data["agent_turn"]["tool_calls"]) == 1
    assert turn2_data["agent_turn"]["tool_calls"][0]["tool_name"] == "lookup_order"
    assert turn2_data["agent_turn"]["tool_calls"][0]["executed"] is True

    # 5. Check events
    events_resp = test_client.get(f"/api/v1/voxia/sessions/{session_id}/events")
    assert events_resp.status_code == 200
    events = events_resp.json()["events"]
    event_types = [e["event_type"] for e in events]
    assert "session_started" in event_types
    assert "user_utterance_received" in event_types
    assert "agent_response_generated" in event_types
    assert "tool_requested" in event_types
    assert "tool_executed" in event_types
    assert "business_result_returned" in event_types

    # 6. End session
    end_resp = test_client.post(f"/api/v1/voxia/sessions/{session_id}/end")
    assert end_resp.status_code == 200
    assert end_resp.json()["status"] == "ended"
    assert end_resp.json()["conversation_id"] is not None

    # 7. Submitting turn after session ended should fail
    post_ended_resp = test_client.post(
        f"/api/v1/voxia/sessions/{session_id}/turns",
        json={"text": "Are you still there?"},
    )
    assert post_ended_resp.status_code == 400


def test_submit_turn_with_audio_base64(test_client):
    start_resp = test_client.post("/api/v1/voxia/sessions", json={})
    session_id = start_resp.json()["session_id"]

    # Mock STT transcribe
    with patch.object(
        voxia_module._stt,
        "transcribe",
        return_value={"text": "Where is my order ORD-1002?", "model": "mock", "latency_ms": 12.0, "error": None},
    ):
        fake_audio_b64 = base64.b64encode(b"FAKE_AUDIO_DATA").decode()
        turn_resp = test_client.post(
            f"/api/v1/voxia/sessions/{session_id}/turns",
            json={"audio_base64": fake_audio_b64},
        )
        assert turn_resp.status_code == 200
        data = turn_resp.json()
        assert data["user_turn"]["audio_provided"] is True
        assert "ORD-1002" in data["agent_text"]
        assert "Ergonomic Office Chair" in data["agent_text"]


def test_stt_endpoint(test_client):
    with patch.object(
        voxia_module._stt,
        "transcribe",
        return_value={"text": "Testing remote STT", "model": "mock-whisper", "latency_ms": 10.5, "error": None},
    ):
        # Raw bytes
        resp1 = test_client.post(
            "/api/v1/voxia/stt",
            content=b"BINARY_AUDIO_BYTES",
            headers={"Content-Type": "audio/webm"},
        )
        assert resp1.status_code == 200
        assert resp1.json()["text"] == "Testing remote STT"

        # JSON base64
        resp2 = test_client.post(
            "/api/v1/voxia/stt",
            json={"audio_base64": base64.b64encode(b"AUDIO").decode()},
        )
        assert resp2.status_code == 200
        assert resp2.json()["text"] == "Testing remote STT"


def test_tts_endpoint(test_client):
    fake_audio = b"\x1a\x45\xdf\xa3fake_audio_stream"
    with patch.object(
        voxia_module._tts,
        "synthesize",
        return_value={"audio_bytes": fake_audio, "content_type": "audio/flac", "latency_ms": 20.0, "error": None},
    ):
        resp = test_client.post("/api/v1/voxia/tts", json={"text": "Hello customer"})
        assert resp.status_code == 200
        assert resp.content == fake_audio
        assert resp.headers["content-type"] == "audio/flac"


def test_novora_bridge_conversion():
    session = VoxiaSession(scenario_id="scen_refund_01", agent_id="agent_voxia_01")
    session.turns.append(VoxiaTurn(role=TurnRole.USER, content="Hello"))
    
    tc = ToolCallRecord(
        tool_name="lookup_order",
        arguments={"order_id": "ORD-1001"},
        executed=True,
        result={"found": True, "order": {"status": "shipped"}},
    )
    session.turns.append(VoxiaTurn(role=TurnRole.AGENT, content="Found order ORD-1001", tool_calls=[tc]))

    conv = session_to_conversation(session)
    assert conv.scenario_id == "scen_refund_01"
    assert conv.source == ConversationSource.VOXIA_SESSION
    assert len(conv.messages) == 2
    assert conv.messages[0].role == MessageRole.CUSTOMER
    assert conv.messages[0].content == "Hello"
    assert conv.messages[1].role == MessageRole.AGENT
    assert conv.messages[1].content == "Found order ORD-1001"
    assert len(conv.trusted_action_records) == 1
    assert conv.trusted_action_records[0]["action_type"] == "tool_call:lookup_order"
    assert conv.trusted_action_records[0]["status"] == "success"
    assert conv.trusted_action_records[0]["verified"] is True

