"""Demo production endpoints: read-only state, deterministic reset, capability
issuance, and driving a run through the Phase 2 demo adapters.

These are demo/hackathon-facing surfaces layered on top of the Phase 1
orchestrator and the Phase 2 demo engine — never a substitute for either.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.dependencies import DemoOrchestratorDep, RunRepositoryDep
from app.application.errors import RunNotFoundError
from app.core.config import Settings, get_settings
from app.domain.errors import DomainError
from app.domain.runs.lifecycle import RunStatus
from app.infrastructure.demo.capability import CapabilityError
from app.infrastructure.demo.dependencies import get_capability_store, get_demo_engine
from app.infrastructure.demo.engine import DemoProductionEngine
from app.infrastructure.demo.metrics import MetricsSnapshot, compute_metrics
from app.infrastructure.demo.state import DemoProductionState

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])
runs_router = APIRouter(prefix="/api/v1/runs", tags=["runs", "demo"])


def _require_non_production(settings: Settings) -> None:
    """Reject a request outright when running with ``BRANCHPOINT_ENV=production``."""
    if settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="demo endpoints are not available in production",
        )


class DeploymentResponse(BaseModel):
    """The deployed pricing-service version, safe for external display."""

    service: str
    version: str
    previous_version: str | None
    deployed_at: datetime


class FeatureFlagResponse(BaseModel):
    """A demo feature flag."""

    key: str
    enabled: bool
    service: str


class CapacityResponse(BaseModel):
    """Replica count and cost for a demo service."""

    service: str
    replicas: int
    daily_infra_cost_usd: float


class MetricsResponse(BaseModel):
    """Every derived headline metric."""

    regression_active: bool
    checkout_error_rate: float
    checkout_p95_ms: float
    pricing_timeout_rate: float
    affected_users: int
    database_latency_ms: float
    checkout_cpu_utilization: float
    pricing_cpu_utilization: float
    daily_infra_cost_usd: float

    @classmethod
    def from_domain(cls, metrics: MetricsSnapshot) -> "MetricsResponse":
        """Build the response from a computed metrics snapshot."""
        return cls(**metrics.model_dump())


class OrdersSummaryResponse(BaseModel):
    """Aggregate order counts. Never exposes raw order records or payment data."""

    total_orders: int
    orders_schema_version: int
    orders_with_payment_revision: int


class DemoStateResponse(BaseModel):
    """Everything about current demo reality that is safe to expose externally.

    Never includes capability tokens, hashes, or raw order records — only
    aggregate, derived values.
    """

    deployment: DeploymentResponse
    feature_flag: FeatureFlagResponse
    capacity: CapacityResponse
    metrics: MetricsResponse
    orders: OrdersSummaryResponse
    snapshot_at: datetime

    @classmethod
    def from_domain(cls, state: DemoProductionState) -> "DemoStateResponse":
        """Build the response from a demo production state snapshot."""
        metrics = compute_metrics(state)
        return cls(
            deployment=DeploymentResponse(
                service=state.pricing_deployment.service,
                version=state.pricing_deployment.version,
                previous_version=state.pricing_deployment.previous_version,
                deployed_at=state.pricing_deployment.deployed_at,
            ),
            feature_flag=FeatureFlagResponse(
                key=state.pricing_flag.key,
                enabled=state.pricing_flag.enabled,
                service=state.pricing_flag.service,
            ),
            capacity=CapacityResponse(
                service=state.pricing_capacity.service,
                replicas=state.pricing_capacity.replicas,
                daily_infra_cost_usd=metrics.daily_infra_cost_usd,
            ),
            metrics=MetricsResponse.from_domain(metrics),
            orders=OrdersSummaryResponse(
                total_orders=len(state.orders),
                orders_schema_version=state.orders_schema_version,
                orders_with_payment_revision=sum(
                    1 for order in state.orders if order.payment_revision is not None
                ),
            ),
            snapshot_at=state.snapshot_at,
        )


class CommitCapabilityResponse(BaseModel):
    """A freshly issued one-time commit capability. The token is shown exactly once."""

    capability_id: str
    token: str
    run_id: str
    world_id: str
    action_id: str
    expires_at: datetime | None


@router.get("/state", response_model=DemoStateResponse)
async def get_demo_state(
    engine: DemoProductionEngine = Depends(get_demo_engine),
) -> DemoStateResponse:
    """Return the current demo production state and its derived metrics."""
    state = await engine.reality()
    return DemoStateResponse.from_domain(state)


@router.post("/reset", response_model=DemoStateResponse)
async def reset_demo_state(
    settings: Settings = Depends(get_settings),
    engine: DemoProductionEngine = Depends(get_demo_engine),
) -> DemoStateResponse:
    """Restore demo reality to the exact initial incident.

    Unavailable when ``BRANCHPOINT_ENV=production``.
    """
    _require_non_production(settings)
    state = await engine.reset()
    return DemoStateResponse.from_domain(state)


@runs_router.post(
    "/{run_id}/execute-demo-worlds", response_model=None, status_code=status.HTTP_200_OK
)
async def execute_demo_worlds(run_id: str, orchestrator: DemoOrchestratorDep) -> dict[str, str]:
    """Drive an existing run through observe -> plan -> fork -> execute -> attack ->
    compare -> request_approval using the deterministic Phase 2 demo adapters.

    The run must already exist (created via ``POST /api/v1/runs``). This does
    not create a new run, and it never commits — approval remains a distinct,
    explicit step.
    """
    try:
        run = await orchestrator.observe(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    try:
        run = await orchestrator.plan(run.run_id)
        if not run.is_terminal:
            run = await orchestrator.fork(run.run_id)
            run = await orchestrator.execute_worlds(run.run_id)
            run = await orchestrator.run_adversarial_tests(run.run_id)
            run = await orchestrator.compare(run.run_id)
            run = await orchestrator.request_approval(run.run_id)
    except DomainError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"run_id": run.run_id, "status": str(run.status)}


@runs_router.post("/{run_id}/commit-capability", response_model=CommitCapabilityResponse)
async def issue_commit_capability(
    run_id: str, repository: RunRepositoryDep
) -> CommitCapabilityResponse:
    """Issue a one-time capability authorizing exactly the world/action a granted
    BRANCHPOINT approval selected.

    The raw token is returned exactly once, here. It is never logged, never
    stored in plaintext, and cannot be recovered afterward — only reissued
    (which invalidates nothing already issued, since each token is
    independently single-use).
    """
    run = await repository.get(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"run {run_id} not found")
    if run.status is not RunStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"run {run_id} is {run.status}, expected {RunStatus.APPROVED}",
        )

    store = get_capability_store()
    try:
        issued = await store.issue_for_approved_run(run)
    except (DomainError, CapabilityError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return CommitCapabilityResponse(
        capability_id=issued.capability.capability_id,
        token=issued.token,
        run_id=issued.capability.run_id,
        world_id=issued.capability.world_id,
        action_id=issued.capability.action_id,
        expires_at=issued.capability.expires_at,
    )
