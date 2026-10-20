from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field, field_validator, model_validator

from novora.core.enums import (
    ConversationSource,
    MessageRole,
    OverallStatus,
    RuleStatus,
    RuleType,
)

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class ConversationMessage(BaseModel):
    id: str = Field(default_factory=lambda: f"msg_{uuid4().hex[:8]}")
    role: MessageRole
    content: str = Field(min_length=1)
    sequence: int = Field(ge=0)
    timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class EvidenceReference(BaseModel):
    message_id: str
    speaker: MessageRole
    sequence: int
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    snippet: str
    note: Optional[str] = None

class RuleConfig(BaseModel):
    id: str = Field(default_factory=lambda: f"rule_{uuid4().hex[:8]}")
    rule_type: RuleType
    name: Optional[str] = None
    description: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def assign_stable_id_when_missing(cls, value: Any) -> Any:
        if not isinstance(value, dict) or value.get("id"):
            return value
        identity = {
            key: value.get(key)
            for key in ("rule_type", "name", "description", "parameters")
        }
        encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str)
        value = dict(value)
        value["id"] = f"rule_{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:12]}"
        return value

class EvaluationScenario(BaseModel):
    id: str = Field(default_factory=lambda: f"scen_{uuid4().hex[:8]}")
    name: str = Field(min_length=1)
    business_goal: str = Field(min_length=1)
    success_criteria: List[str] = Field(default_factory=list)
    rules: List[RuleConfig] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)

class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: f"conv_{uuid4().hex[:8]}")
    scenario_id: Optional[str] = None
    source: ConversationSource = ConversationSource.TRANSCRIPT_UPLOAD
    messages: List[ConversationMessage] = Field(default_factory=list)
    trusted_action_records: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Verified action records from authoritative external systems (e.g. executed refund, booking)"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("messages")
    @classmethod
    def validate_message_sequences(cls, messages: List[ConversationMessage]) -> List[ConversationMessage]:
        if not messages:
            return messages
        # Verify sequences are ascending
        seqs = [m.sequence for m in messages]
        if seqs != sorted(seqs):
            raise ValueError("Messages must be strictly ordered by sequence number")
        return messages

class RuleResult(BaseModel):
    rule_id: str
    rule_name: str
    rule_type: RuleType
    rule_version: str = "1.0.0"
    status: RuleStatus
    explanation: str
    evidence: List[EvidenceReference] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)

class EvaluationReport(BaseModel):
    id: str = Field(default_factory=lambda: f"eval_{uuid4().hex[:8]}")
    scenario_id: str
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    conversation_id: str
    test_run_id: Optional[str] = None
    scenario_fingerprint: Optional[str] = None
    expected_rule_ids: List[str] = Field(default_factory=list)
    integrity_issues: List[str] = Field(default_factory=list)
    overall_status: OverallStatus
    summary: str
    rule_results: List[RuleResult] = Field(default_factory=list)
    total_rules: int = 0
    passed_rules: int = 0
    failed_rules: int = 0
    inconclusive_rules: int = 0
    evaluation_version: str = "1.0.0"
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="before")
    @classmethod
    def compute_counts(cls, data: Any) -> Any:
        if isinstance(data, dict):
            rule_results = data.get("rule_results", [])
            total = len(rule_results)
            passed = sum(1 for r in rule_results if (r.status if hasattr(r, 'status') else r.get("status")) == RuleStatus.PASS)
            failed = sum(1 for r in rule_results if (r.status if hasattr(r, 'status') else r.get("status")) == RuleStatus.FAIL)
            inconclusive = sum(1 for r in rule_results if (r.status if hasattr(r, 'status') else r.get("status")) == RuleStatus.INCONCLUSIVE)
            data["total_rules"] = total
            data["passed_rules"] = passed
            data["failed_rules"] = failed
            data["inconclusive_rules"] = inconclusive
        return data

class TelephonyCallRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"tel_{uuid4().hex[:8]}")
    provider: str = "twilio"
    call_sid: str
    from_number: Optional[str] = None
    to_number: Optional[str] = None
    call_status: str  # queued, ringing, in-progress, completed, failed, busy, no-answer
    duration_seconds: Optional[int] = None
    recording_sid: Optional[str] = None
    recording_url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

class WebhookEventRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"evt_{uuid4().hex[:8]}")
    provider: str  # elevenlabs, twilio, assemblyai
    event_id: str
    signature_verified: bool
    payload: Dict[str, Any] = Field(default_factory=dict)
    status: str = "processed"  # processed, duplicate, rejected
    created_at: datetime = Field(default_factory=utc_now)

class RuleComparison(BaseModel):
    rule_id: Optional[str] = None
    baseline_rule_id: Optional[str] = None
    candidate_rule_id: Optional[str] = None
    rule_name: str
    rule_type: RuleType
    baseline_status: RuleStatus
    candidate_status: RuleStatus
    change: str  # "regressed", "improved", "unchanged", "inconclusive", "not_evaluated"
    explanation_diff: str

class RegressionReport(BaseModel):
    scenario_id: str
    baseline_id: str
    candidate_id: str
    baseline_status: OverallStatus
    candidate_status: OverallStatus
    comparison_status: OverallStatus = OverallStatus.INCONCLUSIVE
    coverage_complete: bool = False
    coverage_issues: List[str] = Field(default_factory=list)
    regression_detected: bool
    net_status_change: str  # "regressed", "improved", "neutral"
    rule_comparisons: List[RuleComparison] = Field(default_factory=list)
    summary: str
    created_at: datetime = Field(default_factory=utc_now)
