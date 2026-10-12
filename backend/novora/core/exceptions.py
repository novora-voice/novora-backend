"""Typed exception hierarchy for Novora platform and provider adapters."""

class NovoraError(Exception):
    """Base exception for all Novora platform errors."""
    pass

class NovoraAdapterError(NovoraError):
    """Base exception for provider adapter failures."""
    pass

class PayloadValidationError(NovoraAdapterError):
    """Raised when an external payload violates structural or semantic validation constraints."""
    def __init__(self, message: str, field: str = "", details: dict = None) -> None:
        super().__init__(message)
        self.field = field
        self.details = details or {}

class PayloadSizeLimitError(PayloadValidationError):
    """Raised when an incoming payload exceeds byte or element limits."""
    pass

class UnauthorizedError(NovoraAdapterError):
    """Raised when authentication credentials or webhook signatures fail validation."""
    pass

class UnsupportedPayloadError(NovoraAdapterError):
    """Raised when an unrecognized event type or payload schema is received."""
    pass

class UnsupportedOperationError(NovoraAdapterError):
    """Raised when an operation is invoked that the provider does not support."""
    def __init__(self, provider: str, capability: str) -> None:
        super().__init__(f"Provider '{provider}' does not support capability '{capability}'.")
        self.provider = provider
        self.capability = capability

class SSRFSecurityError(NovoraError):
    """Raised when a remote endpoint configuration targets forbidden internal or private network addresses."""
    def __init__(self, destination: str, reason: str) -> None:
        super().__init__(f"SSRF violation: Access to destination '{destination}' is prohibited ({reason}).")
        self.destination = destination
        self.reason = reason

class TenantIsolationError(NovoraError):
    """Raised when a query attempts to access or mix data across tenant boundaries."""
    pass
