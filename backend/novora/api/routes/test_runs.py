import asyncio
import json
import logging
import random
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
from arq import func
from arq.connections import ArqRedis
from arq.worker import Retry, Worker
from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel
from redis.exceptions import RedisError
from novora.core.execution_models import (
    AgentConfig,
    EvaluationJobState,
    ScriptedTurn,
    TestCase,
    TestRun,
)
from novora.core.models import EvaluationReport, EvaluationScenario
from novora.adapters.database import (
    SQLAlchemyConversationRepository,
    SQLAlchemyEvaluationRepository,
    SQLAlchemyIntegrationRepository,
    SQLAlchemyRecordRepository,
    SQLAlchemyScenarioRepository,
    get_database_session_manager,
)
from novora.api.auth_utils import DATABASE_URL
from novora.evaluation.orchestration.pipeline import CombinedEvaluationPipeline
from novora.scenarios.templates import get_default_test_case_for_scenario

router = APIRouter(prefix="/api/v1/test-runs", tags=["Test Execution & Ghost Caller"])
logger = logging.getLogger(__name__)
pipeline = CombinedEvaluationPipeline()
MAX_EVALUATION_RETRIES = 10
MAX_EVALUATION_TRIES = MAX_EVALUATION_RETRIES + 1
EVALUATION_JOB_TIMEOUT_SECONDS = 600
EVALUATION_EXECUTION_TIMEOUT_SECONDS = EVALUATION_JOB_TIMEOUT_SECONDS - 30


class NonRetryableEvaluationError(RuntimeError):
    """An evaluation error that the provider explicitly says must not be retried."""

    def __init__(
        self,
        message: str,
        *,
        test_run: Optional[TestRun] = None,
        evaluation_report: Optional[EvaluationReport] = None,
    ) -> None:
        super().__init__(message)
        self.test_run = test_run
        self.evaluation_report = evaluation_report


def _is_provider_owner_action_error(message: str) -> bool:
    body_start = message.find("{")
    if body_start < 0:
        return False
    try:
        detail = json.loads(message[body_start:])
    except json.JSONDecodeError:
        return False
    return (
        isinstance(detail, dict)
        and detail.get("cloudflare_error") is True
        and detail.get("retryable") is False
        and detail.get("owner_action_required") is True
    )


def _vapi_blocked_summary(error_message: str) -> str:
    body_start = error_message.find("{")
    ray_id = None
    if body_start >= 0:
        try:
            detail = json.loads(error_message[body_start:])
        except json.JSONDecodeError:
            detail = {}
        if isinstance(detail, dict):
            ray_id = detail.get("ray_id")
    ray_reference = f" Contact Vapi support with Cloudflare Ray ID {ray_id}." if ray_id else " Contact Vapi support with the Cloudflare error details."
    return (
        "Vapi API access was blocked by Cloudflare Error 1010 before the agent session started. "
        "Agent behavior and agent-side blockers were not evaluated."
        f"{ray_reference}"
    )


def _evaluation_job_repository() -> SQLAlchemyRecordRepository[EvaluationJobState]:
    database = get_database_session_manager(DATABASE_URL)
    return SQLAlchemyRecordRepository(database, "evaluation_job", EvaluationJobState)


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


class EvaluationJobResponse(BaseModel):
    job_id: str
    status: str
    attempt: int = 0
    error: Optional[str] = None
    test_run: Optional[TestRun] = None
    evaluation_report: Optional[EvaluationReport] = None


def _build_test_case(req: TestRunExecutionRequest) -> TestCase:
    if req.test_case:
        return req.test_case
    if req.scripted_turns:
        return TestCase(
            scenario_id=req.scenario.id,
            name=f"Custom Test: {req.scenario.name}",
            description=req.user_instructions or "User-defined scripted turns",
            scripted_turns=req.scripted_turns,
        )
    if req.user_instructions and req.user_instructions.strip():
        return TestCase(
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
    return get_default_test_case_for_scenario(req.scenario.id)


def _execute_test_run(
    req: TestRunExecutionRequest,
    *,
    scenario_repository: Any = None,
    agent_repository: Any = None,
    integration_repository: Any = None,
    test_case_repository: Any = None,
    test_run_repository: Any = None,
    evaluation_repository: Any = None,
    conversation_repository: Any = None,
) -> TestRunResponse:
    database = get_database_session_manager(DATABASE_URL)
    scenario_repository = scenario_repository or SQLAlchemyScenarioRepository(database)
    agent_repository = agent_repository or SQLAlchemyRecordRepository(database, "agent", AgentConfig)
    integration_repository = integration_repository or SQLAlchemyIntegrationRepository(database)
    test_case_repository = test_case_repository or SQLAlchemyRecordRepository(database, "test_case", TestCase)
    test_run_repository = test_run_repository or SQLAlchemyRecordRepository(database, "test_run", TestRun)
    evaluation_repository = evaluation_repository or SQLAlchemyEvaluationRepository(database)
    conversation_repository = conversation_repository or SQLAlchemyConversationRepository(database)

    agent_id = (req.agent.external_agent_id or "").strip()
    if not agent_id:
        raise ValueError("An agent ID is required before running an evaluation.")

    tc = _build_test_case(req)
    scenario_repository.save(req.scenario)
    agent_repository.save(req.agent)
    test_case_repository.save(tc)
    provider_config = dict(req.provider_config)
    # Credentials always come from backend configuration, never from browser input.
    provider_config.pop("api_key", None)
    provider_config.pop("elevenlabs_tts_api_key", None)
    provider_config.pop("elevenlabs_tts_voice_id", None)
    if not provider_config.get("api_key"):
        provider = req.agent.provider_name.lower()
        env_keys = {
            "elevenlabs": "ELEVENLABS_API_KEY",
            "assemblyai": "ASSEMBLYAI_API_KEY",
            "vapi": "VAPI_API_KEY",
            "retell": "RETELL_API_KEY",
        }
        env_name = env_keys.get(provider)
        api_key = os.getenv(env_name) if env_name else None
        if not api_key:
            integration = integration_repository.get_by_provider(provider)
            if integration:
                api_key = integration.metadata.get("raw_key")
        if not api_key:
            raise ValueError(f"No {provider} API key is configured. Set {env_name} in the backend environment or connect the provider integration.")
        provider_config["api_key"] = api_key

    run, report, _conv = pipeline.run_pipeline(
        scenario=req.scenario,
        test_case=tc,
        agent=req.agent,
        provider_config=provider_config,
        enable_llm_judge=req.enable_llm_judge,
    )
    if run.status.value == "failed":
        error_message = run.error_message or f"{req.agent.provider_name} provider execution failed."
        if _is_provider_owner_action_error(error_message):
            report.agent_id = agent_id
            report.agent_name = req.agent.name.strip()
            if req.agent.provider_name.lower() == "vapi":
                report.summary = _vapi_blocked_summary(error_message)
            conversation_repository.save(_conv)
            evaluation_repository.save(report)
            test_run_repository.save(run)
            raise NonRetryableEvaluationError(
                error_message,
                test_run=run,
                evaluation_report=report,
            )
        raise RuntimeError(error_message)
    report.agent_id = agent_id
    report.agent_name = req.agent.name.strip()
    conversation_repository.save(_conv)
    evaluation_repository.save(report)
    test_run_repository.save(run)
    return TestRunResponse(test_run=run, evaluation_report=report)


async def execute_test_run_job(
    ctx: Dict[str, Any],
    job_id: str,
    request_data: Dict[str, Any],
) -> Dict[str, Any]:
    attempt = int(ctx.get("job_try", 1))
    jobs = _evaluation_job_repository()
    state = jobs.get(job_id)
    if state is None:
        raise RuntimeError(f"Evaluation job '{job_id}' is missing its PostgreSQL record.")
    state = state.model_copy(update={
        "status": "running",
        "attempt": attempt,
        "error": None,
        "updated_at": datetime.now(timezone.utc),
    })
    jobs.save(state)

    try:
        req = TestRunExecutionRequest.model_validate(request_data)
        result = await asyncio.wait_for(
            asyncio.to_thread(_execute_test_run, req),
            timeout=EVALUATION_EXECUTION_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        if isinstance(exc, NonRetryableEvaluationError):
            jobs.save(state.model_copy(update={
                "status": "failed",
                "attempt": attempt,
                "error": error,
                "test_run": exc.test_run,
                "evaluation_report": exc.evaluation_report,
                "updated_at": datetime.now(timezone.utc),
            }))
            logger.error("Evaluation job %s stopped without retry: %s", job_id, error)
            return {"job_id": job_id, "status": "failed", "error": error}
        if attempt <= MAX_EVALUATION_RETRIES:
            delay = random.uniform(5, 10)
            jobs.save(state.model_copy(update={
                "status": "retrying",
                "attempt": attempt,
                "error": error,
                "updated_at": datetime.now(timezone.utc),
            }))
            logger.warning(
                "Evaluation job %s failed on attempt %s; retrying in %.2f seconds: %s",
                job_id,
                attempt,
                delay,
                error,
            )
            raise Retry(defer=delay) from exc

        jobs.save(state.model_copy(update={
            "status": "failed",
            "attempt": attempt,
            "error": error,
            "updated_at": datetime.now(timezone.utc),
        }))
        logger.exception("Evaluation job %s failed after %s attempts", job_id, attempt)
        raise

    state = state.model_copy(update={
        "status": "completed",
        "attempt": attempt,
        "error": None,
        "test_run": result.test_run,
        "evaluation_report": result.evaluation_report,
        "updated_at": datetime.now(timezone.utc),
    })
    jobs.save(state)
    result_data = result.model_dump(mode="json")
    return result_data


def create_evaluation_worker(redis: ArqRedis) -> Worker:
    return Worker(
        functions=[
            func(
                execute_test_run_job,
                timeout=EVALUATION_JOB_TIMEOUT_SECONDS,
                max_tries=MAX_EVALUATION_TRIES,
            )
        ],
        redis_pool=redis,
        max_jobs=2,
        max_tries=MAX_EVALUATION_TRIES,
        job_timeout=EVALUATION_JOB_TIMEOUT_SECONDS,
        keep_result=0,
        retry_jobs=True,
    )


@router.post("", response_model=TestRunResponse, status_code=status.HTTP_201_CREATED)
def execute_test_run(req: TestRunExecutionRequest, request: Request) -> TestRunResponse:
    """Execute a ghost-caller test conversation and run deterministic + LLM evaluations."""
    agent_id = (req.agent.external_agent_id or "").strip()
    if not agent_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "AGENT_ID_REQUIRED", "message": "An agent ID is required before running an evaluation."},
        )

    return _execute_test_run(
        req,
        scenario_repository=request.app.state.scenario_repository,
        agent_repository=request.app.state.agent_repository,
        integration_repository=request.app.state.integration_repository,
        test_case_repository=request.app.state.test_case_repository,
        test_run_repository=request.app.state.test_run_repository,
        evaluation_repository=request.app.state.evaluation_repository,
        conversation_repository=request.app.state.conversation_repository,
    )


@router.post("/jobs", response_model=EvaluationJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_test_run(req: TestRunExecutionRequest, request: Request) -> EvaluationJobResponse:
    agent_id = (req.agent.external_agent_id or "").strip()
    if not agent_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "AGENT_ID_REQUIRED", "message": "An agent ID is required before running an evaluation."},
        )

    redis: Optional[ArqRedis] = getattr(request.app.state, "evaluation_redis", None)
    worker_task = getattr(request.app.state, "evaluation_worker_task", None)
    if redis is None or worker_task is None or worker_task.done():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Evaluation queue worker is unavailable. Check Redis and backend startup logs, then restart the backend.",
        )

    request.app.state.scenario_repository.save(req.scenario)
    job_id = f"evaljob_{uuid4().hex}"
    request_data = req.model_dump(mode="json")
    request_data.get("provider_config", {}).pop("api_key", None)
    request_data.get("provider_config", {}).pop("elevenlabs_tts_api_key", None)
    request_data.get("provider_config", {}).pop("elevenlabs_tts_voice_id", None)
    jobs = request.app.state.evaluation_job_repository
    jobs.save(EvaluationJobState(
        id=job_id,
        status="queued",
        request_data=request_data,
    ))
    try:
        await redis.enqueue_job(
            "execute_test_run_job",
            job_id,
            request_data,
            _job_id=job_id,
        )
    except RedisError as exc:
        logger.exception("Could not enqueue evaluation job %s", job_id)
        jobs.save(EvaluationJobState(
            id=job_id,
            status="failed",
            attempt=0,
            error="Could not enqueue the evaluation job.",
            request_data=request_data,
        ))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not submit the evaluation to Redis. Check the backend Redis connection and try again.",
        ) from exc
    return EvaluationJobResponse(job_id=job_id, status="queued")


@router.get("/jobs/{job_id}", response_model=EvaluationJobResponse)
def get_evaluation_job(job_id: str, request: Request) -> EvaluationJobResponse:
    job = request.app.state.evaluation_job_repository.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation job not found.")
    return EvaluationJobResponse(
        job_id=job.id,
        status=job.status,
        attempt=job.attempt,
        error=job.error,
        test_run=job.test_run,
        evaluation_report=job.evaluation_report,
    )


@router.get("/{run_id}", response_model=TestRun)
def get_test_run(run_id: str, request: Request) -> TestRun:
    """Retrieve details, normalized events, and tool calls for a test run."""
    run = request.app.state.test_run_repository.get(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test run with id '{run_id}' not found.",
        )
    return run


@router.get("", response_model=List[TestRun])
def list_test_runs(
    request: Request,
    scenario_id: Optional[str] = Query(None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> List[TestRun]:
    """List historical test runs with pagination and scenario filtering."""
    if scenario_id:
        return request.app.state.test_run_repository.list_by_scenario(scenario_id, limit=limit, offset=offset)
    return request.app.state.test_run_repository.list_all(limit=limit, offset=offset)
