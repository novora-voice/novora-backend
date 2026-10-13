import pytest
from novora.adapters.providers.retell import RetellAdapter
from novora.adapters.providers.vapi import VapiAdapter
from novora.core.enums import ConversationSource, MessageRole
from novora.core.exceptions import UnsupportedOperationError
from novora.providers.capabilities import (
    ProviderCapability,
    get_provider_manifest,
)

def test_provider_capability_manifest_queries():
    el_manifest = get_provider_manifest("elevenlabs")
    assert el_manifest.supports(ProviderCapability.POST_CALL_TRANSCRIPT_WEBHOOK) is True
    assert el_manifest.supports(ProviderCapability.TELEPHONY_STATUS_CALLBACK) is False

    # Calling assert_supports on unsupported capability raises UnsupportedOperationError
    with pytest.raises(UnsupportedOperationError, match="does not support capability"):
        el_manifest.assert_supports(ProviderCapability.TELEPHONY_STATUS_CALLBACK)

def test_vapi_adapter_normalization():
    adapter = VapiAdapter()
    payload = {
        "message": {
            "call": {"id": "call_vapi_9821"},
            "messages": [
                {"role": "user", "message": "Can you check my refund?"},
                {"role": "assistant", "message": "Checking that now."},
                {
                    "role": "tool_call_result",
                    "toolName": "refund_tool",
                    "result": {"status": "success", "amount": 25.0},
                },
            ],
            "endedReason": "customer-ended-call",
        }
    }

    conv = adapter.parse_conversation_webhook(payload, scenario_id="scen_1")
    assert conv.id == "call_vapi_9821"
    assert conv.source == ConversationSource.VAPI_WEBHOOK
    assert len(conv.messages) == 2
    assert conv.messages[0].role == MessageRole.CUSTOMER
    assert conv.messages[1].role == MessageRole.AGENT

    # Tool call was captured in trusted_action_records
    assert len(conv.trusted_action_records) == 1
    assert conv.trusted_action_records[0]["action_type"] == "refund_tool"

def test_retell_adapter_normalization():
    adapter = RetellAdapter()
    payload = {
        "call_id": "call_retell_4411",
        "agent_id": "agent_retell_01",
        "transcript_object": [
            {"role": "agent", "content": "Hello, thank you for calling."},
            {"role": "user", "content": "Hi, I have a question about my invoice."},
        ],
    }

    conv = adapter.parse_conversation_webhook(payload)
    assert conv.id == "call_retell_4411"
    assert conv.source == ConversationSource.RETELL_WEBHOOK
    assert len(conv.messages) == 2
    assert conv.messages[0].role == MessageRole.AGENT
    assert conv.messages[1].role == MessageRole.CUSTOMER
