from novora.adapters.providers.transcript_importer import TranscriptImporter
from novora.core.enums import ConversationSource, MessageRole

def test_transcript_import_from_dialogue_text():
    text = (
        "Customer: Hi, I am inquiring about order #9821.\n"
        "Agent: Hello! I'd be glad to look that up for you.\n"
        "Customer: My email is alex@novora.test.\n"
        "Agent: Thank you. I have located your refund status."
    )
    conv = TranscriptImporter.from_text(text=text, scenario_id="scen_100")

    assert conv.source == ConversationSource.TRANSCRIPT_UPLOAD
    assert conv.scenario_id == "scen_100"
    assert len(conv.messages) == 4

    assert conv.messages[0].role == MessageRole.CUSTOMER
    assert conv.messages[0].sequence == 0
    assert "order #9821" in conv.messages[0].content

    assert conv.messages[1].role == MessageRole.AGENT
    assert conv.messages[1].sequence == 1

    assert conv.messages[2].role == MessageRole.CUSTOMER
    assert conv.messages[3].role == MessageRole.AGENT

def test_transcript_import_from_structured_records():
    records = [
        {"role": "user", "text": "Can I return this item?", "id": "m_01"},
        {"role": "agent", "text": "Yes, our policy allows returns within 30 days.", "id": "m_02"},
    ]
    conv = TranscriptImporter.from_records(records=records)

    assert len(conv.messages) == 2
    assert conv.messages[0].role == MessageRole.CUSTOMER
    assert conv.messages[0].id == "m_01"
    assert conv.messages[1].role == MessageRole.AGENT
    assert conv.messages[1].id == "m_02"
