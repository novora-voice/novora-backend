import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Set
from novora.core.exceptions import NovoraError
from novora.core.execution_models import ToolCallRecord, ToolResultRecord

class ToolSecurityError(NovoraError):
    """Raised when an unapproved or dangerous tool call is attempted."""
    pass

class ToolRegistry:
    """Explicit registry of permitted tools with argument validation and sandbox execution."""

    SENSITIVE_KEYS: Set[str] = {
        "password", "secret", "token", "ssn", "credit_card", "api_key", "pin", "auth"
    }
    MOCK_SUPPORT_TICKETS: Dict[str, Dict[str, Any]] = {}

    def __init__(self, sandbox_mode: bool = True) -> None:
        self.sandbox_mode = sandbox_mode
        self._handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self._register_default_sandbox_tools()

    def register(
        self,
        name: str,
        handler: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> None:
        self._handlers[name.lower().strip()] = handler

    def is_permitted(self, tool_name: str) -> bool:
        return tool_name.lower().strip() in self._handlers

    def execute_tool(
        self,
        tool_call: ToolCallRecord,
        permitted_list: Optional[List[str]] = None,
    ) -> ToolResultRecord:
        clean_name = tool_call.tool_name.lower().strip()
        if permitted_list and clean_name not in [p.lower().strip() for p in permitted_list]:
            tool_call.status = "forbidden"
            tool_call.error = f"Tool '{tool_call.tool_name}' is not in permitted list."
            return ToolResultRecord(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                result={"error": tool_call.error},
                success=False,
            )

        handler = self._handlers.get(clean_name)
        if not handler:
            tool_call.status = "forbidden"
            tool_call.error = f"Tool '{tool_call.tool_name}' is not registered."
            return ToolResultRecord(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                result={"error": tool_call.error},
                success=False,
            )

        start = time.perf_counter()
        try:
            raw_result = handler(tool_call.arguments)
            tool_call.status = "executed"
            tool_call.execution_time_ms = round((time.perf_counter() - start) * 1000, 2)
            redacted_result, redacted_keys = self.redact_sensitive_values(raw_result)
            return ToolResultRecord(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                result=redacted_result,
                redacted_fields=redacted_keys,
                success=True,
            )
        except Exception as exc:
            tool_call.status = "failed"
            tool_call.error = str(exc)
            tool_call.execution_time_ms = round((time.perf_counter() - start) * 1000, 2)
            return ToolResultRecord(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                result={"error": str(exc)},
                success=False,
            )

    def redact_sensitive_values(
        self, data: Dict[str, Any]
    ) -> tuple[Dict[str, Any], List[str]]:
        redacted = {}
        redacted_fields = []
        for k, v in data.items():
            if any(s in k.lower() for s in self.SENSITIVE_KEYS):
                redacted[k] = "[REDACTED]"
                redacted_fields.append(k)
            elif isinstance(v, dict):
                sub_redacted, sub_fields = self.redact_sensitive_values(v)
                redacted[k] = sub_redacted
                redacted_fields.extend(sub_fields)
            else:
                redacted[k] = v
        return redacted, redacted_fields

    def _register_default_sandbox_tools(self) -> None:
        self.register(
            "check_order",
            lambda args: {
                "order_id": args.get("order_id", "ORD-1234"),
                "status": "delivered",
                "total": 49.99,
                "customer_email": args.get("customer_email", "cust@example.com"),
            },
        )
        self.register(
            "lookup_policy",
            lambda args: {
                "policy_name": args.get("policy", "return_window"),
                "allowed_days": 30,
                "requires_receipt": True,
            },
        )
        self.register(
            "refund_tool",
            lambda args: {
                "transaction_id": "tx_mock_refund_881",
                "amount": float(args.get("amount", 25.0)),
                "status": "sandbox_confirmed",
            },
        )
        self.register(
            "booking_tool",
            lambda args: {
                "reservation_id": "res_mock_442",
                "date": args.get("date", "2026-10-20"),
                "status": "confirmed",
            },
        )
        self.register(
            "check_system_status",
            lambda args: {
                "service": args.get("service", "core_api"),
                "status": "operational",
                "latency_ms": 15,
            },
        )
        self.register("create_support_ticket", self._create_support_ticket)

    @classmethod
    def _create_support_ticket(cls, args: Dict[str, Any]) -> Dict[str, Any]:
        ticket_id = f"TICK-{str(uuid.uuid4())[:8].upper()}"
        ticket = {
            "email": args.get("email"),
            "issue": args.get("issue") or args.get("description"),
            "status": "Open",
        }
        cls.MOCK_SUPPORT_TICKETS[ticket_id] = ticket
        return {"status": "success", "ticket_id": ticket_id, **ticket}
