"""Phase 3 agent-run endpoints.

``POST /api/v1/agent-runs`` starts a TrueForge-backed BRANCHPOINT run and
drives it to the human approval gate. It never commits: changing reality
requires the destructive ``branchpoint_commit_recommended_world`` MCP tool,
which TrueForge pauses for explicit human approval. There is deliberately no
REST endpoint that approves or commits, so there is exactly one approval path
rather than two competing ones.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import (
    EventSinkDep,
    RunRepositoryDep,
    SessionBindingStoreDep,
    build_agent_orchestrator,
)
from app.application.orchestration.agent_run import AgentRunService
from app.core.config import ModelNotConfiguredError, Settings, get_settings
from app.domain.comparison.models import ComparisonResult
from app.domain.incidents.models import Incident, IncidentSeverity
from app.domain.primitives import new_id, utc_now
from app.domain.runs.lifecycle import RunStatus
from app.domain.worlds.models import World
from app.infrastructure.trueforge.errors import TrueForgeError

router = APIRouter(prefix="/api/v1", tags=["agent-runs"])


class StartAgentRunRequest(BaseModel):
    """Body of ``POST /api/v1/agent-runs``."""

    objective: str = Field(min_length=1, max_length=500)
    title: str = "Production incident"
    severity: IncidentSeverity = IncidentSeverity.CRITICAL
    affected_services: tuple[str, ...] = ()

    def to_incident(self) -> Incident:
        """Convert the request into a domain incident."""
        return Incident(
            incident_id=new_id("incident"),
            title=self.title,
            goal=self.objective,
            severity=self.severity,
            detected_at=utc_now(),
            affected_services=self.affected_services,
        )


class SessionBindingResponse(BaseModel):
    """One BRANCHPOINT id bound to one TrueForge session."""

    purpose: str
    trueforge_session_id: str
    world_id: str | None
    status: str
    last_turn_id: str | None
    created_at: datetime
    updated_at: datetime


class AgentRunResponse(BaseModel):
    """Status of a Phase 3 agent run."""

    run_id: str
    status: RunStatus
    recommended_world_id: str | None
    awaiting_approval: bool
    sessions: tuple[SessionBindingResponse, ...]
    detail: str


class WorldDetailResponse(BaseModel):
    """One world with its measured outcome and evidence counts."""

    world_id: str
    status: str
    verdict: str | None
    verdict_reason: str
    action_id: str
    action_name: str
    action_type: str
    goal_achieved: bool | None
    goal_attainment: float | None
    regressions_detected: int | None
    blast_radius: int | None
    cost_delta: float | None
    evidence_count: int
    counterexample_count: int
    reproduced_counterexamples: int

    @classmethod
    def from_domain(cls, world: World) -> "WorldDetailResponse":
        """Build the response from a domain world."""
        outcome = world.outcome
        return cls(
            world_id=world.world_id,
            status=str(world.status),
            verdict=str(world.verdict) if world.verdict else None,
            verdict_reason=world.verdict_reason,
            action_id=world.candidate_action.action_id,
            action_name=world.candidate_action.name,
            action_type=str(world.candidate_action.action_type),
            goal_achieved=outcome.goal_achieved if outcome else None,
            goal_attainment=outcome.goal_attainment if outcome else None,
            regressions_detected=outcome.regressions_detected if outcome else None,
            blast_radius=outcome.blast_radius if outcome else None,
            cost_delta=outcome.cost_delta if outcome else None,
            evidence_count=len(world.evidence),
            counterexample_count=len(world.counterexamples),
            reproduced_counterexamples=sum(
                1 for cx in world.counterexamples if str(cx.status) == "REPRODUCED"
            ),
        )


class WorldsResponse(BaseModel):
    """Every world in a run."""

    run_id: str
    worlds: tuple[WorldDetailResponse, ...]


class RankingResponse(BaseModel):
    """One world's place in the deterministic ordering."""

    world_id: str
    rank: int
    goal_achieved: bool
    goal_attainment: float
    regressions_detected: int
    blast_radius: int
    cost_delta: float


class RejectedWorldDetail(BaseModel):
    """A world disqualified by comparison, and why."""

    world_id: str
    reasons: tuple[str, ...]
    detail: str


class ComparisonDetailResponse(BaseModel):
    """The deterministic comparison for a run."""

    run_id: str
    recommended_world_id: str | None
    eligible_world_ids: tuple[str, ...]
    tied_world_ids: tuple[str, ...]
    rankings: tuple[RankingResponse, ...]
    rejected_worlds: tuple[RejectedWorldDetail, ...]
    summary: str

    @classmethod
    def from_domain(cls, run_id: str, comparison: ComparisonResult) -> "ComparisonDetailResponse":
        """Build the response from a domain comparison result."""
        return cls(
            run_id=run_id,
            recommended_world_id=comparison.recommended_world_id,
            eligible_world_ids=comparison.eligible_world_ids,
            tied_world_ids=comparison.tied_world_ids,
            rankings=tuple(
                RankingResponse(
                    world_id=r.world_id,
                    rank=r.rank,
                    goal_achieved=r.goal_achieved,
                    goal_attainment=r.goal_attainment,
                    regressions_detected=r.regressions_detected,
                    blast_radius=r.blast_radius,
                    cost_delta=r.cost_delta,
                )
                for r in comparison.rankings
            ),
            rejected_worlds=tuple(
                RejectedWorldDetail(
                    world_id=rejected.world_id,
                    reasons=tuple(str(reason) for reason in rejected.reasons),
                    detail=rejected.detail,
                )
                for rejected in comparison.rejected_worlds
            ),
            summary=comparison.summary,
        )


@router.post("/agent-runs", response_model=AgentRunResponse)
async def start_agent_run(
    body: StartAgentRunRequest,
    repository: RunRepositoryDep,
    events: EventSinkDep,
    bindings: SessionBindingStoreDep,
) -> AgentRunResponse:
    """Start a TrueForge-backed run and drive it to the approval gate.

    Returns once the run is awaiting human approval (or has been rejected).
    Nothing in reality has changed.
    """
    settings: Settings = get_settings()
    try:
        # Called for its check: a run must not start half-configured. The same
        # resolution runs again inside ``build_agent_orchestrator``.
        settings.resolve_model()
    except ModelNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    service = AgentRunService(
        orchestrator=build_agent_orchestrator(), events=events, bindings=bindings
    )
    try:
        run = await service.drive_to_approval(body.to_incident())
    except TrueForgeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"TrueForge failure: {exc}"
        ) from exc

    return await _agent_run_response(run.run_id, repository, bindings)


@router.get("/agent-runs/{run_id}", response_model=AgentRunResponse)
async def get_agent_run(
    run_id: str, repository: RunRepositoryDep, bindings: SessionBindingStoreDep
) -> AgentRunResponse:
    """Return a run's status together with its TrueForge session bindings."""
    return await _agent_run_response(run_id, repository, bindings)


@router.get("/runs/{run_id}/worlds", response_model=WorldsResponse)
async def get_run_worlds(run_id: str, repository: RunRepositoryDep) -> WorldsResponse:
    """Return every counterfactual world in a run with its measured outcome."""
    run = await repository.get(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"run {run_id} not found")
    return WorldsResponse(
        run_id=run_id,
        worlds=tuple(WorldDetailResponse.from_domain(world) for world in run.worlds),
    )


@router.get("/runs/{run_id}/comparison", response_model=ComparisonDetailResponse)
async def get_run_comparison(run_id: str, repository: RunRepositoryDep) -> ComparisonDetailResponse:
    """Return the deterministic comparison for a run."""
    run = await repository.get(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"run {run_id} not found")
    if run.comparison is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"run {run_id} has not been compared yet (status {run.status})",
        )
    return ComparisonDetailResponse.from_domain(run_id, run.comparison)


async def _agent_run_response(
    run_id: str, repository: RunRepositoryDep, bindings: SessionBindingStoreDep
) -> AgentRunResponse:
    run = await repository.get(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"run {run_id} not found")

    recommended = run.comparison.recommended_world_id if run.comparison else None
    awaiting = run.status is RunStatus.AWAITING_APPROVAL
    return AgentRunResponse(
        run_id=run.run_id,
        status=run.status,
        recommended_world_id=recommended,
        awaiting_approval=awaiting,
        sessions=tuple(
            SessionBindingResponse(
                purpose=str(b.purpose),
                trueforge_session_id=b.trueforge_session_id,
                world_id=b.world_id,
                status=str(b.status),
                last_turn_id=b.last_turn_id,
                created_at=b.created_at,
                updated_at=b.updated_at,
            )
            for b in await bindings.list_for_run(run_id)
        ),
        detail=(
            "awaiting human approval in TrueForge; nothing in reality has changed"
            if awaiting
            else f"run is {run.status}"
        ),
    )
