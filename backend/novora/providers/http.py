import json
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ProviderRequestError(RuntimeError):
    pass


def request_bytes(
    method: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 30,
) -> bytes:
    request_headers = {"Accept": "application/octet-stream"}
    request_headers.update(headers or {})
    body = None
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            content = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ProviderRequestError(f"Provider API returned HTTP {exc.code}: {detail[:1000]}") from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise ProviderRequestError(f"Could not connect to provider API: {exc}") from exc
    if not content:
        raise ProviderRequestError("Provider API returned an empty audio response.")
    return content


def request_json_value(
    method: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 30,
) -> Any:
    request_headers = {"Accept": "application/json"}
    request_headers.update(headers or {})
    body = None
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            content = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ProviderRequestError(f"Provider API returned HTTP {exc.code}: {detail[:1000]}") from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise ProviderRequestError(f"Could not connect to provider API: {exc}") from exc
    if not content:
        return {}
    try:
        value = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ProviderRequestError("Provider API returned invalid JSON.") from exc
    if not isinstance(value, (dict, list)):
        raise ProviderRequestError("Provider API returned an unexpected response.")
    return value


def request_json(
    method: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    payload: Optional[Dict[str, Any]] = None,
    timeout: float = 30,
) -> Dict[str, Any]:
    value = request_json_value(
        method,
        url,
        headers=headers,
        payload=payload,
        timeout=timeout,
    )
    if not isinstance(value, dict):
        raise ProviderRequestError("Provider API returned an unexpected response.")
    return value
