from novora.adapters.providers.assemblyai import AssemblyAIAdapter
from novora.core.enums import ConversationSource, MessageRole

def test_assemblyai_utterances_normalization():
    adapter = AssemblyAIAdapter()
    payload = {
        "id": "aai_transcript_5544",
        "audio_duration": 60.5,
        "confidence": 0.98,
        "utterances": [
            {
                "speaker": "A",
                "text": "Thank you for calling customer service, how can I help you?",
                "start": 500,
                "end": 3500,
                "confidence": 0.99,
            },
            {
                "speaker": "B",
                "text": "Hello, I want to check on my delayed refund.",
                "start": 3800,
                "end": 6200,
                "confidence": 0.97,
            },
        ],
    }

    conv = adapter.parse_transcription_result(payload, scenario_id="scen_support")

    assert conv.id == "conv_aai_aai_transcript_5544"
    assert conv.source == ConversationSource.ASSEMBLYAI_WEBHOOK
    assert conv.scenario_id == "scen_support"
    assert len(conv.messages) == 2

    # Speaker A greeted, so detected as Agent
    assert conv.messages[0].role == MessageRole.AGENT
    assert conv.messages[0].content == "Thank you for calling customer service, how can I help you?"
    assert conv.messages[0].metadata["confidence"] == 0.99

    # Speaker B is Customer
    assert conv.messages[1].role == MessageRole.CUSTOMER
    assert conv.messages[1].content == "Hello, I want to check on my delayed refund."
