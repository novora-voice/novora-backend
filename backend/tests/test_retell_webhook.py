"""Tests for Retell voice-agent webhook adapter — normalization and conversation output."""

import pytest
from novora.adapters.providers.retell import RetellAdapter
from novora.core.enums import ConversationSource, MessageRole


def test_retell_parses_call_analyzed_webhook():
    adapter = RetellAdapter()
    payload = {
        "call_id": "retell-call-xyz789",
        "agent_id": "agent-001",
        "call_status": "ended",
        "transcript_object": [
            {"role": "agent", "content": "Hello, how can I help you today?"},
            {"role": "user", "content": "I need to check my order status."},
            {"role": "agent", "content": "Sure! Let me look that up for you."},
        ],
        "call_analysis": {"call_successful": True, "agent_sentiment": "positive"},
    }

    conv = adapter.parse_conversation_webhook(payload)

    assert conv.source == ConversationSource.RETELL_WEBHOOK
    assert conv.id == "retell-call-xyz789"
    assert len(conv.messages) == 3
    assert conv.messages[0].role == MessageRole.AGENT
    assert conv.messages[1].role == MessageRole.CUSTOMER
    assert conv.messages[2].role == MessageRole.AGENT
    assert conv.metadata["call_status"] == "ended"
    assert conv.metadata["call_analysis"]["call_successful"] is True


def test_retell_handles_flat_transcript_field():
    """Some Retell webhooks use 'transcript' list instead of 'transcript_object'."""
    adapter = RetellAdapter()
    payload = {
        "call_id": "retell-call-flat",
        "transcript": [
            {"role": "agent", "content": "Greetings!"},
            {"role": "user", "content": "Hi there."},
        ],
    }
    conv = adapter.parse_conversation_webhook(payload)
    assert len(conv.messages) == 2


def test_retell_assigns_sequence_numbers_correctly():
    adapter = RetellAdapter()
    payload = {
        "call_id": "retell-seq-test",
        "transcript_object": [
            {"role": "user", "content": "Turn zero."},
            {"role": "agent", "content": "Turn one."},
            {"role": "user", "content": "Turn two."},
        ],
    }
    conv = adapter.parse_conversation_webhook(payload)
    seqs = [m.sequence for m in conv.messages]
    assert seqs == [0, 1, 2]


def test_retell_assigns_scenario_id():
    adapter = RetellAdapter()
    payload = {"call_id": "retell-scen", "transcript_object": []}
    conv = adapter.parse_conversation_webhook(payload, scenario_id="scen_retell_01")
    assert conv.scenario_id == "scen_retell_01"


def test_retell_handles_empty_transcript():
    adapter = RetellAdapter()
    payload = {"call_id": "retell-empty", "transcript_object": []}
    conv = adapter.parse_conversation_webhook(payload)
    assert len(conv.messages) == 0


def test_retell_signature_verification():
    adapter = RetellAdapter()
    # Retell uses token equality check
    assert adapter.verify_webhook_signature(b"{}", "bearer-token", "bearer-token") is True
    assert adapter.verify_webhook_signature(b"{}", "wrong", "bearer-token") is False
