from enum import Enum
from typing import Dict, Optional, Set
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
    PROGRAMMATIC_GHOST_CALLER = "programmatic_ghost_caller"
    WEBSOCKET_AGENT_SESSION = "websocket_agent_session"
    TOOL_CALLING_EXECUTION = "tool_calling_execution"
    AUDIO_INPUT_STREAM = "audio_input_stream"
    AGENT_DISCOVERY = "agent_discovery"
    WEBHOOK_CONTRACT_TEST = "webhook_contract_test"
    PAYLOAD_GENERATION = "payload_generation"


class ProviderGroup(str, Enum):
    VOICE_PROVIDER = "voice_provider"        # ElevenLabs, AssemblyAI - ghost caller capable
    INFRASTRUCTURE = "infrastructure"        # Vapi, Retell - pipeline + webhook testing
    TELEPHONY = "telephony"                  # Twilio
    TRANSCRIPTION = "transcription"          # AssemblyAI (also voice_provider capable)


class ProviderManifest(BaseModel):
    provider_name: str
    display_name: str = ""
    category: str  # "voice_agent", "telephony", "transcription"
    provider_group: str = ProviderGroup.INFRASTRUCTURE.value
    supported_capabilities: Set[ProviderCapability] = Field(default_factory=set)
    supports_ghost_caller: bool = False
    supports_webhook_contract_test: bool = False
    requires_audio_input: bool = False
    supports_payload_generation: bool = False
    is_live_verified: bool = False
    documentation_url: Optional[str] = None

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
        display_name="ElevenLabs",
        category="voice_agent",
        provider_group=ProviderGroup.VOICE_PROVIDER.value,
        supported_capabilities={
            ProviderCapability.POST_CALL_TRANSCRIPT_WEBHOOK,
            ProviderCapability.SIGNATURE_VERIFICATION,
            ProviderCapability.PROGRAMMATIC_GHOST_CALLER,
            ProviderCapability.WEBSOCKET_AGENT_SESSION,
            ProviderCapability.TOOL_CALLING_EXECUTION,
            ProviderCapability.AGENT_DISCOVERY,
        },
        supports_ghost_caller=True,
        supports_webhook_contract_test=True,
        requires_audio_input=False,
        is_live_verified=False,
        documentation_url="https://elevenlabs.io/docs/eleven-agents/api-reference",
    ),
    "assemblyai": ProviderManifest(
        provider_name="assemblyai",
        display_name="AssemblyAI",
        category="voice_agent",
        provider_group=ProviderGroup.VOICE_PROVIDER.value,
        supported_capabilities={
            ProviderCapability.POST_CALL_TRANSCRIPT_WEBHOOK,
            ProviderCapability.SPEAKER_DIARIZATION,
            ProviderCapability.WEBSOCKET_AGENT_SESSION,
            ProviderCapability.AUDIO_INPUT_STREAM,
            ProviderCapability.TOOL_CALLING_EXECUTION,
        },
        supports_ghost_caller=True,
        supports_webhook_contract_test=True,
        requires_audio_input=True,
        is_live_verified=False,
        documentation_url="https://www.assemblyai.com/docs/voice-agents/voice-agent-api",
    ),
    "vapi": ProviderManifest(
        provider_name="vapi",
        display_name="Vapi",
        category="voice_agent",
        provider_group=ProviderGroup.INFRASTRUCTURE.value,
        supported_capabilities={
            ProviderCapability.POST_CALL_TRANSCRIPT_WEBHOOK,
            ProviderCapability.TOOL_EXECUTION_LOGS,
            ProviderCapability.PROGRAMMATIC_GHOST_CALLER,
            ProviderCapability.AGENT_DISCOVERY,
            ProviderCapability.WEBHOOK_CONTRACT_TEST,
            ProviderCapability.PAYLOAD_GENERATION,
        },
        supports_ghost_caller=False,
        supports_webhook_contract_test=True,
        supports_payload_generation=True,
        is_live_verified=False,
        documentation_url="https://docs.vapi.ai/",
    ),
    "retell": ProviderManifest(
        provider_name="retell",
        display_name="Retell AI",
        category="voice_agent",
        provider_group=ProviderGroup.INFRASTRUCTURE.value,
        supported_capabilities={
            ProviderCapability.POST_CALL_TRANSCRIPT_WEBHOOK,
            ProviderCapability.PROGRAMMATIC_GHOST_CALLER,
            ProviderCapability.AGENT_DISCOVERY,
            ProviderCapability.WEBHOOK_CONTRACT_TEST,
            ProviderCapability.PAYLOAD_GENERATION,
        },
        supports_ghost_caller=False,
        supports_webhook_contract_test=True,
        supports_payload_generation=True,
        is_live_verified=False,
        documentation_url="https://docs.retellai.com/",
    ),
    "twilio": ProviderManifest(
        provider_name="twilio",
        display_name="Twilio",
        category="telephony",
        provider_group=ProviderGroup.TELEPHONY.value,
        supported_capabilities={
            ProviderCapability.TELEPHONY_STATUS_CALLBACK,
            ProviderCapability.RECORDING_CALLBACK,
            ProviderCapability.SIGNATURE_VERIFICATION,
        },
        supports_ghost_caller=False,
        supports_webhook_contract_test=True,
        is_live_verified=False,
    ),
}


def get_provider_manifest(provider_name: str) -> ProviderManifest:
    name_key = provider_name.lower().strip()
    manifest = PROVIDER_MANIFESTS.get(name_key)
    if not manifest:
        return ProviderManifest(
            provider_name=provider_name,
            display_name=provider_name.title(),
            category="custom",
            provider_group=ProviderGroup.INFRASTRUCTURE.value,
            supported_capabilities=set(),
        )
    return manifest
