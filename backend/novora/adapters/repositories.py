from threading import Lock
from typing import Any, Dict, List, Optional
from novora.core.interfaces import EvaluationRepository, ScenarioRepository
from novora.core.models import Conversation, EvaluationReport, EvaluationScenario, TelephonyCallRecord, WebhookEventRecord

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

class InMemoryConversationRepository:
    """Thread-safe in-memory conversation store for ingested conversations."""

    def __init__(self) -> None:
        self._store: Dict[str, Conversation] = {}
        self._lock = Lock()

    def save(self, conversation: Conversation) -> Conversation:
        with self._lock:
            self._store[conversation.id] = conversation
        return conversation

    def get(self, conversation_id: str) -> Optional[Conversation]:
        with self._lock:
            return self._store.get(conversation_id)

    def list_all(self, limit: int = 50, offset: int = 0) -> List[Conversation]:
        with self._lock:
            items = list(self._store.values())
        return items[offset : offset + limit]

class InMemoryTelephonyRepository:
    """Thread-safe in-memory telephony call store."""

    def __init__(self) -> None:
        self._store: Dict[str, TelephonyCallRecord] = {}
        self._lock = Lock()

    def save(self, record: TelephonyCallRecord) -> TelephonyCallRecord:
        with self._lock:
            self._store[record.call_sid] = record
        return record

    def get(self, call_sid: str) -> Optional[TelephonyCallRecord]:
        with self._lock:
            return self._store.get(call_sid)

    def list_all(self, limit: int = 50, offset: int = 0) -> List[TelephonyCallRecord]:
        with self._lock:
            items = list(self._store.values())
        return items[offset : offset + limit]

class InMemoryWebhookEventRepository:
    """Thread-safe in-memory webhook event store for audit and idempotency."""

    def __init__(self) -> None:
        self._store: Dict[str, WebhookEventRecord] = {}
        self._lock = Lock()

    def record_event(self, event: WebhookEventRecord) -> WebhookEventRecord:
        with self._lock:
            key = f"{event.provider}:{event.event_id}"
            self._store[key] = event
        return event

    def is_processed(self, provider: str, event_id: str) -> bool:
        with self._lock:
            key = f"{provider}:{event_id}"
            return key in self._store

    def get(self, event_id: str) -> Optional[WebhookEventRecord]:
        with self._lock:
            for k, v in self._store.items():
                if k.endswith(f":{event_id}"):
                    return v
        return None

