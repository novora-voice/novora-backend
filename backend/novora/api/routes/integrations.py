from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from novora.core.execution_models import (
    AgentConfig,
    IntegrationHealth,
    ProviderConfig,
)
from novora.persistence.repositories import InMemoryIntegrationRepository
from novora.persistence.secrets import SecretManager
from novora.providers.registry import global_provider_registry

router = APIRouter(tags=["Integrations & Agents"])
default_integration_repo = InMemoryIntegrationRepository()

class IntegrationCreateRequest(BaseModel):
    provider_name: str
    api_key: str
    base_url: Optional[str] = None
    timeout_seconds: int = 30
    safe_mode: bool = True

@router.post("/api/v1/integrations", response_model=ProviderConfig, status_code=status.HTTP_201_CREATED)
def create_integration(req: IntegrationCreateRequest) -> ProviderConfig:
    """Create or update a provider integration with masked secret storage."""
    masked = SecretManager.mask_secret(req.api_key)
    cfg = ProviderConfig(
        provider_name=req.provider_name.lower().strip(),
        api_key_masked=masked,
        base_url=req.base_url,
        timeout_seconds=req.timeout_seconds,
        safe_mode=req.safe_mode,
        metadata={"raw_key": req.api_key},  # kept in-memory for server-side testing
    )
    return default_integration_repo.save(cfg)

@router.get("/api/v1/integrations", response_model=List[ProviderConfig])
def list_integrations() -> List[ProviderConfig]:
    """List configured provider integrations with masked credentials."""
    return default_integration_repo.list_all()

@router.post("/api/v1/integrations/{integration_id}/test-connectivity", response_model=IntegrationHealth)
def test_connectivity(integration_id: str) -> IntegrationHealth:
    """Tests connectivity to a configured provider."""
    cfg = default_integration_repo.get(integration_id)
    if not cfg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Integration with id '{integration_id}' not found.",
        )
    adapter = global_provider_registry.get_adapter(cfg.provider_name)
    if not adapter:
        return IntegrationHealth(
            provider=cfg.provider_name,
            is_healthy=False,
            error=f"No adapter available for provider '{cfg.provider_name}'.",
        )
    raw_key = cfg.metadata.get("raw_key") or cfg.api_key_masked
    return adapter.check_connectivity({"api_key": raw_key})

@router.get("/api/v1/agents", response_model=List[AgentConfig])
def list_agents(
    provider: str = Query(..., description="Provider name: elevenlabs, vapi, retell, assemblyai"),
    agent_id: Optional[str] = Query(None, description="Optional agent ID to validate"),
) -> List[AgentConfig]:
    """Discover or validate configured agents for a provider."""
    adapter = global_provider_registry.get_adapter(provider)
    if not adapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider}' not supported for agent discovery.",
        )
    return adapter.list_or_validate_agents({"agent_id": agent_id}, agent_id=agent_id)
