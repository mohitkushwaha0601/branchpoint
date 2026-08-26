"""Top-level API router."""

from fastapi import APIRouter

from app.api.routes.agent_runs import router as agent_runs_router
from app.api.routes.demo import router as demo_router
from app.api.routes.demo import runs_router as demo_runs_router
from app.api.routes.harness import router as harness_router
from app.api.routes.health import router as health_router
from app.api.routes.runs import router as runs_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(runs_router)
api_router.include_router(demo_router)
api_router.include_router(demo_runs_router)
api_router.include_router(agent_runs_router)
api_router.include_router(harness_router)
