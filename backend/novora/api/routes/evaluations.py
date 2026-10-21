from typing import Any, List, Optional
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
        rules = [RuleConfig(**r.model_dump(exclude_none=True)) for r in req.rules]
        scen = EvaluationScenario(name=req.name, business_goal=req.business_goal, success_criteria=req.success_criteria, rules=rules)
        saved = scenarios.save(scen)
        return ScenarioResponse.model_validate(saved.model_dump())

    @app.get("/api/v1/scenarios/{scenario_id}", response_model=ScenarioResponse, tags=["Scenarios"])
    def get_scenario(scenario_id: str) -> ScenarioResponse:
        scen = scenarios.get(scenario_id)
        if not scen:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Scenario '{scenario_id}' not found.")
        return ScenarioResponse.model_validate(scen.model_dump())

    @app.put("/api/v1/scenarios/{scenario_id}", response_model=ScenarioResponse, tags=["Scenarios"])
    def update_scenario(scenario_id: str, req: CreateScenarioRequest) -> ScenarioResponse:
        existing = scenarios.get(scenario_id)
        rules = [RuleConfig(**r.model_dump(exclude_none=True)) for r in req.rules]
        scenario_fields: dict[str, Any] = {
            "name": req.name,
            "business_goal": req.business_goal,
            "success_criteria": req.success_criteria,
            "rules": rules,
        }
        if existing:
            scenario_fields["created_at"] = existing.created_at
        scen = EvaluationScenario(id=scenario_id, **scenario_fields)
        saved = scenarios.save(scen)
        return ScenarioResponse.model_validate(saved.model_dump())

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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scenario with id '{req.scenario_id}' not found. Cannot evaluate.",
            )
        conversations.save(req.conversation)
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
    def list_evaluation_reports(
        scenario_id: Optional[str] = Query(None),
        agent_id: Optional[str] = Query(None),
        agent_name: Optional[str] = Query(None),
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> List[EvaluationReportResponse]:
        if scenario_id:
            reports = evaluations.list_by_scenario(scenario_id=scenario_id, limit=limit, offset=offset)
        elif agent_id or agent_name:
            reports = evaluations.list_by_agent(agent_id=agent_id, agent_name=agent_name, limit=limit, offset=offset)
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Provide scenario_id, agent_id, or agent_name to list evaluation reports.",
            )
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
        run_repository = getattr(app.state, "test_run_repository", None)

        def validate_saved_evidence(report: Any, label: str) -> Any:
            issues = list(report.integrity_issues)
            conversation = conversations.get(report.conversation_id)
            if conversation is None:
                issues.append(f"{label} transcript {report.conversation_id} is missing from persistence.")
            elif not conversation.messages:
                issues.append(f"{label} transcript {report.conversation_id} has no persisted messages.")
            else:
                message_ids = {message.id for message in conversation.messages}
                dangling = {
                    evidence.message_id
                    for result in report.rule_results
                    for evidence in result.evidence
                    if evidence.message_id not in message_ids
                }
                if dangling:
                    issues.append(f"{label} has {len(dangling)} evidence reference(s) missing from its transcript.")

            if report.test_run_id:
                run = run_repository.get(report.test_run_id) if run_repository else None
                if run is None:
                    issues.append(f"{label} test run {report.test_run_id} is missing from persistence.")
                else:
                    if run.evaluation_id != report.id:
                        issues.append(f"{label} test run does not point back to evaluation {report.id}.")
                    if run.conversation_id != report.conversation_id:
                        issues.append(f"{label} test run and evaluation reference different transcripts.")
                    if run.scenario_id != report.scenario_id:
                        issues.append(f"{label} test run and evaluation reference different scenarios.")
            return report.model_copy(update={"integrity_issues": issues})

        base_rep = validate_saved_evidence(base_rep, "Baseline")
        cand_rep = validate_saved_evidence(cand_rep, "Candidate")
        diff = EvaluationComparator.compare(baseline=base_rep, candidate=cand_rep)
        return RegressionReportResponse.model_validate(diff.model_dump())
