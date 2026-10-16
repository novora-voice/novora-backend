from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from novora.core.models import EvaluationScenario, RuleConfig


class PayloadGenerationRequest(BaseModel):
    provider: str
    agent_id: str
    scenario: Optional[EvaluationScenario] = None
    scenario_id: Optional[str] = None
    template_id: Optional[str] = None
    user_instructions: Optional[str] = None
    custom_json: Optional[Dict[str, Any]] = None
    deterministic_rules: Optional[List[RuleConfig]] = None
    llm_evaluations: Optional[List[Dict[str, Any]]] = None


class PayloadJudgeVerdict(BaseModel):
    decision: str  # "pass", "revise", "reject"
    feedback: str
    issues: List[str] = Field(default_factory=list)
    confidence: float = 0.95
    model_used: str = "deepseek-payload-judge"


class PayloadPipelineResult(BaseModel):
    status: str  # "pass", "revised", "rejected", "error"
    provider: str
    agent_id: str
    final_payload: Dict[str, Any] = Field(default_factory=dict)
    revision_count: int = 0
    history: List[Dict[str, Any]] = Field(default_factory=list)
    judge_verdict: Optional[PayloadJudgeVerdict] = None
    schema_validation: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None


class PayloadValidationRequest(BaseModel):
    provider: str
    agent_id: str
    payload: Dict[str, Any]
    user_instructions: Optional[str] = None
    scenario_id: Optional[str] = None


class PayloadTemplate(BaseModel):
    id: str
    provider: str
    name: str
    description: str
    payload: Dict[str, Any]
