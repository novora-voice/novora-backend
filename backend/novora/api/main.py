from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Header, HTTPException, Query, Request, status
from novora.adapters.providers.assemblyai import AssemblyAIAdapter
from novora.adapters.providers.elevenlabs import ElevenLabsAdapter
from novora.adapters.providers.transcript_importer import TranscriptImporter
from novora.adapters.providers.twilio import TwilioAdapter
from novora.adapters.repositories import (
    InMemoryEvaluationRepository,
    InMemoryScenarioRepository,
    InMemoryTelephonyRepository,
    InMemoryWebhookEventRepository,
)
from novora.api.schemas import (
    CompareEvaluationsRequest,
    ConversationResponse,
    CreateScenarioRequest,
    EvaluateConversationRequest,
    EvaluationReportResponse,
    ImportTranscriptRequest,
    RegressionReportResponse,
    ScenarioResponse,
    TelephonyCallResponse,
)
from novora.core.models import EvaluationScenario, RuleConfig, WebhookEventRecord
from novora.evaluation.comparator import EvaluationComparator
from novora.evaluation.engine import EvaluationEngine

def create_app(
    scenario_repo: Optional[InMemoryScenarioRepository] = None,
    evaluation_repo: Optional[InMemoryEvaluationRepository] = None,
    telephony_repo: Optional[InMemoryTelephonyRepository] = None,
    webhook_repo: Optional[InMemoryWebhookEventRepository] = None,
    evaluation_engine: Optional[EvaluationEngine] = None,
    elevenlabs_secret: str = "test_elevenlabs_secret",
    twilio_auth_token: str = "test_twilio_auth_token",
) -> FastAPI:
    """Factory creating and configuring the Novora FastAPI application."""
    app = FastAPI(
        title="Novora Evaluation API",
        version="0.1.0",
        description="Deterministic evaluation platform for enterprise AI voice agents.",
    )

    scenarios = scenario_repo or InMemoryScenarioRepository()
    evaluations = evaluation_repo or InMemoryEvaluationRepository()
    telephony = telephony_repo or InMemoryTelephonyRepository()
    webhooks = webhook_repo or InMemoryWebhookEventRepository()
    engine = evaluation_engine or EvaluationEngine()

    el_adapter = ElevenLabsAdapter(webhook_repo=webhooks)
    tw_adapter = TwilioAdapter()
    aai_adapter = AssemblyAIAdapter()

    @app.get("/health", tags=["Health"])
    def health_check():
        return {"status": "ok", "service": "novora-core-api"}

    # ---------------------------------------------------------
    # Scenario Endpoints
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Evaluation & History Endpoints
    # ---------------------------------------------------------
    @app.post(
        "/api/v1/evaluations",
        response_model=EvaluationReportResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["Evaluations"],
    )
    def evaluate_conversation(
        req: EvaluateConversationRequest,
    ) -> EvaluationReportResponse:
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
        reports = evaluations.list_by_scenario(
            scenario_id=scenario_id, limit=limit, offset=offset
        )
        return [
            EvaluationReportResponse.model_validate(r.model_dump()) for r in reports
        ]

    @app.get(
        "/api/v1/scenarios/{scenario_id}/history",
        response_model=List[EvaluationReportResponse],
        tags=["Evaluations"],
    )
    def get_scenario_evaluation_history(
        scenario_id: str,
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> List[EvaluationReportResponse]:
        scenario = scenarios.get(scenario_id)
        if not scenario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scenario '{scenario_id}' not found.",
            )
        reports = evaluations.list_by_scenario(
            scenario_id=scenario_id, limit=limit, offset=offset
        )
        return [
            EvaluationReportResponse.model_validate(r.model_dump()) for r in reports
        ]

    @app.post(
        "/api/v1/evaluations/compare",
        response_model=RegressionReportResponse,
        tags=["Evaluations"],
    )
    def compare_evaluation_runs(
        req: CompareEvaluationsRequest,
    ) -> RegressionReportResponse:
        base_rep = evaluations.get(req.baseline_evaluation_id)
        if not base_rep:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Baseline evaluation '{req.baseline_evaluation_id}' not found.",
            )
        cand_rep = evaluations.get(req.candidate_evaluation_id)
        if not cand_rep:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Candidate evaluation '{req.candidate_evaluation_id}' not found.",
            )

        diff = EvaluationComparator.compare(baseline=base_rep, candidate=cand_rep)
        return RegressionReportResponse.model_validate(diff.model_dump())

    # ---------------------------------------------------------
    # Ingestion & Provider Webhooks
    # ---------------------------------------------------------
    @app.post(
        "/api/v1/conversations/import-transcript",
        response_model=ConversationResponse,
        tags=["Ingestion"],
    )
    def import_transcript(req: ImportTranscriptRequest) -> ConversationResponse:
        if req.text:
            conv = TranscriptImporter.from_text(
                text=req.text,
                scenario_id=req.scenario_id,
            )
        elif req.records:
            conv = TranscriptImporter.from_records(
                records=req.records,
                scenario_id=req.scenario_id,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either 'text' or 'records' must be provided in transcript import request.",
            )
        return ConversationResponse.model_validate(conv.model_dump())

    @app.post(
        "/api/v1/webhooks/elevenlabs",
        status_code=status.HTTP_200_OK,
        tags=["Webhooks"],
    )
    async def elevenlabs_webhook(
        request: Request,
        elevenlabs_signature: Optional[str] = Header(None, alias="elevenlabs-signature"),
        x_timestamp: Optional[str] = Header(None, alias="x-timestamp"),
        scenario_id: Optional[str] = Query(None),
        auto_evaluate: bool = Query(False),
    ):
        raw_body = await request.body()
        payload = await request.json()

        # Check signature if provided or required
        verified = False
        if elevenlabs_signature:
            verified = el_adapter.verify_webhook_signature(
                raw_body=raw_body,
                signature=elevenlabs_signature,
                secret=elevenlabs_secret,
                timestamp=x_timestamp or "",
            )
            if not verified:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid ElevenLabs webhook signature.",
                )

        event_id = str(payload.get("conversation_id", payload.get("id", "")))
        is_dup, conv = el_adapter.process_webhook_idempotent(
            event_id=event_id,
            payload=payload,
            signature_verified=verified,
            scenario_id=scenario_id,
        )

        if is_dup:
            return {"status": "already_processed", "event_id": event_id}

        result: Dict[str, Any] = {
            "status": "processed",
            "conversation_id": conv.id if conv else None,
            "message_count": len(conv.messages) if conv else 0,
        }

        # Auto-evaluate against specified scenario if requested
        if auto_evaluate and scenario_id and conv:
            scen = scenarios.get(scenario_id)
            if scen:
                report = engine.evaluate(conversation=conv, scenario=scen)
                evaluations.save(report)
                result["evaluation_report_id"] = report.id
                result["overall_status"] = report.overall_status.value

        return result

    @app.post(
        "/api/v1/webhooks/twilio",
        response_model=TelephonyCallResponse,
        tags=["Webhooks"],
    )
    async def twilio_webhook(
        request: Request,
        x_twilio_signature: Optional[str] = Header(None, alias="X-Twilio-Signature"),
    ) -> TelephonyCallResponse:
        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type:
            form_data = await request.form()
            payload = dict(form_data)
        else:
            payload = await request.json()

        if x_twilio_signature and twilio_auth_token:
            params = {k: str(v) for k, v in payload.items()}
            is_valid = tw_adapter.verify_webhook_signature(
                url=str(request.url),
                params=params,
                signature=x_twilio_signature,
                auth_token=twilio_auth_token,
            )
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid Twilio signature header.",
                )

        record = tw_adapter.parse_telephony_event(payload)
        saved = telephony.save(record)
        return TelephonyCallResponse.model_validate(saved.model_dump())

    @app.post(
        "/api/v1/webhooks/assemblyai",
        response_model=ConversationResponse,
        tags=["Webhooks"],
    )
    async def assemblyai_webhook(
        payload: Dict[str, Any],
        scenario_id: Optional[str] = Query(None),
    ) -> ConversationResponse:
        conv = aai_adapter.parse_transcription_result(
            payload=payload,
            scenario_id=scenario_id,
        )
        return ConversationResponse.model_validate(conv.model_dump())

    @app.get(
        "/api/v1/telephony/calls",
        response_model=List[TelephonyCallResponse],
        tags=["Telephony"],
    )
    def list_telephony_calls(
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> List[TelephonyCallResponse]:
        items = telephony.list_all(limit=limit, offset=offset)
        return [TelephonyCallResponse.model_validate(i.model_dump()) for i in items]

    return app

# Default ASGI app instance
app = create_app()
