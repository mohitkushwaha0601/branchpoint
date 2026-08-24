"""Service health endpoint."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import APP_VERSION, SERVICE_NAME

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Deterministic service health response."""

    status: Literal["ok"] = "ok"
    service: str = SERVICE_NAME
    version: str = APP_VERSION


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report whether the API process is available."""
    return HealthResponse()
