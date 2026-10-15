from typing import Any, Dict, List, Optional
from novora.providers.capabilities import (
    PROVIDER_MANIFESTS,
    ProviderManifest,
    get_provider_manifest,
)
from novora.core.exceptions import UnsupportedOperationError

class ProviderRegistry:
    """Central registry for supported voice and telephony provider adapters."""

    def __init__(self) -> None:
        self._adapters: Dict[str, Any] = {}

    def register(self, provider_name: str, adapter: Any) -> None:
        self._adapters[provider_name.lower().strip()] = adapter

    def get_adapter(self, provider_name: str) -> Optional[Any]:
        return self._adapters.get(provider_name.lower().strip())

    def get_manifest(self, provider_name: str) -> ProviderManifest:
        return get_provider_manifest(provider_name)

    def list_manifests(self) -> List[ProviderManifest]:
        return list(PROVIDER_MANIFESTS.values())

    def assert_capability(self, provider_name: str, capability: Any) -> None:
        manifest = self.get_manifest(provider_name)
        manifest.assert_supports(capability)

# Singleton global registry instance
global_provider_registry = ProviderRegistry()
