import pytest
from novora.adapters.providers.neutral_ingestion import NeutralIngestionAdapter
from novora.core.enums import MessageRole
from novora.core.exceptions import (
    PayloadSizeLimitError,
    PayloadValidationError,
)

def test_neutral_ingestion_valid_payload():
    payload = {
        "conversation_id": "conv_neutral_01",
        "messages": [
            {
                "id": "m1",
                "role": "customer",
                "content": "Hi, where is my order #1234?",
                "sequence": 0,
                "timestamp": "2026-10-12T12:00:00Z",
            },
            {
                "id": "m2",
                "role": "assistant",
                "content": "I am checking order #1234 right now.",
                "sequence": 1,
                "timestamp": 1791806415,
            },
        ],
    }

    conv = NeutralIngestionAdapter.ingest(payload, scenario_id="scen_01")
    assert conv.id == "conv_neutral_01"
    assert conv.scenario_id == "scen_01"
    assert len(conv.messages) == 2
    assert conv.messages[0].role == MessageRole.CUSTOMER
    assert conv.messages[1].role == MessageRole.AGENT
    assert conv.messages[0].timestamp is not None
    assert conv.messages[1].timestamp is not None

def test_neutral_ingestion_missing_messages_raises():
    with pytest.raises(PayloadValidationError, match="missing required 'messages'"):
        NeutralIngestionAdapter.ingest({"conversation_id": "c1"})

def test_neutral_ingestion_empty_content_raises():
    payload = {
        "messages": [{"role": "user", "content": "   "}]
    }
    with pytest.raises(PayloadValidationError, match="empty content"):
        NeutralIngestionAdapter.ingest(payload)

def test_neutral_ingestion_exceeding_message_count_limit():
    payload = {
        "messages": [{"role": "user", "content": f"msg {i}"} for i in range(1005)]
    }
    with pytest.raises(PayloadSizeLimitError, match="exceeds maximum allowed limit"):
        NeutralIngestionAdapter.ingest(payload)
