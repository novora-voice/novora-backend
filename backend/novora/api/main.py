import asyncio
import logging
import os
import signal
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional
from urllib.parse import urlsplit
from arq import create_pool
from arq.connections import RedisSettings
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from novora.api.auth import init_db, router as auth_router
from novora.api.auth_utils import DATABASE_URL
from novora.api.routes import (
    batches_router,
    integrations_router,
    payloads_router,
    providers_router,
    templates_router,
    test_runs_router,
    tool_endpoints_router,
)
from novora.api.routes.configured_agents import router as configured_agents_router
from novora.api.routes.evaluations import register_evaluation_routes
from novora.api.routes.test_runs import create_evaluation_worker
from novora.api.routes.webhooks import register_webhook_routes
from novora.adapters.repositories import (
    InMemoryConversationRepository,
    InMemoryEvaluationRepository,
    InMemoryScenarioRepository,
    InMemoryTelephonyRepository,
    InMemoryWebhookEventRepository,
)
from novora.adapters.database import (
    DatabaseSessionManager,
    SQLAlchemyConversationRepository,
    SQLAlchemyEvaluationRepository,
    SQLAlchemyIntegrationRepository,
    SQLAlchemyHttpToolEndpointRepository,
    SQLAlchemyScenarioRepository,
    SQLAlchemyTelephonyRepository,
    SQLAlchemyWebhookEventRepository,
    SQLAlchemyRecordRepository,
)
from novora.core.execution_models import (
    AgentConfig,
    BatchEvaluation,
    EvaluationJobState,
    TestCase,
    TestRun,
)
from novora.evaluation.engine import EvaluationEngine

logger = logging.getLogger(__name__)


async def _run_docker_command(*args: str) -> tuple[int, str]:
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    process = await asyncio.create_subprocess_exec(
        "docker",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        creationflags=creation_flags,
    )
    output, _ = await process.communicate()
    return process.returncode or 0, output.decode("utf-8", errors="replace").strip()


async def _start_local_redis(redis_url: str) -> None:
    parsed = urlsplit(redis_url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.username or parsed.password:
        raise RuntimeError("Redis is unreachable. Check the configured REDIS_URL and make sure its service is running.")
    port = parsed.port or 6379

    return_code, output = await _run_docker_command("start", "novora-redis")
    if return_code != 0:
        return_code, output = await _run_docker_command(
            "run", "--detach", "--name", "novora-redis", "--restart", "unless-stopped",
            "--publish", f"{port}:6379", "redis:7-alpine",
        )
    if return_code != 0:
        raise RuntimeError(
            "Could not start local Redis. Start Docker Desktop or run Redis manually. "
            f"Docker reported: {output or 'no details'}"
        )
    logger.info("Started local Redis container for the evaluation queue")


async def _connect_evaluation_redis(redis_url: str):
    redis_settings = RedisSettings.from_dsn(redis_url)
    redis = None
    try:
        redis = await create_pool(redis_settings)
        await redis.ping()
        return redis
    except Exception as first_error:
        if redis is not None:
            await redis.aclose()
        await _start_local_redis(redis_url)
        last_error: Exception = first_error
        for _ in range(30):
            await asyncio.sleep(1)
            redis = None
            try:
                redis = await create_pool(redis_settings)
                await redis.ping()
                return redis
            except Exception as exc:
                last_error = exc
                if redis is not None:
                    await redis.aclose()
        raise RuntimeError("Local Redis did not become ready within 30 seconds.") from last_error

def create_app(
    scenario_repo: Optional[InMemoryScenarioRepository] = None,
    evaluation_repo: Optional[InMemoryEvaluationRepository] = None,
    telephony_repo: Optional[InMemoryTelephonyRepository] = None,
    webhook_repo: Optional[InMemoryWebhookEventRepository] = None,
    conversation_repo: Optional[InMemoryConversationRepository] = None,
    evaluation_engine: Optional[EvaluationEngine] = None,
    elevenlabs_secret: str = "test_elevenlabs_secret",
    twilio_auth_token: str = "test_twilio_auth_token",
) -> FastAPI:
    """Factory creating and configuring the Novora FastAPI application."""
    database = DatabaseSessionManager(DATABASE_URL)
    scenarios = scenario_repo or SQLAlchemyScenarioRepository(database)
    evaluations = evaluation_repo or SQLAlchemyEvaluationRepository(database)
    telephony = telephony_repo or SQLAlchemyTelephonyRepository(database)
    webhooks = webhook_repo or SQLAlchemyWebhookEventRepository(database)
    conversations = conversation_repo or SQLAlchemyConversationRepository(database)
    if scenario_repo is None and not scenarios.list_all(limit=1):
        for scenario in InMemoryScenarioRepository(seed_defaults=True).list_all(limit=100):
            scenarios.save(scenario)
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            init_db()
        except Exception as exc:
            logger.exception("Could not initialize PostgreSQL authentication tables")
            raise RuntimeError("PostgreSQL initialization failed; the API cannot start without durable storage.") from exc

        if os.environ.get("NOVORA_DISABLE_EVALUATION_WORKER", "").lower() == "true":
            app.state.evaluation_redis = None
            logger.info("Evaluation worker startup disabled by configuration")
        else:
            redis_url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
            try:
                redis = await _connect_evaluation_redis(redis_url)
            except Exception as exc:
                logger.exception("Unable to initialize Redis for the evaluation queue")
                raise RuntimeError("Could not initialize Redis for the evaluation queue; see the startup error for details.") from exc

            worker = create_evaluation_worker(redis)
            worker_task = asyncio.create_task(worker.async_run(), name="novora-arq-worker")
            app.state.evaluation_redis = redis
            app.state.evaluation_worker = worker
            app.state.evaluation_worker_task = worker_task
            logger.info("Started embedded ARQ evaluation worker")

        try:
            yield
        finally:
            worker_task = getattr(app.state, "evaluation_worker_task", None)
            if worker_task is not None:
                app.state.evaluation_worker.handle_sig(signal.SIGTERM)
                try:
                    await worker_task
                except asyncio.CancelledError:
                    pass
                await app.state.evaluation_worker.close()
            else:
                redis = getattr(app.state, "evaluation_redis", None)
                if redis is not None:
                    await redis.aclose()

    app = FastAPI(
        title="Novora Evaluation API",
        version="0.1.0",
        description="Provider-aware voice-agent testing and evaluation platform.",
        lifespan=lifespan,
    )

     app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://novora-voice.github.io/novora-frontend", "http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Modular Routers
    app.include_router(auth_router)
    app.include_router(configured_agents_router)
    app.include_router(providers_router)
    app.include_router(integrations_router)
    app.include_router(templates_router)
    app.include_router(test_runs_router)
    app.include_router(tool_endpoints_router)
    app.include_router(batches_router)
    app.include_router(payloads_router)

    engine = evaluation_engine or EvaluationEngine()
    app.state.scenario_repository = scenarios
    app.state.evaluation_repository = evaluations
    app.state.conversation_repository = conversations
    app.state.telephony_repository = telephony
    app.state.webhook_repository = webhooks
    app.state.database_session_manager = database
    app.state.agent_repository = SQLAlchemyRecordRepository(database, "agent", AgentConfig)
    app.state.batch_repository = SQLAlchemyRecordRepository(database, "batch", BatchEvaluation)
    app.state.integration_repository = SQLAlchemyIntegrationRepository(database)
    app.state.tool_endpoint_repository = SQLAlchemyHttpToolEndpointRepository(database)
    app.state.test_case_repository = SQLAlchemyRecordRepository(database, "test_case", TestCase)
    app.state.test_run_repository = SQLAlchemyRecordRepository(database, "test_run", TestRun)
    app.state.evaluation_job_repository = SQLAlchemyRecordRepository(database, "evaluation_job", EvaluationJobState)

    @app.get("/health", tags=["Health"])
    def health_check():
        worker_task = getattr(app.state, "evaluation_worker_task", None)
        queue_ready = bool(
            getattr(app.state, "evaluation_redis", None)
            and worker_task is not None
            and not worker_task.done()
        )
        return {
            "status": "ok",
            "service": "novora-core-api",
            "evaluation_queue": "ready" if queue_ready else "unavailable",
        }

    # Register evaluation and webhook routes
    register_evaluation_routes(app, scenarios, evaluations, conversations, engine)
    register_webhook_routes(
        app, conversations, scenarios, evaluations, telephony, webhooks, engine,
        elevenlabs_secret, twilio_auth_token,
    )

    return app

# Default ASGI app instance
app = create_app()
