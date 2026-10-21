from typing import Any, Dict, List, Optional
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from novora.core.enums import OverallStatus, TestRunStatus
from novora.core.execution_models import (
    AgentConfig,
    BatchEvaluation,
    TestCase,
)
from novora.core.models import EvaluationScenario
from novora.evaluation.orchestration.pipeline import CombinedEvaluationPipeline
from novora.scenarios.templates import get_default_test_case_for_scenario

router = APIRouter(prefix="/api/v1/batches", tags=["Batch Evaluations"])
pipeline = CombinedEvaluationPipeline()

class BatchCreateRequest(BaseModel):
    name: str
    scenario: EvaluationScenario
    agent: AgentConfig
    test_cases: Optional[List[TestCase]] = None
    provider_config: Dict[str, Any] = {}

class BatchDetailResponse(BaseModel):
    batch: BatchEvaluation
    test_run_statuses: List[Dict[str, Any]]

@router.post("", response_model=BatchEvaluation, status_code=status.HTTP_201_CREATED)
def create_and_run_batch(req: BatchCreateRequest, request: Request) -> BatchEvaluation:
    """Execute a batch evaluation across multiple test cases."""
    scenario_repository = request.app.state.scenario_repository
    test_case_repository = request.app.state.test_case_repository
    test_run_repository = request.app.state.test_run_repository
    evaluation_repository = request.app.state.evaluation_repository
    conversation_repository = request.app.state.conversation_repository
    agent_repository = request.app.state.agent_repository
    batch_repository = request.app.state.batch_repository

    scenario_repository.save(req.scenario)
    agent_repository.save(req.agent)
    tcs = req.test_cases or [get_default_test_case_for_scenario(req.scenario.id)]
    run_ids: List[str] = []
    passed = 0
    failed = 0
    inconclusive = 0

    for tc in tcs:
        test_case_repository.save(tc)
        run, report, conv = pipeline.run_pipeline(
            scenario=req.scenario,
            test_case=tc,
            agent=req.agent,
            provider_config=req.provider_config,
        )
        conversation_repository.save(conv)
        evaluation_repository.save(report)
        test_run_repository.save(run)
        run_ids.append(run.id)

        if report.overall_status == OverallStatus.PASS:
            passed += 1
        elif report.overall_status == OverallStatus.FAIL:
            failed += 1
        else:
            inconclusive += 1

    overall_batch_status = TestRunStatus.COMPLETED
    if failed > 0:
        overall_batch_status = TestRunStatus.FAILED

    batch = BatchEvaluation(
        id=f"batch_{uuid4().hex[:8]}",
        name=req.name,
        scenario_id=req.scenario.id,
        test_run_ids=run_ids,
        total_runs=len(tcs),
        passed_runs=passed,
        failed_runs=failed,
        inconclusive_runs=inconclusive,
        status=overall_batch_status,
    )
    return batch_repository.save(batch)

@router.get("/{batch_id}", response_model=BatchDetailResponse)
def get_batch(batch_id: str, request: Request) -> BatchDetailResponse:
    """Inspect progress, status, and partial failures of a batch evaluation."""
    batch = request.app.state.batch_repository.get(batch_id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch evaluation with id '{batch_id}' not found.",
        )
    run_statuses = []
    for rid in batch.test_run_ids:
        r = request.app.state.test_run_repository.get(rid)
        if r:
            run_statuses.append({
                "test_run_id": r.id,
                "test_case_id": r.test_case_id,
                "status": r.status.value,
                "evaluation_id": r.evaluation_id,
                "error": r.error_message,
            })
    return BatchDetailResponse(batch=batch, test_run_statuses=run_statuses)

@router.get("", response_model=List[BatchEvaluation])
def list_batches(request: Request) -> List[BatchEvaluation]:
    """List all persisted batch evaluations."""
    return request.app.state.batch_repository.list_all()
