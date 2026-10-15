"""Tests for InMemoryConversationRepository and conversation API endpoints."""

import pytest
from fastapi.testclient import TestClient
from novora.adapters.repositories import InMemoryConversationRepository
from novora.api.main import create_app
from novora.core.enums import ConversationSource, MessageRole
from novora.core.models import Conversation, ConversationMessage


# -----------------------------------------------------------------------
# InMemoryConversationRepository unit tests
# -----------------------------------------------------------------------

def test_conversation_repository_save_and_get():
    repo = InMemoryConversationRepository()
    conv = Conversation(
        id="conv_test_001",
        source=ConversationSource.TRANSCRIPT_UPLOAD,
        messages=[
            ConversationMessage(
                id="m1",
                role=MessageRole.CUSTOMER,
                content="Hello, I need help.",
                sequence=0,
            ),
            ConversationMessage(
                id="m2",
                role=MessageRole.AGENT,
                content="Sure! How can I assist?",
                sequence=1,
            ),
        ],
    )
    repo.save(conv)

    fetched = repo.get("conv_test_001")
    assert fetched is not None
    assert fetched.id == "conv_test_001"
    assert len(fetched.messages) == 2
    assert fetched.messages[0].role == MessageRole.CUSTOMER


def test_conversation_repository_get_missing_returns_none():
    repo = InMemoryConversationRepository()
    assert repo.get("does_not_exist") is None


def test_conversation_repository_list_all():
    repo = InMemoryConversationRepository()
    for i in range(5):
        repo.save(Conversation(
            id=f"conv_{i:03d}",
            messages=[
                ConversationMessage(
                    id=f"m{i}",
                    role=MessageRole.AGENT,
                    content=f"Message {i}",
                    sequence=0,
                )
            ],
        ))
    result = repo.list_all(limit=3, offset=0)
    assert len(result) == 3

    result_offset = repo.list_all(limit=3, offset=3)
    assert len(result_offset) == 2


def test_conversation_repository_overwrite_on_save():
    repo = InMemoryConversationRepository()
    conv_v1 = Conversation(
        id="conv_overwrite",
        messages=[
            ConversationMessage(id="m1", role=MessageRole.AGENT, content="Version 1", sequence=0),
        ],
    )
    conv_v2 = Conversation(
        id="conv_overwrite",
        messages=[
            ConversationMessage(id="m1", role=MessageRole.AGENT, content="Version 2", sequence=0),
        ],
    )
    repo.save(conv_v1)
    repo.save(conv_v2)

    fetched = repo.get("conv_overwrite")
    assert fetched.messages[0].content == "Version 2"


# -----------------------------------------------------------------------
# Conversation API endpoint tests
# -----------------------------------------------------------------------

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_conversation_persisted_after_transcript_import(client):
    """Importing a transcript should persist the conversation and make it retrievable."""
    res = client.post(
        "/api/v1/conversations/import-transcript",
        json={
            "text": "Customer: I want a refund.\nAgent: Let me check that.",
            "scenario_id": "scen_persist_01",
        },
    )
    assert res.status_code == 200
    data = res.json()
    conv_id = data["id"]
    assert conv_id is not None

    # Retrieve by ID
    get_res = client.get(f"/api/v1/conversations/{conv_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == conv_id
    assert len(get_res.json()["messages"]) == 2


def test_conversation_not_found_returns_404(client):
    res = client.get("/api/v1/conversations/non_existent_conv")
    assert res.status_code == 404


def test_list_conversations_endpoint(client):
    # Import two transcripts to populate the store
    for text in [
        "Customer: Hello.\nAgent: Hi there.",
        "Customer: Need refund.\nAgent: Sure.",
    ]:
        client.post(
            "/api/v1/conversations/import-transcript",
            json={"text": text},
        )

    res = client.get("/api/v1/conversations?limit=10&offset=0")
    assert res.status_code == 200
    assert len(res.json()) >= 2


def test_vapi_webhook_endpoint_persists_conversation(client):
    payload = {
        "message": {
            "call": {"id": "vapi-api-test-001"},
            "messages": [
                {"role": "user", "message": "My order is late."},
                {"role": "assistant", "message": "Let me check that for you."},
            ],
        }
    }
    res = client.post("/api/v1/webhooks/vapi", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "vapi-api-test-001"
    assert len(data["messages"]) == 2
    assert data["source"] == "vapi_webhook"

    # Conversation should now be retrievable
    get_res = client.get(f"/api/v1/conversations/vapi-api-test-001")
    assert get_res.status_code == 200


def test_retell_webhook_endpoint_persists_conversation(client):
    payload = {
        "call_id": "retell-api-test-001",
        "transcript_object": [
            {"role": "agent", "content": "Hello, how can I help?"},
            {"role": "user", "content": "I need to cancel my subscription."},
        ],
    }
    res = client.post("/api/v1/webhooks/retell", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "retell-api-test-001"
    assert len(data["messages"]) == 2
    assert data["source"] == "retell_webhook"

    # Conversation should now be retrievable
    get_res = client.get("/api/v1/conversations/retell-api-test-001")
    assert get_res.status_code == 200
