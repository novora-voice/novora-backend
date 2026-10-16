from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from novora.core.execution_models import (
    AgentConfig,
    ScriptedTurn,
    TestCase,
    TestRun,
)
from novora.core.models import EvaluationReport, EvaluationScenario
from novora.evaluation.orchestration.pipeline import CombinedEvaluationPipeline
from novora.persistence.repositories import (
    InMemoryTestCaseRepository,
    InMemoryTestRunRepository,
)
from novora.scenarios.templates import get_default_test_case_for_scenario

router = APIRouter(prefix="/api/v1/test-runs", tags=["Test Execution & Ghost Caller"])
default_test_run_repo = InMemoryTestRunRepository()
default_test_case_repo = InMemoryTestCaseRepository()
pipeline = CombinedEvaluationPipeline()


class TestRunExecutionRequest(BaseModel):
    scenario: EvaluationScenario
    test_case: Optional[TestCase] = None
    agent: AgentConfig
    provider_config: Dict[str, Any] = {}
    enable_llm_judge: bool = True
    # User-defined test instructions in plain English
    user_instructions: Optional[str] = None
    # Custom scripted turns override
    scripted_turns: Optional[List[ScriptedTurn]] = None


class TestRunResponse(BaseModel):
    test_run: TestRun
    evaluation_report: Optional[EvaluationReport] = None


@router.post("", response_model=TestRunResponse, status_code=status.HTTP_201_CREATED)
def execute_test_run(req: TestRunExecutionRequest) -> TestRunResponse:
    """Execute a ghost-caller test conversation and run deterministic + LLM evaluations."""
    # Validate agent ID is present — must not be empty or a placeholder
    agent_id = (req.agent.external_agent_id or "").strip()
    if not agent_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "AGENT_ID_REQUIRED", "message": "An agent ID is required before running an evaluation."},
        )

    # Build test case: explicit > scripted turns > plain-English instructions > default template
    if req.test_case:
        tc = req.test_case
    elif req.scripted_turns:
        tc = TestCase(
            scenario_id=req.scenario.id,
            name=f"Custom Test: {req.scenario.name}",
            description=req.user_instructions or "User-defined scripted turns",
            scripted_turns=req.scripted_turns,
        )
    elif req.user_instructions and req.user_instructions.strip():
        tc = TestCase(
            scenario_id=req.scenario.id,
            name=f"Instruction-Based Test: {req.scenario.name}",
            description=req.user_instructions,
            scripted_turns=[
                ScriptedTurn(
                    sequence=1,
                    user_message=req.user_instructions.strip(),
                    expected_response_keywords=[],
                ),
            ],
        )
    else:
        tc = get_default_test_case_for_scenario(req.scenario.id)

    default_test_case_repo.save(tc)

    run, report, _conv = pipeline.run_pipeline(
        scenario=req.scenario,
        test_case=tc,
        agent=req.agent,
        provider_config=req.provider_config,
        enable_llm_judge=req.enable_llm_judge,
    )
    default_test_run_repo.save(run)
    return TestRunResponse(test_run=run, evaluation_report=report)


@router.get("/{run_id}", response_model=TestRun)
def get_test_run(run_id: str) -> TestRun:
    """Retrieve details, normalized events, and tool calls for a test run."""
    run = default_test_run_repo.get(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test run with id '{run_id}' not found.",
        )
    return run


@router.get("", response_model=List[TestRun])
def list_test_runs(
    scenario_id: Optional[str] = Query(None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> List[TestRun]:
    """List historical test runs with pagination and scenario filtering."""
    if scenario_id:
        return default_test_run_repo.list_by_scenario(scenario_id)
    return default_test_run_repo.list_all(limit=limit, offset=offset)
