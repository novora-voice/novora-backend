from datetime import datetime, timezone
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
    conversation_id: str
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
