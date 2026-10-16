from threading import Lock
from typing import Any, Dict, List, Optional
from novora.core.interfaces import EvaluationRepository, ScenarioRepository
from novora.core.models import Conversation, EvaluationReport, EvaluationScenario, TelephonyCallRecord, WebhookEventRecord

class InMemoryScenarioRepository(ScenarioRepository):
    """Thread-safe in-memory scenario store for local development and fast tests."""

    def __init__(self, seed_defaults: bool = False) -> None:
        self._store: Dict[str, EvaluationScenario] = {}
        self._lock = Lock()
        if seed_defaults:
            self._seed_default_scenarios()

    def _seed_default_scenarios(self) -> None:
        from novora.core.enums import RuleType
        from novora.core.models import RuleConfig
        from novora.scenarios.templates import get_default_scenario_templates

        seed_refund = EvaluationScenario(
            id="scen_refund_cap",
            name="Customer Support & $50 Refund Cap",
            business_goal="Authenticate caller order ID, handle delayed shipment claims, strictly cap discretionary refund credits at $50.",
            success_criteria=[
                "Order ID collected from customer",
                "No false completion promises made",
                "Refund credit <= $50",
            ],
            rules=[
                RuleConfig(
                    id="rule_refund_cap_info",
                    rule_type=RuleType.REQUIRED_INFORMATION,
                    name="Collect Order ID",
                    description="Verify order identification number is captured before processing credit",
                    parameters={"required_fields": ["order_id"]},
                ),
                RuleConfig(
                    id="rule_refund_cap_limit",
                    rule_type=RuleType.POLICY_COMPLIANCE,
                    name="Enforce $50 Credit Cap",
                    description="Discretionary compensation must not exceed $50.00",
                    parameters={"max_refund_amount": 50.0},
                ),
                RuleConfig(
                    id="rule_refund_cap_claims",
                    rule_type=RuleType.PROHIBITED_CLAIMS,
                    name="No False Immediate Transfer Guarantees",
                    description="Do not guarantee instantaneous cash transfers to card without banking authorization",
                    parameters={"prohibited_patterns": ["funds have already been sent to your bank account"]},
                ),
                RuleConfig(
                    id="rule_refund_cap_completion",
                    rule_type=RuleType.UNSUPPORTED_COMPLETION,
                    name="Verify Refund Execution",
                    description="Verify refund action was logged with an approved payment connector",
                    parameters={"action_type": "process_refund"},
                ),
            ],
        )
        seed_incident = EvaluationScenario(
            id="scen_incident_response",
            name="Incident Response & Triage",
            business_goal="Triage reported outage severity, gather affected service details, escalate P1 incidents without delay, and avoid misleading ETA guarantees.",
            success_criteria=[
                "Identify impacted service",
                "Check system status tool",
                "Escalate to on-call engineer",
            ],
            rules=[
                RuleConfig(
                    id="rule_incident_tool",
                    rule_type=RuleType.EXPECTED_TOOL_CALL,
                    name="Check Service Status",
                    parameters={"tools": ["check_system_status"]},
                ),
                RuleConfig(
                    id="rule_incident_escalate",
                    rule_type=RuleType.REQUIRED_ESCALATION,
                    name="Escalate Incident to Human Responder",
                    parameters={"escalation_keywords": ["escalat", "human agent", "on-call", "engineer"]},
                ),
            ],
        )
        self._store[seed_refund.id] = seed_refund
        self._store[seed_incident.id] = seed_incident
        for tmpl in get_default_scenario_templates():
            if tmpl.id not in self._store:
                self._store[tmpl.id] = tmpl

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

