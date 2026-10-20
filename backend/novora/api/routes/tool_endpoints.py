import os
from typing import Any, Dict, Literal, Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from novora.api.auth import UserOrm, get_current_user
from novora.core.execution_models import HttpToolEndpointConfig, HttpToolEvaluationResult
from novora.execution.http_tool import evaluate_http_tool_endpoint
from novora.persistence.secrets import SecretManager

router = APIRouter(prefix="/api/v1/tool-endpoints", tags=["Developer Tool Endpoints"])


class ToolEndpointRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    provider: Literal["vapi", "retell"]
    tool_name: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_-]+$")
    endpoint_url: str = Field(min_length=1, max_length=2048)
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    timeout_ms: int = Field(default=3000, ge=100, le=10000)
    bearer_token: Optional[str] = Field(default=None, max_length=4096)


class ToolEndpointTestRequest(BaseModel):
    arguments: Dict[str, Any] = Field(default_factory=dict)
    agent_id: str = Field(default="novora-sandbox-agent", max_length=255)
    allow_writes: bool = False


def _validate_endpoint_request(req: ToolEndpointRequest) -> None:
    parsed = urlsplit(req.endpoint_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Endpoint URL must be HTTP(S), with no embedded credentials, query, or fragment.",
        )
    if req.provider == "vapi" and req.method != "POST":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Vapi tool-call webhook endpoints must use POST.",
        )
    if parsed.scheme != "https" and os.getenv("NOVORA_ALLOW_PRIVATE_TOOL_ENDPOINTS", "").lower() != "true":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Tool endpoints must use HTTPS; set NOVORA_ALLOW_PRIVATE_TOOL_ENDPOINTS=true for local development.",
        )


def _public_config(
    req: ToolEndpointRequest,
    endpoint_id: Optional[str] = None,
    existing: Optional[HttpToolEndpointConfig] = None,
) -> HttpToolEndpointConfig:
    values: Dict[str, Any] = {
        "name": req.name.strip(),
        "provider": req.provider,
        "tool_name": req.tool_name,
        "endpoint_url": req.endpoint_url.strip(),
        "method": req.method,
        "timeout_ms": req.timeout_ms,
        "api_key_masked": (
            SecretManager.mask_secret(req.bearer_token)
            if req.bearer_token
            else existing.api_key_masked if existing else ""
        ),
        "has_auth": bool(req.bearer_token) or bool(existing and existing.has_auth),
    }
    if endpoint_id or existing:
        values["id"] = endpoint_id or existing.id
    if existing:
        values["created_at"] = existing.created_at
    return HttpToolEndpointConfig(**values)


@router.post("", response_model=HttpToolEndpointConfig, status_code=status.HTTP_201_CREATED)
def create_tool_endpoint(
    req: ToolEndpointRequest,
    request: Request,
    current_user: UserOrm = Depends(get_current_user),
) -> HttpToolEndpointConfig:
    _validate_endpoint_request(req)
    config = _public_config(req)
    request.app.state.tool_endpoint_repository.save(
        current_user.id,
        config,
        req.bearer_token,
    )
    return config


@router.get("", response_model=list[HttpToolEndpointConfig])
def list_tool_endpoints(
    request: Request,
    current_user: UserOrm = Depends(get_current_user),
) -> list[HttpToolEndpointConfig]:
    return request.app.state.tool_endpoint_repository.list_all(current_user.id)


@router.put("/{endpoint_id}", response_model=HttpToolEndpointConfig)
def update_tool_endpoint(
    endpoint_id: str,
    req: ToolEndpointRequest,
    request: Request,
    current_user: UserOrm = Depends(get_current_user),
) -> HttpToolEndpointConfig:
    _validate_endpoint_request(req)
    stored = request.app.state.tool_endpoint_repository.get(current_user.id, endpoint_id)
    if not stored:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool endpoint not found.")
    existing, previous_token = stored
    config = _public_config(req, endpoint_id=endpoint_id, existing=existing)
    request.app.state.tool_endpoint_repository.save(
        current_user.id,
        config,
        req.bearer_token or previous_token,
    )
    return config


@router.delete("/{endpoint_id}")
def delete_tool_endpoint(
    endpoint_id: str,
    request: Request,
    current_user: UserOrm = Depends(get_current_user),
) -> Dict[str, str]:
    deleted = request.app.state.tool_endpoint_repository.delete(current_user.id, endpoint_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool endpoint not found.")
    return {"status": "deleted"}


@router.post("/{endpoint_id}/evaluations", response_model=HttpToolEvaluationResult)
def evaluate_tool_endpoint(
    endpoint_id: str,
    req: ToolEndpointTestRequest,
    request: Request,
    current_user: UserOrm = Depends(get_current_user),
) -> HttpToolEvaluationResult:
    stored = request.app.state.tool_endpoint_repository.get(current_user.id, endpoint_id)
    if not stored:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool endpoint not found.")
    config, bearer_token = stored
    result = evaluate_http_tool_endpoint(
        config=config,
        arguments=req.arguments,
        agent_id=req.agent_id,
        bearer_token=bearer_token,
        allow_writes=req.allow_writes,
    )
    request.app.state.tool_endpoint_repository.save_result(current_user.id, result)
    return result


@router.get("/{endpoint_id}/evaluations", response_model=list[HttpToolEvaluationResult])
def list_tool_endpoint_evaluations(
    endpoint_id: str,
    request: Request,
    current_user: UserOrm = Depends(get_current_user),
) -> list[HttpToolEvaluationResult]:
    if not request.app.state.tool_endpoint_repository.get(current_user.id, endpoint_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool endpoint not found.")
    return request.app.state.tool_endpoint_repository.list_results(current_user.id, endpoint_id)
