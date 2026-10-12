from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from novora.core.enums import RuleType
from novora.core.models import (
    Conversation,
    EvaluationReport,
    EvaluationScenario,
    RegressionReport,
    RuleConfig,
    TelephonyCallRecord,
)

class CreateRuleConfigRequest(BaseModel):
    rule_type: RuleType
    name: Optional[str] = None
    description: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)

class CreateScenarioRequest(BaseModel):
    name: str = Field(min_length=1, description="Scenario title")
    business_goal: str = Field(min_length=1, description="High level business objective")
    success_criteria: List[str] = Field(default_factory=list)
    rules: List[CreateRuleConfigRequest] = Field(default_factory=list)

class EvaluateConversationRequest(BaseModel):
    scenario_id: str = Field(description="Target scenario to evaluate against")
    conversation: Conversation = Field(description="Normalized conversation transcript and metadata")

class ImportTranscriptRequest(BaseModel):
    text: Optional[str] = Field(default=None, description="Multi-line dialogue text")
    records: Optional[List[Dict[str, Any]]] = Field(default=None, description="Structured message turns")
    scenario_id: Optional[str] = Field(default=None, description="Optional associated scenario ID")
    format: str = Field(default="dialogue_text", description="dialogue_text or records")

class CompareEvaluationsRequest(BaseModel):
    baseline_evaluation_id: str = Field(description="ID of baseline evaluation run")
    candidate_evaluation_id: str = Field(description="ID of candidate evaluation run to compare")

class ScenarioResponse(EvaluationScenario):
    pass

class EvaluationReportResponse(EvaluationReport):
    pass

class RegressionReportResponse(RegressionReport):
    pass

class TelephonyCallResponse(TelephonyCallRecord):
    pass

class ConversationResponse(Conversation):
    pass
