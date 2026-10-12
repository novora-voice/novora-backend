import re
from typing import Any, Dict, List, Optional
from novora.core.enums import ConversationSource, MessageRole
from novora.core.models import Conversation, ConversationMessage
from novora.providers.base import TranscriptionProvider

AGENT_GREETING_PATTERN = re.compile(
    r"(?:thank you for calling|thanks for calling|how can i help|my name is|how may i assist)",
    re.IGNORECASE,
)

class AssemblyAIAdapter(TranscriptionProvider):
    """Adapter for AssemblyAI speech-to-text transcription results and webhooks."""

    def parse_transcription_result(
        self,
        payload: Dict[str, Any],
        scenario_id: Optional[str] = None,
        agent_speaker: Optional[str] = None,
    ) -> Conversation:
        """Parses AssemblyAI transcript payload with diarized utterances into a normalized Conversation."""
        transcript_id = str(payload.get("id", payload.get("transcript_id", "transcript_aai")))
        raw_utterances = payload.get("utterances", [])

        # Auto-detect which speaker label corresponds to the agent if not provided
        detected_agent_speaker = agent_speaker
        if not detected_agent_speaker and raw_utterances:
            first_turn = raw_utterances[0]
            first_text = str(first_turn.get("text", ""))
            first_spk = str(first_turn.get("speaker", "A"))
            if AGENT_GREETING_PATTERN.search(first_text):
                detected_agent_speaker = first_spk
            else:
                # If caller spoke first, assume second speaker is agent
                speakers = list(dict.fromkeys(str(u.get("speaker", "")) for u in raw_utterances))
                if len(speakers) > 1:
                    detected_agent_speaker = speakers[1]
                else:
                    detected_agent_speaker = "B"

        messages: List[ConversationMessage] = []

        if raw_utterances:
            for idx, utt in enumerate(raw_utterances):
                spk = str(utt.get("speaker", "A"))
                role = MessageRole.AGENT if spk == detected_agent_speaker else MessageRole.CUSTOMER
                content = str(utt.get("text", "")).strip()

                messages.append(
                    ConversationMessage(
                        id=f"msg_aai_{idx:03d}",
                        role=role,
                        content=content,
                        sequence=idx,
                        metadata={
                            "speaker_label": spk,
                            "start_ms": utt.get("start"),
                            "end_ms": utt.get("end"),
                            "confidence": utt.get("confidence"),
                        },
                    )
                )
        else:
            # Fallback if no utterances diarization is present: treat entire text as single customer utterance
            full_text = str(payload.get("text", "")).strip()
            if full_text:
                messages.append(
                    ConversationMessage(
                        id="msg_aai_000",
                        role=MessageRole.CUSTOMER,
                        content=full_text,
                        sequence=0,
                    )
                )

        metadata = {
            "assemblyai_transcript_id": transcript_id,
            "audio_duration": payload.get("audio_duration"),
            "confidence": payload.get("confidence"),
            "audio_url": payload.get("audio_url"),
            "agent_speaker_detected": detected_agent_speaker,
        }

        return Conversation(
            id=f"conv_aai_{transcript_id}",
            scenario_id=scenario_id,
            source=ConversationSource.ASSEMBLYAI_WEBHOOK,
            messages=messages,
            metadata=metadata,
        )
