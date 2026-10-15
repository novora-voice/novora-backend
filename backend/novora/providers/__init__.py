from novora.providers.base import (
    ExecutableVoiceProvider,
    TelephonyProvider,
    TranscriptionProvider,
    VoiceAgentProvider,
)
from novora.providers.registry import ProviderRegistry, global_provider_registry
from novora.providers.elevenlabs.adapter import ElevenLabsExecutionAdapter
from novora.providers.elevenlabs.client import ElevenLabsGhostCaller
from novora.providers.assemblyai.adapter import AssemblyAIExecutionAdapter
from novora.providers.assemblyai.client import AssemblyAIVoiceAgentClient
from novora.providers.vapi.adapter import VapiExecutionAdapter
from novora.providers.vapi.client import VapiTestClient
from novora.providers.retell.adapter import RetellExecutionAdapter
from novora.providers.retell.client import RetellTestClient

# Register default execution adapters in global registry
global_provider_registry.register("elevenlabs", ElevenLabsExecutionAdapter())
global_provider_registry.register("assemblyai", AssemblyAIExecutionAdapter())
global_provider_registry.register("vapi", VapiExecutionAdapter())
global_provider_registry.register("retell", RetellExecutionAdapter())

__all__ = [
    "VoiceAgentProvider",
    "TelephonyProvider",
    "TranscriptionProvider",
    "ExecutableVoiceProvider",
    "ProviderRegistry",
    "global_provider_registry",
    "ElevenLabsExecutionAdapter",
    "ElevenLabsGhostCaller",
    "AssemblyAIExecutionAdapter",
    "AssemblyAIVoiceAgentClient",
    "VapiExecutionAdapter",
    "VapiTestClient",
    "RetellExecutionAdapter",
    "RetellTestClient",
]
