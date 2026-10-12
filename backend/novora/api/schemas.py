from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from novora.core.enums import RuleType
from novora.core.models import Conversation, EvaluationReport, EvaluationScenario, RuleConfig

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

class ScenarioResponse(EvaluationScenario):
    pass

class EvaluationReportResponse(EvaluationReport):
    pass
