from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from novora.core.models import EvaluationScenario
from novora.scenarios.templates import get_default_scenario_templates

router = APIRouter(prefix="/api/v1/scenarios", tags=["Scenario Templates"])

class TemplateInstantiateRequest(BaseModel):
    template_id: str
    custom_name: Optional[str] = None

@router.get("/templates", response_model=List[EvaluationScenario])
def list_scenario_templates() -> List[EvaluationScenario]:
    """Retrieve built-in starting templates: Customer Support, Incident Response, Language Practitioner."""
    return get_default_scenario_templates()

@router.post("/from-template", response_model=EvaluationScenario, status_code=status.HTTP_201_CREATED)
def instantiate_from_template(req: TemplateInstantiateRequest) -> EvaluationScenario:
    """Instantiate a new customizable scenario from a built-in template."""
    templates = {t.id: t for t in get_default_scenario_templates()}
    tpl = templates.get(req.template_id)
    if not tpl:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template with id '{req.template_id}' not found.",
        )
    cloned = tpl.model_copy(deep=True)
    if req.custom_name:
        cloned.name = req.custom_name
    return cloned
