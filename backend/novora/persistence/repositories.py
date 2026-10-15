import threading
from typing import Dict, List, Optional
from novora.core.execution_models import (
    BatchEvaluation,
    ProviderConfig,
    TestCase,
    TestRun,
)

class InMemoryIntegrationRepository:
    def __init__(self) -> None:
        self._store: Dict[str, ProviderConfig] = {}
        self._lock = threading.Lock()

    def save(self, config: ProviderConfig) -> ProviderConfig:
        with self._lock:
            self._store[config.id] = config
            return config

    def get(self, config_id: str) -> Optional[ProviderConfig]:
        with self._lock:
            return self._store.get(config_id)

    def get_by_provider(self, provider: str) -> Optional[ProviderConfig]:
        with self._lock:
            for c in self._store.values():
                if c.provider_name.lower() == provider.lower():
                    return c
            return None

    def list_all(self) -> List[ProviderConfig]:
        with self._lock:
            return list(self._store.values())

class InMemoryTestCaseRepository:
    def __init__(self) -> None:
        self._store: Dict[str, TestCase] = {}
        self._lock = threading.Lock()

    def save(self, tc: TestCase) -> TestCase:
        with self._lock:
            self._store[tc.id] = tc
            return tc

    def get(self, tc_id: str) -> Optional[TestCase]:
        with self._lock:
            return self._store.get(tc_id)

    def list_by_scenario(self, scenario_id: str) -> List[TestCase]:
        with self._lock:
            return [t for t in self._store.values() if t.scenario_id == scenario_id]

class InMemoryTestRunRepository:
    def __init__(self) -> None:
        self._store: Dict[str, TestRun] = {}
        self._lock = threading.Lock()

    def save(self, run: TestRun) -> TestRun:
        with self._lock:
            self._store[run.id] = run
            return run

    def get(self, run_id: str) -> Optional[TestRun]:
        with self._lock:
            return self._store.get(run_id)

    def list_by_scenario(self, scenario_id: str) -> List[TestRun]:
        with self._lock:
            return [r for r in self._store.values() if r.scenario_id == scenario_id]

    def list_all(self, limit: int = 50, offset: int = 0) -> List[TestRun]:
        with self._lock:
            runs = sorted(self._store.values(), key=lambda r: r.started_at, reverse=True)
            return runs[offset : offset + limit]

class InMemoryBatchRepository:
    def __init__(self) -> None:
        self._store: Dict[str, BatchEvaluation] = {}
        self._lock = threading.Lock()

    def save(self, batch: BatchEvaluation) -> BatchEvaluation:
        with self._lock:
            self._store[batch.id] = batch
            return batch

    def get(self, batch_id: str) -> Optional[BatchEvaluation]:
        with self._lock:
            return self._store.get(batch_id)

    def list_all(self) -> List[BatchEvaluation]:
        with self._lock:
            return sorted(self._store.values(), key=lambda b: b.created_at, reverse=True)
