from novora.api.routes.batches import router as batches_router
from novora.api.routes.integrations import router as integrations_router
from novora.api.routes.payloads import router as payloads_router
from novora.api.routes.providers import router as providers_router
from novora.api.routes.templates import router as templates_router
from novora.api.routes.test_runs import router as test_runs_router
from novora.api.routes.tool_endpoints import router as tool_endpoints_router

__all__ = [
    "providers_router",
    "integrations_router",
    "templates_router",
    "test_runs_router",
    "batches_router",
    "payloads_router",
    "tool_endpoints_router",
]
