from typing import Any, List
from fastapi import FastAPI, HTTPException, Query, status
from novora.api.schemas import (
    CompareEvaluationsRequest,
    ConversationResponse,
    CreateScenarioRequest,
    EvaluateConversationRequest,
    EvaluationReportResponse,
    RegressionReportResponse,
    ScenarioResponse,
)
from novora.core.models import Conversation, EvaluationScenario, RuleConfig
from novora.evaluation.comparator import EvaluationComparator

def register_evaluation_routes(
    app: FastAPI,
    scenarios: Any,
    evaluations: Any,
    conversations: Any,
    engine: Any,
) -> None:
    @app.post("/api/v1/scenarios", response_model=ScenarioResponse, status_code=status.HTTP_201_CREATED, tags=["Scenarios"])
    def create_scenario(req: CreateScenarioRequest) -> ScenarioResponse:
        rules = [RuleConfig(rule_type=r.rule_type, name=r.name, description=r.description, parameters=r.parameters) for r in req.rules]
        scen = EvaluationScenario(name=req.name, business_goal=req.business_goal, success_criteria=req.success_criteria, rules=rules)
        saved = scenarios.save(scen)
        return ScenarioResponse.model_validate(saved.model_dump())

    @app.get("/api/v1/scenarios/{scenario_id}", response_model=ScenarioResponse, tags=["Scenarios"])
    def get_scenario(scenario_id: str) -> ScenarioResponse:
        scen = scenarios.get(scenario_id)
        if not scen:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Scenario '{scenario_id}' not found.")
        return ScenarioResponse.model_validate(scen.model_dump())

    @app.get("/api/v1/scenarios", response_model=List[ScenarioResponse], tags=["Scenarios"])
    def list_scenarios(limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)) -> List[ScenarioResponse]:
        items = scenarios.list_all(limit=limit, offset=offset)
        return [ScenarioResponse.model_validate(i.model_dump()) for i in items]

    @app.get("/api/v1/conversations/{conversation_id}", response_model=ConversationResponse, tags=["Conversations"])
    def get_conversation(conversation_id: str) -> ConversationResponse:
        conv = conversations.get(conversation_id)
        if not conv:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Conversation '{conversation_id}' not found.")
        return ConversationResponse.model_validate(conv.model_dump())

    @app.get("/api/v1/conversations", response_model=List[ConversationResponse], tags=["Conversations"])
    def list_conversations(limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)) -> List[ConversationResponse]:
        items = conversations.list_all(limit=limit, offset=offset)
        return [ConversationResponse.model_validate(i.model_dump()) for i in items]

    @app.post("/api/v1/evaluations", response_model=EvaluationReportResponse, status_code=status.HTTP_201_CREATED, tags=["Evaluations"])
    def create_evaluation(req: EvaluateConversationRequest) -> EvaluationReportResponse:
        scen = scenarios.get(req.scenario_id)
        if not scen:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Scenario '{req.scenario_id}' not found.")
        report = engine.evaluate(conversation=req.conversation, scenario=scen)
        saved = evaluations.save(report)
        return EvaluationReportResponse.model_validate(saved.model_dump())

    @app.get("/api/v1/evaluations/{evaluation_id}", response_model=EvaluationReportResponse, tags=["Evaluations"])
    def get_evaluation_report(evaluation_id: str) -> EvaluationReportResponse:
        report = evaluations.get(evaluation_id)
        if not report:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Evaluation report '{evaluation_id}' not found.")
        return EvaluationReportResponse.model_validate(report.model_dump())

    @app.get("/api/v1/evaluations", response_model=List[EvaluationReportResponse], tags=["Evaluations"])
    def list_evaluation_reports(scenario_id: str = Query(...), limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)) -> List[EvaluationReportResponse]:
        reports = evaluations.list_by_scenario(scenario_id=scenario_id, limit=limit, offset=offset)
        return [EvaluationReportResponse.model_validate(r.model_dump()) for r in reports]

    @app.get("/api/v1/scenarios/{scenario_id}/history", response_model=List[EvaluationReportResponse], tags=["Evaluations"])
    def get_scenario_history(scenario_id: str, limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)) -> List[EvaluationReportResponse]:
        reports = evaluations.list_by_scenario(scenario_id=scenario_id, limit=limit, offset=offset)
        return [EvaluationReportResponse.model_validate(r.model_dump()) for r in reports]

    @app.post("/api/v1/evaluations/compare", response_model=RegressionReportResponse, tags=["Evaluations"])
    def compare_evaluations(req: CompareEvaluationsRequest) -> RegressionReportResponse:
        base_rep = evaluations.get(req.baseline_evaluation_id)
        cand_rep = evaluations.get(req.candidate_evaluation_id)
        if not base_rep or not cand_rep:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Baseline or candidate evaluation not found.")
        diff = EvaluationComparator.compare(baseline=base_rep, candidate=cand_rep)
        return RegressionReportResponse.model_validate(diff.model_dump())
