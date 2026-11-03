"""Voxia tool registry and mock business tools."""
from __future__ import annotations
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Mock order dataset ──────────────────────────────────────────────────────
_ORDER_FIXTURE: Dict[str, Dict[str, Any]] = {
    "ORD-1001": {
        "order_id": "ORD-1001",
        "customer_name": "Alice Johnson",
        "product": "Wireless Headphones Pro",
        "status": "shipped",
        "tracking_number": "TRK-884421",
        "estimated_delivery": "2026-11-05",
        "amount": 129.99,
        "currency": "USD",
    },
    "ORD-1002": {
        "order_id": "ORD-1002",
        "customer_name": "Bob Smith",
        "product": "Ergonomic Office Chair",
        "status": "processing",
        "tracking_number": None,
        "estimated_delivery": "2026-11-08",
        "amount": 349.00,
        "currency": "USD",
    },
    "ORD-1003": {
        "order_id": "ORD-1003",
        "customer_name": "Carol White",
        "product": "Mechanical Keyboard",
        "status": "delivered",
        "tracking_number": "TRK-229917",
        "estimated_delivery": "2026-10-29",
        "amount": 89.50,
        "currency": "USD",
    },
}


def lookup_order(order_id: str) -> Dict[str, Any]:
    """Mock tool: look up an order by ID. Returns fixture data or error."""
    normalized = order_id.strip().upper()
    if normalized in _ORDER_FIXTURE:
        return {"found": True, "order": _ORDER_FIXTURE[normalized]}
    return {"found": False, "order_id": normalized, "error": "Order not found in our system."}


# ── Tool registry ────────────────────────────────────────────────────────────
_AUTHORIZED_TOOLS: Dict[str, Callable[..., Any]] = {
    "lookup_order": lookup_order,
}

_TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "lookup_order": {
        "name": "lookup_order",
        "description": "Look up customer order details by order ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The order reference number, e.g. ORD-1001",
                }
            },
            "required": ["order_id"],
        },
    }
}


def get_tool_schemas() -> List[Dict[str, Any]]:
    return list(_TOOL_SCHEMAS.values())


def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> Any:
    """Execute an authorized tool. Raises ValueError for unauthorized tools."""
    if tool_name not in _AUTHORIZED_TOOLS:
        raise ValueError(f"Tool '{tool_name}' is not authorized.")
    # Validate required arguments
    schema = _TOOL_SCHEMAS.get(tool_name, {})
    required = schema.get("parameters", {}).get("required", [])
    for req_arg in required:
        if req_arg not in arguments:
            raise ValueError(f"Missing required argument '{req_arg}' for tool '{tool_name}'.")
    func = _AUTHORIZED_TOOLS[tool_name]
    valid_keys = set(schema.get("parameters", {}).get("properties", {}).keys())
    filtered_args = {k: v for k, v in arguments.items() if k in valid_keys} if valid_keys else arguments
    return func(**filtered_args)
