from typing import Optional, Protocol, List
from novora.core.models import (
    Conversation,
    EvaluationReport,
    EvaluationScenario,
    RuleConfig,
    RuleResult,
)

class RuleEvaluatorProtocol(Protocol):
    """Protocol for all rule evaluation strategies."""

    def evaluate(
        self,
        config: RuleConfig,
        conversation: Conversation,
        scenario: EvaluationScenario,
    ) -> RuleResult:
        ...

class ScenarioRepository(Protocol):
    """Protocol for scenario persistence."""

    def save(self, scenario: EvaluationScenario) -> EvaluationScenario:
        ...

    def get(self, scenario_id: str) -> Optional[EvaluationScenario]:
        ...

    def list_all(self, limit: int = 50, offset: int = 0) -> List[EvaluationScenario]:
        ...

class EvaluationRepository(Protocol):
    """Protocol for evaluation report persistence."""

    def save(self, report: EvaluationReport) -> EvaluationReport:
        ...

    def get(self, report_id: str) -> Optional[EvaluationReport]:
        ...

    def list_by_scenario(self, scenario_id: str, limit: int = 50, offset: int = 0) -> List[EvaluationReport]:
        ...

class TelephonyRepository(Protocol):
    """Protocol for telephony call records persistence."""

    def save(self, record: "TelephonyCallRecord") -> "TelephonyCallRecord":
        ...

    def get(self, call_sid: str) -> Optional["TelephonyCallRecord"]:
        ...

    def list_all(self, limit: int = 50, offset: int = 0) -> List["TelephonyCallRecord"]:
        ...

class WebhookEventRepository(Protocol):
    """Protocol for webhook idempotency and audit logs."""

    def record_event(self, event: "WebhookEventRecord") -> "WebhookEventRecord":
        ...

    def is_processed(self, provider: str, event_id: str) -> bool:
        ...

    def get(self, event_id: str) -> Optional["WebhookEventRecord"]:
        ...

