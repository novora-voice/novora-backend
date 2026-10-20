from datetime import datetime, timezone

from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from novora.adapters.database import (
    DatabaseSessionManager,
    SQLAlchemyHttpToolEndpointRepository,
)
from novora.adapters.db_models import DBApplicationRecord
from novora.api.main import create_app
from novora.api.auth import UserOrm, get_current_user
from novora.core.execution_models import (
    HttpToolEndpointConfig,
    HttpToolEvaluationResult,
)
from novora.execution import http_tool


def _config(provider="vapi", method="POST"):
    return HttpToolEndpointConfig(
        id=f"endpoint_{provider}",
        name="Support CRM",
        provider=provider,
        tool_name="create_support_ticket",
        endpoint_url="https://crm.example.com/api/tickets",
        method=method,
        has_auth=True,
    )


def test_http_tool_endpoint_repository_encrypts_credentials_and_scopes_records():
    manager = DatabaseSessionManager("sqlite:///:memory:")
    repo = SQLAlchemyHttpToolEndpointRepository(manager)
    config = _config()
    repo.save("owner-a", config, "sensitive-bearer-token")

    loaded = repo.get("owner-a", config.id)
    assert loaded is not None
    saved_config, saved_token = loaded
    assert saved_config.endpoint_url == config.endpoint_url
    assert saved_token == "sensitive-bearer-token"
    assert repo.get("owner-b", config.id) is None
    assert repo.list_all("owner-b") == []

    with manager.get_session() as session:
        row = session.query(DBApplicationRecord).filter(
            DBApplicationRecord.record_type == "http_tool_endpoint"
        ).one()
        assert "sensitive-bearer-token" not in row.payload


def test_vapi_contract_replay_checks_matching_tool_call_result(monkeypatch):
    monkeypatch.setattr(http_tool, "_validate_target", lambda _: None)

    def fake_send(method, url, payload, bearer_token, timeout_ms):
        assert method == "POST"
        assert payload["message"]["toolCallList"][0]["function"]["name"] == "create_support_ticket"
        call_id = payload["message"]["toolCallList"][0]["id"]
        return 200, {"results": [{
            "toolCallId": call_id,
            "result": "{\"ticket_id\":\"T-123\",\"api_key\":\"private\"}",
        }]}, None

    monkeypatch.setattr(http_tool, "_send", fake_send)
    result = http_tool.evaluate_http_tool_endpoint(
        _config(),
        {"customer_email": "sam@example.com", "issue_description": "Broken display", "api_key": "private"},
        "assistant-1",
        "server-only-token",
        allow_writes=True,
    )

    assert result.success
    assert result.performance_pass
    assert result.status_code == 200
    assert result.request_payload["message"]["type"] == "tool-calls"
    assert result.response_payload["results"][0]["result"] == "{\"ticket_id\":\"T-123\",\"api_key\":\"[REDACTED]\"}"
    arguments = result.request_payload["message"]["toolCallList"][0]["function"]["arguments"]
    assert arguments["api_key"] == "[REDACTED]"


def test_retell_contract_replay_uses_custom_function_http_body(monkeypatch):
    monkeypatch.setattr(http_tool, "_validate_target", lambda _: None)
    captured = {}

    def fake_send(method, url, payload, bearer_token, timeout_ms):
        captured.update(method=method, url=url, payload=payload, token=bearer_token)
        return 201, {"ticket_id": "T-456", "status": "open"}, None

    monkeypatch.setattr(http_tool, "_send", fake_send)
    result = http_tool.evaluate_http_tool_endpoint(
        _config("retell"),
        {"customer_email": "sam@example.com"},
        "retell-agent-1",
        "server-only-token",
        allow_writes=True,
    )

    assert result.success
    assert captured["method"] == "POST"
    assert captured["payload"]["name"] == "create_support_ticket"
    assert captured["payload"]["call"]["agent_id"] == "retell-agent-1"
    assert captured["payload"]["args"] == {"customer_email": "sam@example.com"}
    assert result.response_payload == {"ticket_id": "T-456", "status": "open"}


def test_write_tool_calls_are_blocked_until_explicit_run_confirmation(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("an unconfirmed write must not reach the user's endpoint")

    monkeypatch.setattr(http_tool, "_validate_target", fail_if_called)
    monkeypatch.setattr(http_tool, "_send", fail_if_called)
    result = http_tool.evaluate_http_tool_endpoint(
        _config(),
        {"customer_email": "sam@example.com"},
        "assistant-1",
        None,
        allow_writes=False,
    )

    assert not result.success
    assert "Confirm writes" in result.error
    assert result.status_code is None


def test_private_tool_endpoint_blocked_by_default(monkeypatch):
    monkeypatch.delenv("NOVORA_ALLOW_PRIVATE_TOOL_ENDPOINTS", raising=False)
    monkeypatch.setattr(
        http_tool.socket,
        "getaddrinfo",
        lambda *args: [(None, None, None, None, ("127.0.0.1", 443))],
    )
    try:
        http_tool._validate_target("https://internal.example.com/tool")
    except ValueError as exc:
        assert "public IP" in str(exc)
    else:
        raise AssertionError("private-address DNS results must be rejected")


def test_tool_endpoint_api_requires_auth_and_saves_owner_scoped_evaluation(monkeypatch):
    app = create_app()

    def authenticated_test_user(request: Request) -> UserOrm:
        authorization = request.headers.get("Authorization")
        if not authorization:
            raise HTTPException(status_code=401, detail="Authentication required.")
        return UserOrm(id=authorization.removeprefix("Bearer "))

    app.dependency_overrides[get_current_user] = authenticated_test_user
    client = TestClient(app)
    assert client.get("/api/v1/tool-endpoints").status_code == 401

    owner_headers = {"Authorization": "Bearer owner-a"}
    other_headers = {"Authorization": "Bearer owner-b"}
    create = client.post(
        "/api/v1/tool-endpoints",
        headers=owner_headers,
        json={
            "name": "Support API",
            "provider": "vapi",
            "tool_name": "create_support_ticket",
            "endpoint_url": "https://crm.example.com/api/tickets",
            "method": "POST",
            "bearer_token": "private-token-value",
        },
    )
    assert create.status_code == 201
    endpoint = create.json()
    assert endpoint["has_auth"] is True
    assert "private-token-value" not in create.text

    assert client.get("/api/v1/tool-endpoints", headers=other_headers).json() == []
    assert client.post(
        f"/api/v1/tool-endpoints/{endpoint['id']}/evaluations",
        headers=other_headers,
        json={"arguments": {"email": "sam@example.com"}, "allow_writes": True},
    ).status_code == 404

    def fake_evaluate(config, arguments, agent_id, bearer_token, allow_writes):
        assert bearer_token == "private-token-value"
        assert allow_writes is True
        return HttpToolEvaluationResult(
            id="tool_eval_test",
            endpoint_id=config.id,
            endpoint_name=config.name,
            provider=config.provider,
            tool_name=config.tool_name,
            method="POST",
            endpoint_url="https://crm.example.com/api/tickets",
            request_payload={"message": {"type": "tool-calls"}},
            status_code=200,
            response_payload={"ticket_id": "T-789"},
            latency_ms=42,
            success=True,
            performance_pass=True,
            created_at=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(
        "novora.api.routes.tool_endpoints.evaluate_http_tool_endpoint",
        fake_evaluate,
    )
    evaluated = client.post(
        f"/api/v1/tool-endpoints/{endpoint['id']}/evaluations",
        headers=owner_headers,
        json={"arguments": {"customer_email": "sam@example.com"}, "allow_writes": True},
    )
    assert evaluated.status_code == 200
    assert evaluated.json()["response_payload"]["ticket_id"] == "T-789"
    history = client.get(
        f"/api/v1/tool-endpoints/{endpoint['id']}/evaluations",
        headers=owner_headers,
    )
    assert history.status_code == 200
    assert history.json()[0]["id"] == "tool_eval_test"


def test_vapi_endpoint_rejects_non_post_method():
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: UserOrm(id="owner-method")
    client = TestClient(app)
    response = client.post(
        "/api/v1/tool-endpoints",
        json={
            "name": "Bad Vapi Endpoint",
            "provider": "vapi",
            "tool_name": "lookup",
            "endpoint_url": "https://crm.example.com/api/tickets",
            "method": "GET",
        },
    )
    assert response.status_code == 422
