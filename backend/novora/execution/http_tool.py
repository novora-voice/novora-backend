import ipaddress
import json
import os
import socket
import time
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

from novora.core.execution_models import (
    HttpToolEndpointConfig,
    HttpToolEvaluationResult,
)

MAX_RESPONSE_BYTES = 1_000_000
PERFORMANCE_LIMIT_MS = 3000
SENSITIVE_RESPONSE_KEYS = (
    "password",
    "secret",
    "token",
    "api_key",
    "authorization",
    "credential",
)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def _validate_target(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("Endpoint URL must be an HTTP(S) URL without credentials, query, or fragment.")

    allow_private = os.getenv("NOVORA_ALLOW_PRIVATE_TOOL_ENDPOINTS", "").lower() == "true"
    if parsed.scheme != "https" and not allow_private:
        raise ValueError("Tool endpoints must use HTTPS; set NOVORA_ALLOW_PRIVATE_TOOL_ENDPOINTS=true for local development.")

    try:
        addresses = {
            ipaddress.ip_address(info[4][0])
            for info in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
        }
    except OSError as exc:
        raise ValueError("Tool endpoint hostname could not be resolved.") from exc
    if not addresses:
        raise ValueError("Tool endpoint hostname did not resolve to an IP address.")
    if parsed.scheme == "http" and any(address.is_global for address in addresses):
        raise ValueError("Unencrypted HTTP is allowed only for private-network development endpoints.")
    if not allow_private and any(not address.is_global for address in addresses):
        raise ValueError("Tool endpoint must resolve only to public IP addresses.")


def _redact_response(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if any(part in key.lower() for part in SENSITIVE_RESPONSE_KEYS)
            else _redact_response(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_response(item) for item in value]
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return value
        if isinstance(decoded, (dict, list)):
            return json.dumps(_redact_response(decoded), separators=(",", ":"))
    return value


def _send(
    method: str,
    url: str,
    payload: Optional[Dict[str, Any]],
    bearer_token: Optional[str],
    timeout_ms: int,
) -> tuple[Optional[int], Any, Optional[str]]:
    headers = {"Accept": "application/json"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, headers=headers, method=method)
    opener = build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout_ms / 1000) as response:
            status_code = response.status
            content = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        status_code = exc.code
        content = exc.read(MAX_RESPONSE_BYTES + 1)
    except (TimeoutError, URLError, OSError) as exc:
        return None, None, f"Endpoint request failed: {type(exc).__name__}"

    if len(content) > MAX_RESPONSE_BYTES:
        return status_code, None, "Endpoint response exceeded the 1 MB limit."
    if not content:
        return status_code, None, None
    decoded = content.decode("utf-8", errors="replace")
    try:
        return status_code, json.loads(decoded), None
    except json.JSONDecodeError:
        return status_code, decoded, None


def _build_request(
    config: HttpToolEndpointConfig,
    arguments: Dict[str, Any],
    agent_id: str,
    call_id: str,
) -> tuple[str, Optional[Dict[str, Any]]]:
    if config.provider == "vapi":
        payload = {
            "message": {
                "type": "tool-calls",
                "toolCallList": [{
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": config.tool_name,
                        "arguments": arguments,
                    },
                }],
            },
        }
        return "POST", payload

    if config.method in {"GET", "DELETE"}:
        return config.method, None
    payload = {
        "name": config.tool_name,
        "call": {"call_id": call_id, "agent_id": agent_id},
        "args": arguments,
    }
    return config.method, payload


def _build_url(config: HttpToolEndpointConfig, method: str, arguments: Dict[str, Any]) -> str:
    parsed = urlsplit(config.endpoint_url)
    if config.provider == "retell" and method in {"GET", "DELETE"}:
        query = urlencode(arguments, doseq=True)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))
    return config.endpoint_url


def _valid_vapi_response(response: Any, call_id: str) -> bool:
    if not isinstance(response, dict) or not isinstance(response.get("results"), list):
        return False
    return any(
        isinstance(item, dict)
        and item.get("toolCallId") == call_id
        and isinstance(item.get("result"), str)
        for item in response["results"]
    )


def evaluate_http_tool_endpoint(
    config: HttpToolEndpointConfig,
    arguments: Dict[str, Any],
    agent_id: str,
    bearer_token: Optional[str],
    allow_writes: bool,
) -> HttpToolEvaluationResult:
    call_id = f"novora_{uuid4().hex}"
    method, payload = _build_request(config, arguments, agent_id, call_id)
    url = _build_url(config, method, arguments)
    safe_url = urlsplit(config.endpoint_url)
    display_url = urlunsplit((safe_url.scheme, safe_url.netloc, safe_url.path, "", ""))

    if method != "GET" and not allow_writes:
        return HttpToolEvaluationResult(
            endpoint_id=config.id,
            endpoint_name=config.name,
            provider=config.provider,
            tool_name=config.tool_name,
            method=method,
            endpoint_url=display_url,
            request_payload=_redact_response(payload or arguments),
            success=False,
            performance_pass=False,
            error="This endpoint uses a potentially mutating method. Confirm writes for this run to continue.",
        )

    start = time.perf_counter()
    status_code: Optional[int] = None
    response_payload: Any = None
    error: Optional[str] = None
    try:
        _validate_target(url)
        status_code, response_payload, error = _send(
            method,
            url,
            payload,
            bearer_token,
            config.timeout_ms,
        )
    except ValueError as exc:
        error = str(exc)
    latency_ms = round((time.perf_counter() - start) * 1000, 2)

    response_payload = _redact_response(response_payload)
    if status_code is not None and not 200 <= status_code < 300:
        error = f"Endpoint returned HTTP {status_code}."
    if config.provider == "vapi" and status_code is not None and 200 <= status_code < 300:
        if not _valid_vapi_response(response_payload, call_id):
            error = "Vapi endpoint response must include a results entry with the matching toolCallId and result."

    performance_pass = latency_ms <= PERFORMANCE_LIMIT_MS
    if not performance_pass and error is None:
        error = "Endpoint response exceeded the 3000 ms performance target."
    success = (
        status_code is not None
        and 200 <= status_code < 300
        and error is None
    )
    return HttpToolEvaluationResult(
        endpoint_id=config.id,
        endpoint_name=config.name,
        provider=config.provider,
        tool_name=config.tool_name,
        method=method,
        endpoint_url=display_url,
        request_payload=_redact_response(payload or arguments),
        status_code=status_code,
        response_payload=response_payload,
        latency_ms=latency_ms,
        success=success,
        performance_pass=performance_pass,
        error=error,
    )
