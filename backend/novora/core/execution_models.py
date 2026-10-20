from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field
from novora.core.enums import TestRunStatus
from novora.core.models import EvaluationReport

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class ProviderConfig(BaseModel):
    id: str = Field(default_factory=lambda: f"pcfg_{uuid4().hex[:8]}")
    provider_name: str
    api_key_masked: str
    base_url: Optional[str] = None
    timeout_seconds: int = 30
    safe_mode: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

class AgentConfig(BaseModel):
    id: str = Field(default_factory=lambda: f"ag_{uuid4().hex[:8]}")
    provider_name: str
    external_agent_id: str
    name: str
    system_prompt: Optional[str] = None
    permitted_tools: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

class ToolCallRecord(BaseModel):
    call_id: str = Field(default_factory=lambda: f"tc_{uuid4().hex[:8]}")
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)
    status: str = "requested"  # requested, executed, forbidden, failed
    execution_time_ms: Optional[float] = None
    error: Optional[str] = None

class ToolResultRecord(BaseModel):
    call_id: str
    tool_name: str
    result: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)
    redacted_fields: List[str] = Field(default_factory=list)
    success: bool = True

class NormalizedProviderEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"evt_{uuid4().hex[:8]}")
    provider: str
    event_type: str  # transcript.user, transcript.agent, tool.call, session.ended, etc.
    sequence: int = 0
    timestamp: datetime = Field(default_factory=utc_now)
    payload: Dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None

class ScriptedTurn(BaseModel):
    sequence: int
    user_message: str
    expected_response_keywords: List[str] = Field(default_factory=list)
    expected_tools: List[str] = Field(default_factory=list)
    pause_after_seconds: float = 0.5

class TestCase(BaseModel):
    __test__ = False
    id: str = Field(default_factory=lambda: f"tc_{uuid4().hex[:8]}")
    scenario_id: str
    name: str
    description: Optional[str] = None
    scripted_turns: List[ScriptedTurn] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)

class TestRun(BaseModel):
    __test__ = False
    id: str = Field(default_factory=lambda: f"trun_{uuid4().hex[:8]}")

    scenario_id: str
    test_case_id: Optional[str] = None
    provider: str
    agent_id: str
    status: TestRunStatus = TestRunStatus.PENDING
    events: List[NormalizedProviderEvent] = Field(default_factory=list)
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    conversation_id: Optional[str] = None
    evaluation_id: Optional[str] = None
    error_message: Optional[str] = None
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = None

class EvaluationJobState(BaseModel):
    id: str
    status: str
    attempt: int = 0
    error: Optional[str] = None
    request_data: Dict[str, Any]
    test_run: Optional[TestRun] = None
    evaluation_report: Optional[EvaluationReport] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

class BatchEvaluation(BaseModel):
    id: str = Field(default_factory=lambda: f"batch_{uuid4().hex[:8]}")
    name: str
    scenario_id: str
    test_run_ids: List[str] = Field(default_factory=list)
    total_runs: int = 0
    passed_runs: int = 0
    failed_runs: int = 0
    inconclusive_runs: int = 0
    status: TestRunStatus = TestRunStatus.PENDING
    created_at: datetime = Field(default_factory=utc_now)

class IntegrationHealth(BaseModel):
    provider: str
    is_healthy: bool
    latency_ms: Optional[float] = None
    last_checked: datetime = Field(default_factory=utc_now)
    error: Optional[str] = None


class HttpToolEndpointConfig(BaseModel):
    id: str = Field(default_factory=lambda: f"tool_ep_{uuid4().hex[:12]}")
    name: str
    provider: str
    tool_name: str
    endpoint_url: str
    method: str = "GET"
    timeout_ms: int = 3000
    api_key_masked: str = ""
    has_auth: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class HttpToolEvaluationResult(BaseModel):
    id: str = Field(default_factory=lambda: f"tool_eval_{uuid4().hex[:12]}")
    endpoint_id: str
    endpoint_name: str
    provider: str
    tool_name: str
    method: str
    endpoint_url: str
    request_payload: Dict[str, Any]
    status_code: Optional[int] = None
    response_payload: Any = None
    latency_ms: Optional[float] = None
    success: bool
    performance_pass: bool
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
