"""Run inspection endpoints.

Phase 1 exposes creating and reading runs plus their event timeline. Steps that
would mutate reality are deliberately absent until their adapters exist.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import EventSinkDep, OrchestratorDep, RunRepositoryDep
from app.domain.commits.models import CommitStatus
from app.domain.events import RunEvent, RunEventType
from app.domain.incidents.models import Incident, IncidentSeverity
from app.domain.primitives import new_id, utc_now
from app.domain.runs.lifecycle import RunStatus
from app.domain.runs.models import BranchpointRun
from app.domain.verification.models import VerificationStatus
from app.domain.worlds.lifecycle import WorldStatus
from app.domain.worlds.models import World, WorldVerdict

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


class IncidentRequest(BaseModel):
    """The condition a caller wants BRANCHPOINT to reason about."""

    title: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    severity: IncidentSeverity
    description: str = ""
    detected_at: datetime | None = None
    affected_services: tuple[str, ...] = ()
    metadata: dict[str, str] = Field(default_factory=dict)

    def to_domain(self) -> Incident:
        """Convert the request into a domain incident."""
        return Incident(
            incident_id=new_id("incident"),
            title=self.title,
            goal=self.goal,
            severity=self.severity,
            detected_at=self.detected_at or utc_now(),
            description=self.description,
            affected_services=self.affected_services,
            metadata=dict(self.metadata),
        )


class CreateRunRequest(BaseModel):
    """Body of ``POST /api/v1/runs``."""

    incident: IncidentRequest


class IncidentResponse(BaseModel):
    """Incident as returned over HTTP."""

    incident_id: str
    title: str
    goal: str
    severity: IncidentSeverity
    detected_at: datetime
    description: str
    affected_services: tuple[str, ...]

    @classmethod
    def from_domain(cls, incident: Incident) -> "IncidentResponse":
        """Build the response from a domain incident."""
        return cls(
            incident_id=incident.incident_id,
            title=incident.title,
            goal=incident.goal,
            severity=incident.severity,
            detected_at=incident.detected_at,
            description=incident.description,
            affected_services=incident.affected_services,
        )


class WorldResponse(BaseModel):
    """One counterfactual world as returned over HTTP."""

    world_id: str
    status: WorldStatus
    action_id: str
    action_name: str
    verdict: WorldVerdict | None
    verdict_reason: str
    evidence_count: int
    counterexample_count: int

    @classmethod
    def from_domain(cls, world: World) -> "WorldResponse":
        """Build the response from a domain world."""
        return cls(
            world_id=world.world_id,
            status=world.status,
            action_id=world.candidate_action.action_id,
            action_name=world.candidate_action.name,
            verdict=world.verdict,
            verdict_reason=world.verdict_reason,
            evidence_count=len(world.evidence),
            counterexample_count=len(world.counterexamples),
        )


class RejectedWorldResponse(BaseModel):
    """A world disqualified by deterministic comparison."""

    world_id: str
    reasons: tuple[str, ...]
    detail: str


class ComparisonResponse(BaseModel):
    """Deterministic comparison outcome."""

    recommended_world_id: str | None
    eligible_world_ids: tuple[str, ...]
    tied_world_ids: tuple[str, ...]
    rejected_worlds: tuple[RejectedWorldResponse, ...]
    summary: str


class ApprovalResponse(BaseModel):
    """Approval state for a run."""

    approval_id: str
    status: str
    selected_world_id: str
    action_id: str
    action_fingerprint: str
    requested_at: datetime
    decided_at: datetime | None
    actor: str | None
    reason: str


class RunResponse(BaseModel):
    """A run and everything decided about it so far."""

    run_id: str
    status: RunStatus
    incident: IncidentResponse
    created_at: datetime
    updated_at: datetime
    candidate_action_ids: tuple[str, ...]
    worlds: tuple[WorldResponse, ...]
    comparison: ComparisonResponse | None
    approval: ApprovalResponse | None
    selected_world_id: str | None
    commit_id: str | None
    commit_status: CommitStatus | None
    verification_status: VerificationStatus | None
    failure_reason: str

    @classmethod
    def from_domain(cls, run: BranchpointRun) -> "RunResponse":
        """Build the response from a domain run."""
        comparison = None
        if run.comparison is not None:
            comparison = ComparisonResponse(
                recommended_world_id=run.comparison.recommended_world_id,
                eligible_world_ids=run.comparison.eligible_world_ids,
                tied_world_ids=run.comparison.tied_world_ids,
                rejected_worlds=tuple(
                    RejectedWorldResponse(
                        world_id=rejected.world_id,
                        reasons=tuple(str(reason) for reason in rejected.reasons),
                        detail=rejected.detail,
                    )
                    for rejected in run.comparison.rejected_worlds
                ),
                summary=run.comparison.summary,
            )

        approval = None
        if run.approval is not None:
            approval = ApprovalResponse(
                approval_id=run.approval.approval_id,
                status=str(run.approval.status),
                selected_world_id=run.approval.selected_world_id,
                action_id=run.approval.action_id,
                action_fingerprint=run.approval.action_fingerprint,
                requested_at=run.approval.requested_at,
                decided_at=run.approval.decided_at,
                actor=run.approval.actor,
                reason=run.approval.reason,
            )

        return cls(
            run_id=run.run_id,
            status=run.status,
            incident=IncidentResponse.from_domain(run.incident),
            created_at=run.created_at,
            updated_at=run.updated_at,
            candidate_action_ids=tuple(action.action_id for action in run.candidate_actions),
            worlds=tuple(WorldResponse.from_domain(world) for world in run.worlds),
            comparison=comparison,
            approval=approval,
            selected_world_id=run.selected_world_id,
            commit_id=run.commit_receipt.commit_id if run.commit_receipt else None,
            commit_status=run.commit_receipt.status if run.commit_receipt else None,
            verification_status=run.verification.status if run.verification else None,
            failure_reason=run.failure_reason,
        )


class RunListResponse(BaseModel):
    """Every stored run, newest first."""

    runs: tuple[RunResponse, ...]


class EventResponse(BaseModel):
    """One entry of a run's timeline."""

    event_id: str
    run_id: str
    world_id: str | None
    event_type: RunEventType
    summary: str
    occurred_at: datetime

    @classmethod
    def from_domain(cls, event: RunEvent) -> "EventResponse":
        """Build the response from a domain event."""
        return cls(
            event_id=event.event_id,
            run_id=event.run_id,
            world_id=event.world_id,
            event_type=event.event_type,
            summary=event.summary,
            occurred_at=event.occurred_at,
        )


class EventListResponse(BaseModel):
    """A run's timeline in arrival order."""

    events: tuple[EventResponse, ...]


@router.post("", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(body: CreateRunRequest, orchestrator: OrchestratorDep) -> RunResponse:
    """Open a run for an incident."""
    run = await orchestrator.create_run(body.incident.to_domain())
    return RunResponse.from_domain(run)


@router.get("", response_model=RunListResponse)
async def list_runs(repository: RunRepositoryDep) -> RunListResponse:
    """List every stored run, newest first."""
    runs = await repository.list_runs()
    return RunListResponse(runs=tuple(RunResponse.from_domain(run) for run in runs))


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, repository: RunRepositoryDep) -> RunResponse:
    """Return one run."""
    run = await repository.get(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"run {run_id} not found")
    return RunResponse.from_domain(run)


@router.get("/{run_id}/events", response_model=EventListResponse)
async def get_run_events(
    run_id: str, repository: RunRepositoryDep, events: EventSinkDep
) -> EventListResponse:
    """Return the timeline for one run."""
    if await repository.get(run_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"run {run_id} not found")
    timeline = await events.events_for(run_id)
    return EventListResponse(events=tuple(EventResponse.from_domain(event) for event in timeline))
