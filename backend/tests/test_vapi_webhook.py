"""Tests for Vapi voice-agent webhook adapter — normalization and conversation output."""

import pytest
from novora.adapters.providers.vapi import VapiAdapter
from novora.core.enums import ConversationSource, MessageRole, RuleStatus, RuleType


def test_vapi_parses_end_of_call_report():
    adapter = VapiAdapter()
    payload = {
        "message": {
            "call": {"id": "vapi-call-abc123"},
            "messages": [
                {"role": "user", "message": "Hello, I need help with my account."},
                {"role": "assistant", "message": "Sure, let me look that up."},
                {"role": "user", "message": "My email is test@example.com."},
            ],
            "endedReason": "customer-ended-call",
            "duration": 45,
            "cost": 0.02,
        }
    }

    conv = adapter.parse_conversation_webhook(payload)

    assert conv.source == ConversationSource.VAPI_WEBHOOK
    assert conv.id == "vapi-call-abc123"
    assert len(conv.messages) == 3
    assert conv.messages[0].role == MessageRole.CUSTOMER
    assert conv.messages[1].role == MessageRole.AGENT
    assert conv.messages[2].role == MessageRole.CUSTOMER
    assert conv.metadata["ended_reason"] == "customer-ended-call"


def test_vapi_extracts_tool_call_results_as_trusted_records():
    adapter = VapiAdapter()
    payload = {
        "message": {
            "call": {"id": "vapi-call-tool-001"},
            "messages": [
                {"role": "assistant", "message": "Processing your refund now."},
                {
                    "role": "tool_call_result",
                    "toolName": "refund",
                    "result": {"status": "success", "amount": 25.0},
                    "message": "Refund tool result",
                },
            ],
        }
    }

    conv = adapter.parse_conversation_webhook(payload)

    # Tool call result should be recorded as trusted action record
    assert len(conv.trusted_action_records) == 1
    assert conv.trusted_action_records[0]["action_type"] == "refund"
    assert conv.trusted_action_records[0]["status"] == "completed"


def test_vapi_handles_empty_transcript_gracefully():
    adapter = VapiAdapter()
    payload = {"message": {"call": {"id": "vapi-call-empty"}, "messages": []}}
    conv = adapter.parse_conversation_webhook(payload)
    assert conv.id == "vapi-call-empty"
    assert len(conv.messages) == 0


def test_vapi_assigns_scenario_id():
    adapter = VapiAdapter()
    payload = {"message": {"call": {"id": "vapi-001"}, "messages": []}}
    conv = adapter.parse_conversation_webhook(payload, scenario_id="scen_99")
    assert conv.scenario_id == "scen_99"


def test_vapi_unsupported_signature_verification():
    adapter = VapiAdapter()
    # Vapi doesn't use HMAC; uses token equality
    assert adapter.verify_webhook_signature(b"{}", "my-token", "my-token") is True
    assert adapter.verify_webhook_signature(b"{}", "wrong-token", "my-token") is False
