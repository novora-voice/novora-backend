from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query, status
from novora.adapters.repositories import (
    InMemoryEvaluationRepository,
    InMemoryScenarioRepository,
)
from novora.api.schemas import (
    CreateScenarioRequest,
    EvaluateConversationRequest,
    EvaluationReportResponse,
    ScenarioResponse,
)
from novora.core.models import EvaluationScenario, RuleConfig
from novora.evaluation.engine import EvaluationEngine

def create_app(
    scenario_repo: Optional[InMemoryScenarioRepository] = None,
    evaluation_repo: Optional[InMemoryEvaluationRepository] = None,
    evaluation_engine: Optional[EvaluationEngine] = None,
) -> FastAPI:
    """Factory creating and configuring the Novora FastAPI application."""
    app = FastAPI(
        title="Novora Evaluation API",
        version="0.1.0",
        description="Deterministic evaluation platform for enterprise AI voice agents.",
    )

    scenarios = scenario_repo or InMemoryScenarioRepository()
    evaluations = evaluation_repo or InMemoryEvaluationRepository()
    engine = evaluation_engine or EvaluationEngine()

    @app.get("/health", tags=["Health"])
    def health_check():
        return {"status": "ok", "service": "novora-core-api"}

    @app.post(
        "/api/v1/scenarios",
        response_model=ScenarioResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["Scenarios"],
    )
    def create_scenario(req: CreateScenarioRequest) -> ScenarioResponse:
        rules = [
            RuleConfig(
                rule_type=r.rule_type,
                name=r.name,
                description=r.description,
                parameters=r.parameters,
            )
            for r in req.rules
        ]
        scenario = EvaluationScenario(
            name=req.name,
            business_goal=req.business_goal,
            success_criteria=req.success_criteria,
            rules=rules,
        )
        saved = scenarios.save(scenario)
        return ScenarioResponse.model_validate(saved.model_dump())

    @app.get(
        "/api/v1/scenarios/{scenario_id}",
        response_model=ScenarioResponse,
        tags=["Scenarios"],
    )
    def get_scenario(scenario_id: str) -> ScenarioResponse:
        scenario = scenarios.get(scenario_id)
        if not scenario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scenario with id '{scenario_id}' not found.",
            )
        return ScenarioResponse.model_validate(scenario.model_dump())

    @app.get(
        "/api/v1/scenarios",
        response_model=List[ScenarioResponse],
        tags=["Scenarios"],
    )
    def list_scenarios(
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> List[ScenarioResponse]:
        items = scenarios.list_all(limit=limit, offset=offset)
        return [ScenarioResponse.model_validate(i.model_dump()) for i in items]

    @app.post(
        "/api/v1/evaluations",
        response_model=EvaluationReportResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["Evaluations"],
    )
    def evaluate_conversation(req: EvaluateConversationRequest) -> EvaluationReportResponse:
        scenario = scenarios.get(req.scenario_id)
        if not scenario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scenario with id '{req.scenario_id}' not found. Cannot evaluate.",
            )

        report = engine.evaluate(conversation=req.conversation, scenario=scenario)
        saved_report = evaluations.save(report)
        return EvaluationReportResponse.model_validate(saved_report.model_dump())

    @app.get(
        "/api/v1/evaluations/{evaluation_id}",
        response_model=EvaluationReportResponse,
        tags=["Evaluations"],
    )
    def get_evaluation_report(evaluation_id: str) -> EvaluationReportResponse:
        report = evaluations.get(evaluation_id)
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluation report with id '{evaluation_id}' not found.",
            )
        return EvaluationReportResponse.model_validate(report.model_dump())

    @app.get(
        "/api/v1/evaluations",
        response_model=List[EvaluationReportResponse],
        tags=["Evaluations"],
    )
    def list_evaluation_reports(
        scenario_id: str = Query(..., description="Filter reports by scenario ID"),
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> List[EvaluationReportResponse]:
        reports = evaluations.list_by_scenario(scenario_id=scenario_id, limit=limit, offset=offset)
        return [EvaluationReportResponse.model_validate(r.model_dump()) for r in reports]

    return app

# Default ASGI app instance
app = create_app()
