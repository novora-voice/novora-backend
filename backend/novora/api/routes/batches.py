from typing import Any, Dict, List, Optional
from uuid import uuid4
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from novora.core.enums import OverallStatus, TestRunStatus
from novora.core.execution_models import (
    AgentConfig,
    BatchEvaluation,
    TestCase,
)
from novora.core.models import EvaluationScenario
from novora.evaluation.orchestration.pipeline import CombinedEvaluationPipeline
from novora.persistence.repositories import (
    InMemoryBatchRepository,
    InMemoryTestRunRepository,
)
from novora.scenarios.templates import get_default_test_case_for_scenario

router = APIRouter(prefix="/api/v1/batches", tags=["Batch Evaluations"])
default_batch_repo = InMemoryBatchRepository()
default_test_run_repo = InMemoryTestRunRepository()
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
def create_and_run_batch(req: BatchCreateRequest) -> BatchEvaluation:
    """Execute a batch evaluation across multiple test cases."""
    tcs = req.test_cases or [get_default_test_case_for_scenario(req.scenario.id)]
    run_ids: List[str] = []
    passed = 0
    failed = 0
    inconclusive = 0

    for tc in tcs:
        run, report, conv = pipeline.run_pipeline(
            scenario=req.scenario,
            test_case=tc,
            agent=req.agent,
            provider_config=req.provider_config,
        )
        default_test_run_repo.save(run)
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
    return default_batch_repo.save(batch)

@router.get("/{batch_id}", response_model=BatchDetailResponse)
def get_batch(batch_id: str) -> BatchDetailResponse:
    """Inspect progress, status, and partial failures of a batch evaluation."""
    batch = default_batch_repo.get(batch_id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch evaluation with id '{batch_id}' not found.",
        )
    run_statuses = []
    for rid in batch.test_run_ids:
        r = default_test_run_repo.get(rid)
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
def list_batches() -> List[BatchEvaluation]:
    """List all persisted batch evaluations."""
    return default_batch_repo.list_all()
