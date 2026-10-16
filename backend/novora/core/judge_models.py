from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from novora.core.enums import RuleStatus

class RubricCriterion(BaseModel):
    criterion_id: str
    name: str
    description: str
    weight: float = 1.0
    rubric_guidance: str

class LLMJudgeVerdict(BaseModel):
    criterion_id: str
    status: RuleStatus
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    rationale: str
    evidence_citations: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class LLMJudgeResult(BaseModel):
    model_name: str = "mock-judge"
    is_available: bool = True
    verdicts: List[LLMJudgeVerdict] = Field(default_factory=list)
    latency_ms: Optional[float] = None
    error_message: Optional[str] = None
