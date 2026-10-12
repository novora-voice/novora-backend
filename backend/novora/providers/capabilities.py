from enum import Enum
from typing import Dict, Set
from pydantic import BaseModel, Field
from novora.core.exceptions import UnsupportedOperationError

class ProviderCapability(str, Enum):
    POST_CALL_TRANSCRIPT_WEBHOOK = "post_call_transcript_webhook"
    LIVE_AUDIO_STREAM = "live_audio_stream"
    TELEPHONY_STATUS_CALLBACK = "telephony_status_callback"
    RECORDING_CALLBACK = "recording_callback"
    TOOL_EXECUTION_LOGS = "tool_execution_logs"
    SIGNATURE_VERIFICATION = "signature_verification"
    SPEAKER_DIARIZATION = "speaker_diarization"

class ProviderManifest(BaseModel):
    provider_name: str
    category: str  # "voice_agent", "telephony", "transcription"
    supported_capabilities: Set[ProviderCapability] = Field(default_factory=set)

    def supports(self, capability: ProviderCapability) -> bool:
        return capability in self.supported_capabilities

    def assert_supports(self, capability: ProviderCapability) -> None:
        if not self.supports(capability):
            raise UnsupportedOperationError(
                provider=self.provider_name,
                capability=capability.value,
            )

PROVIDER_MANIFESTS: Dict[str, ProviderManifest] = {
    "elevenlabs": ProviderManifest(
        provider_name="elevenlabs",
        category="voice_agent",
        supported_capabilities={
            ProviderCapability.POST_CALL_TRANSCRIPT_WEBHOOK,
            ProviderCapability.SIGNATURE_VERIFICATION,
        },
    ),
    "vapi": ProviderManifest(
        provider_name="vapi",
        category="voice_agent",
        supported_capabilities={
            ProviderCapability.POST_CALL_TRANSCRIPT_WEBHOOK,
            ProviderCapability.TOOL_EXECUTION_LOGS,
        },
    ),
    "retell": ProviderManifest(
        provider_name="retell",
        category="voice_agent",
        supported_capabilities={
            ProviderCapability.POST_CALL_TRANSCRIPT_WEBHOOK,
        },
    ),
    "twilio": ProviderManifest(
        provider_name="twilio",
        category="telephony",
        supported_capabilities={
            ProviderCapability.TELEPHONY_STATUS_CALLBACK,
            ProviderCapability.RECORDING_CALLBACK,
            ProviderCapability.SIGNATURE_VERIFICATION,
        },
    ),
    "assemblyai": ProviderManifest(
        provider_name="assemblyai",
        category="transcription",
        supported_capabilities={
            ProviderCapability.POST_CALL_TRANSCRIPT_WEBHOOK,
            ProviderCapability.SPEAKER_DIARIZATION,
        },
    ),
}

def get_provider_manifest(provider_name: str) -> ProviderManifest:
    name_key = provider_name.lower().strip()
    manifest = PROVIDER_MANIFESTS.get(name_key)
    if not manifest:
        return ProviderManifest(
            provider_name=provider_name,
            category="custom",
            supported_capabilities=set(),
        )
    return manifest
