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
