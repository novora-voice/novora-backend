from threading import Lock
from typing import Dict, List, Optional
from novora.core.interfaces import EvaluationRepository, ScenarioRepository
from novora.core.models import EvaluationReport, EvaluationScenario

class InMemoryScenarioRepository(ScenarioRepository):
    """Thread-safe in-memory scenario store for local development and fast tests."""

    def __init__(self) -> None:
        self._store: Dict[str, EvaluationScenario] = {}
        self._lock = Lock()

    def save(self, scenario: EvaluationScenario) -> EvaluationScenario:
        with self._lock:
            self._store[scenario.id] = scenario
        return scenario

    def get(self, scenario_id: str) -> Optional[EvaluationScenario]:
        with self._lock:
            return self._store.get(scenario_id)

    def list_all(self, limit: int = 50, offset: int = 0) -> List[EvaluationScenario]:
        with self._lock:
            items = list(self._store.values())
        return items[offset : offset + limit]

class InMemoryEvaluationRepository(EvaluationRepository):
    """Thread-safe in-memory evaluation report store."""

    def __init__(self) -> None:
        self._store: Dict[str, EvaluationReport] = {}
        self._lock = Lock()

    def save(self, report: EvaluationReport) -> EvaluationReport:
        with self._lock:
            self._store[report.id] = report
        return report

    def get(self, report_id: str) -> Optional[EvaluationReport]:
        with self._lock:
            return self._store.get(report_id)

    def list_by_scenario(self, scenario_id: str, limit: int = 50, offset: int = 0) -> List[EvaluationReport]:
        with self._lock:
            matching = [r for r in self._store.values() if r.scenario_id == scenario_id]
        return matching[offset : offset + limit]
