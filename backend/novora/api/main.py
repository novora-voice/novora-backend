from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from novora.api.auth import init_db, router as auth_router
from novora.api.routes import (
    batches_router,
    integrations_router,
    payloads_router,
    providers_router,
    templates_router,
    test_runs_router,
)
from novora.api.routes.evaluations import register_evaluation_routes
from novora.api.routes.webhooks import register_webhook_routes
from novora.adapters.repositories import (
    InMemoryConversationRepository,
    InMemoryEvaluationRepository,
    InMemoryScenarioRepository,
    InMemoryTelephonyRepository,
    InMemoryWebhookEventRepository,
)
from novora.evaluation.engine import EvaluationEngine

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
    app = FastAPI(
        title="Novora Evaluation API",
        version="0.1.0",
        description="Provider-aware voice-agent testing and evaluation platform.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Modular Routers
    app.include_router(auth_router)
    app.include_router(providers_router)
    app.include_router(integrations_router)
    app.include_router(templates_router)
    app.include_router(test_runs_router)
    app.include_router(batches_router)
    app.include_router(payloads_router)

    # Initialise DB tables on startup
    @app.on_event("startup")
    def _startup():
        try:
            init_db()
        except Exception as exc:
            import warnings
            warnings.warn(f"[Novora] Database init warning: {exc}", RuntimeWarning, stacklevel=1)

    scenarios = scenario_repo or InMemoryScenarioRepository(seed_defaults=True)
    evaluations = evaluation_repo or InMemoryEvaluationRepository()
    telephony = telephony_repo or InMemoryTelephonyRepository()
    webhooks = webhook_repo or InMemoryWebhookEventRepository()
    conversations = conversation_repo or InMemoryConversationRepository()
    engine = evaluation_engine or EvaluationEngine()

    @app.get("/health", tags=["Health"])
    def health_check():
        return {"status": "ok", "service": "novora-core-api"}

    # Register evaluation and webhook routes
    register_evaluation_routes(app, scenarios, evaluations, conversations, engine)
    register_webhook_routes(
        app, conversations, scenarios, evaluations, telephony, webhooks, engine,
        elevenlabs_secret, twilio_auth_token,
    )

    return app

# Default ASGI app instance
app = create_app()
