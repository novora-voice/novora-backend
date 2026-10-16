from typing import List
from fastapi import APIRouter, HTTPException, status
from novora.providers.capabilities import (
    PROVIDER_MANIFESTS,
    ProviderManifest,
    get_provider_manifest,
)

router = APIRouter(prefix="/api/v1/providers", tags=["Providers"])


@router.get("", response_model=List[ProviderManifest])
def list_providers() -> List[ProviderManifest]:
    """List all supported voice-agent and telephony providers with capabilities and group metadata."""
    return list(PROVIDER_MANIFESTS.values())


@router.get("/{provider_name}", response_model=ProviderManifest)
def get_provider_detail(provider_name: str) -> ProviderManifest:
    """Retrieve capabilities and supported execution methods for a specific provider."""
    manifest = get_provider_manifest(provider_name)
    if manifest.category == "custom":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_name}' is not supported.",
        )
    return manifest


@router.get("/{provider_name}/capabilities", response_model=ProviderManifest)
def get_capabilities(provider_name: str) -> ProviderManifest:
    """Retrieve capabilities for a specific provider (legacy compat)."""
    manifest = get_provider_manifest(provider_name)
    if manifest.category == "custom":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_name}' is not supported.",
        )
    return manifest
