"""Phase 3 agent-run endpoints.

``POST /api/v1/agent-runs`` starts a TrueForge-backed BRANCHPOINT run and
drives it to the human approval gate. It never commits.

``POST /api/v1/runs/{run_id}/approval`` is where a human says yes. That one
endpoint is the *only* place a commit can be authorized, and it carries no
action content: the caller cannot name an action, only confirm the one
BRANCHPOINT already recommended and bound. Approving there drives the commit
through the sanctioned destructive path — the
``branchpoint_commit_recommended_world`` MCP tool, invoked by a TrueForge
commit operator whose tool call BRANCHPOINT resumes on behalf of the approval
it already holds — and then through independent verification.
"""

from datetime import datetime
from enum import StrEnum

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import (
    BackgroundRunnerDep,
    EventSinkDep,
    RunRepositoryDep,
    SessionBindingStoreDep,
    build_agent_orchestrator,
    build_approval_coordinator,
)
from app.application.errors import RunNotFoundError
from app.application.orchestration.agent_run import AgentRunService
from app.application.orchestration.approval import (
    ApprovalMismatchError,
    ApprovalNotAvailableError,
    CommitFailedError,
)
from app.core.config import ModelNotConfiguredError, Settings, get_settings
from app.domain.comparison.models import ComparisonResult
from app.domain.evidence.models import Evidence, EvidenceKind, EvidenceSeverity
from app.domain.incidents.models import Incident, IncidentSeverity
from app.domain.primitives import ScalarValue, new_id, utc_now
from app.domain.runs.lifecycle import RunStatus
from app.domain.worlds.models import Counterexample, CounterexampleStatus, World
from app.domain.worlds.verdicts import (
    counterexample_vetoes,
    disqualifying_evidence,
    vetoing_counterexamples,
)
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


class ApproveRunRequest(BaseModel):
    """Body of ``POST /api/v1/runs/{run_id}/approval``.

    Carries **no action content**. ``expected_*`` are optional confirmations of
    what the human believes they are approving; a value that disagrees with the
    bound approval is a conflict, never an instruction to commit something else.
    """

    actor: str = Field(min_length=1, max_length=200)
    expected_world_id: str | None = None
    expected_action_id: str | None = None
    expected_action_fingerprint: str | None = None


class RejectRunRequest(BaseModel):
    """Body of ``POST /api/v1/runs/{run_id}/rejection``.

    Carries no action content, exactly like the approval body: a human declines
    what BRANCHPOINT recommended, and cannot name something else to decline.
    """

    actor: str = Field(min_length=1, max_length=200)
    reason: str = Field(default="", max_length=500)


class HumanDecisionResponse(BaseModel):
    """What the frontend needs after a human refuses the recommendation."""

    run_id: str
    world_id: str
    approval_status: str
    run_status: RunStatus
    actor: str | None
    reason: str
    decided_at: datetime | None
    #: Always ``False`` here. Stated rather than implied so a client never has
    #: to infer from a status enum whether a commit is still on the table.
    commit_possible: bool
    detail: str


class AcceptedRunResponse(BaseModel):
    """What ``POST /api/v1/agent-runs`` returns, before any agent work happens.

    Carries the id of the run the background drive will operate on — the same
    run, never a copy — so a client can navigate to it and start watching the
    timeline immediately.
    """

    run_id: str
    status: RunStatus
    detail: str


class ApprovalDecisionResponse(BaseModel):
    """What the frontend needs after submitting a human approval."""

    run_id: str
    world_id: str
    action_id: str
    action_name: str
    approval_status: str
    run_status: RunStatus
    commit_status: str | None
    verification_status: str | None
    detail: str


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


class EvidenceResponse(BaseModel):
    """One observation about a world, with its authority stated rather than implied.

    ``machine_verifiable`` is the authority bit and it comes straight off the
    domain model: only evidence carrying it may disqualify a world. A client
    must never infer authority from ``source`` — a TrueForge sandbox probe and a
    BRANCHPOINT replay both have a source string, and only one of them counts.

    ``disqualifying`` is the domain's own :attr:`Evidence.disqualifies`
    (machine-verifiable *and* failing), exposed so the client does not have to
    recombine the two and risk recombining them differently.
    """

    evidence_id: str
    kind: EvidenceKind
    source: str
    claim: str
    world_id: str | None
    observed: ScalarValue
    expected: ScalarValue
    passed: bool | None
    severity: EvidenceSeverity
    machine_verifiable: bool
    disqualifying: bool
    artifact: str | None
    recorded_at: datetime

    @classmethod
    def from_domain(cls, evidence: Evidence) -> "EvidenceResponse":
        """Build the response from a domain evidence record."""
        return cls(
            evidence_id=evidence.evidence_id,
            kind=evidence.kind,
            source=evidence.source,
            claim=evidence.claim,
            world_id=evidence.world_id,
            observed=evidence.observed,
            expected=evidence.expected,
            passed=evidence.passed,
            severity=evidence.severity,
            machine_verifiable=evidence.machine_verifiable,
            disqualifying=evidence.disqualifies,
            artifact=evidence.artifact,
            recorded_at=evidence.recorded_at,
        )


class CounterexampleResponse(BaseModel):
    """One adversarial attack against a world, and what it is allowed to prove.

    ``status`` is what the attack claimed. ``authoritative`` is whether
    BRANCHPOINT agrees — computed by the domain's own
    :func:`counterexample_vetoes`, which requires both a reproduction *and*
    machine-verifiable failing evidence behind it.

    Those two can disagree, and that disagreement is the point: an adversary
    that asserts ``REPRODUCED`` without disqualifying evidence serializes as
    ``reproduced=true, authoritative=false`` and vetoes nothing.
    """

    counterexample_id: str
    world_id: str
    title: str
    hypothesis: str
    status: CounterexampleStatus
    reproduced: bool
    authoritative: bool
    created_at: datetime
    reproduction_steps: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    #: The subset of ``evidence_ids`` that is machine-verifiable and failing —
    #: i.e. the replay results that actually justify this attack.
    supporting_evidence_ids: tuple[str, ...]

    @classmethod
    def from_domain(
        cls, counterexample: Counterexample, evidence_by_id: dict[str, Evidence]
    ) -> "CounterexampleResponse":
        """Build the response, deciding authority through the domain rule."""
        return cls(
            counterexample_id=counterexample.attack_id,
            world_id=counterexample.world_id,
            title=counterexample.title,
            hypothesis=counterexample.hypothesis,
            status=counterexample.status,
            reproduced=counterexample.status is CounterexampleStatus.REPRODUCED,
            authoritative=counterexample_vetoes(counterexample, evidence_by_id),
            created_at=counterexample.created_at,
            reproduction_steps=counterexample.reproduction_steps,
            evidence_ids=counterexample.evidence_ids,
            supporting_evidence_ids=tuple(
                evidence_id
                for evidence_id in counterexample.evidence_ids
                if (item := evidence_by_id.get(evidence_id)) is not None and item.disqualifies
            ),
        )


class VetoBasis(StrEnum):
    """Which of the two authoritative paths produced a veto.

    Mirrors :func:`app.domain.worlds.verdicts.derive_verdict`, which vetoes
    either on a substantiated counterexample or on standalone machine-verifiable
    failing evidence. Both are authoritative; neither can come from model prose.
    """

    REPRODUCED_COUNTEREXAMPLE = "REPRODUCED_COUNTEREXAMPLE"
    MACHINE_VERIFIABLE_FAILURE = "MACHINE_VERIFIABLE_FAILURE"


class WorldVetoResponse(BaseModel):
    """Structured linkage from a veto to the evidence that justified it.

    Exists so a client never has to parse ``verdict_reason`` to find out what
    vetoed a world. ``authoritative`` is ``True`` by construction: a veto is only
    ever produced by evidence that qualifies, so a non-authoritative veto is not
    a thing this API can represent.
    """

    basis: VetoBasis
    #: Absent when the veto came from standalone failing evidence.
    counterexample_id: str | None
    #: The machine-verifiable failing evidence behind the veto.
    evidence_ids: tuple[str, ...]
    authoritative: bool
    summary: str

    @classmethod
    def from_domain(cls, world: World) -> "WorldVetoResponse | None":
        """Return the veto linkage for ``world``, or ``None`` if it was not vetoed.

        Both branches delegate to the domain's own rules rather than re-deriving
        them here, so this can never disagree with the verdict it describes.
        """
        vetoing = vetoing_counterexamples(world)
        if vetoing:
            index = world.evidence_by_id
            first = vetoing[0]
            return cls(
                basis=VetoBasis.REPRODUCED_COUNTEREXAMPLE,
                counterexample_id=first.attack_id,
                evidence_ids=tuple(
                    evidence_id
                    for counterexample in vetoing
                    for evidence_id in counterexample.evidence_ids
                    if (item := index.get(evidence_id)) is not None and item.disqualifies
                ),
                authoritative=True,
                summary=first.title,
            )

        failing = disqualifying_evidence(world)
        if failing:
            return cls(
                basis=VetoBasis.MACHINE_VERIFIABLE_FAILURE,
                counterexample_id=None,
                evidence_ids=tuple(item.evidence_id for item in failing),
                authoritative=True,
                summary=", ".join(item.claim for item in failing),
            )
        return None


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
    #: How many counterexamples BRANCHPOINT actually accepts as substantiated.
    #: Can be lower than ``reproduced_counterexamples``: claiming a reproduction
    #: is not the same as having evidence for one.
    authoritative_counterexamples: int
    #: Structured linkage to what vetoed this world, or ``null``.
    veto: WorldVetoResponse | None

    @classmethod
    def from_domain(cls, world: World) -> "WorldDetailResponse":
        """Build the response from a domain world."""
        outcome = world.outcome
        index = world.evidence_by_id
        return cls(
            authoritative_counterexamples=sum(
                1 for cx in world.counterexamples if counterexample_vetoes(cx, index)
            ),
            veto=WorldVetoResponse.from_domain(world),
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
                1 for cx in world.counterexamples if cx.status is CounterexampleStatus.REPRODUCED
            ),
        )


class WorldInspectionResponse(BaseModel):
    """Everything BRANCHPOINT recorded about one world.

    The Inspector's whole chain is readable from this without parsing prose:
    the exploratory attack (``counterexamples``, and evidence whose
    ``machine_verifiable`` is false), what BRANCHPOINT independently replayed
    (evidence whose ``machine_verifiable`` is true), which of those failed
    (``disqualifying``), and what that produced (``veto``).
    """

    run_id: str
    world: WorldDetailResponse
    #: Domain order, which is arrival order: execution evidence, then attack
    #: evidence, then replay evidence.
    evidence: tuple[EvidenceResponse, ...]
    counterexamples: tuple[CounterexampleResponse, ...]

    @classmethod
    def from_domain(cls, run_id: str, world: World) -> "WorldInspectionResponse":
        """Build the response from a domain world."""
        index = world.evidence_by_id
        return cls(
            run_id=run_id,
            world=WorldDetailResponse.from_domain(world),
            evidence=tuple(EvidenceResponse.from_domain(item) for item in world.evidence),
            counterexamples=tuple(
                CounterexampleResponse.from_domain(counterexample, index)
                for counterexample in world.counterexamples
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


@router.post(
    "/agent-runs",
    response_model=AcceptedRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_agent_run(
    body: StartAgentRunRequest,
    events: EventSinkDep,
    bindings: SessionBindingStoreDep,
    runner: BackgroundRunnerDep,
) -> AcceptedRunResponse:
    """Open a TrueForge-backed run and drive it to the approval gate in the background.

    Returns ``202`` as soon as the run exists, so Mission Control can navigate
    to it and watch the real lifecycle rather than staring at a blocked POST for
    the length of a planning pass.

    The drive runs in this process against **this same run id**. It stops at
    ``AWAITING_APPROVAL`` (or a terminal rejection): committing still requires
    the separate, human-approved path, and nothing in reality has changed when
    this returns.
    """
    settings: Settings = get_settings()
    try:
        # Checked before the run exists: a half-configured run would be created
        # only to fail on its first agent call. The same resolution runs again
        # inside ``build_agent_orchestrator``.
        settings.resolve_model()
    except ModelNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    service = AgentRunService(
        orchestrator=build_agent_orchestrator(), events=events, bindings=bindings
    )
    run = await service.create_run(body.to_incident())

    # ``drive_safely`` turns any pipeline failure into this run's own FAILED
    # state, so a client watching the run always learns what happened.
    started = runner.start(run.run_id, lambda: service.drive_safely(run.run_id))
    if not started:  # pragma: no cover - a fresh run id cannot already be running
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"run {run.run_id} is already being driven",
        )

    return AcceptedRunResponse(run_id=run.run_id, status=run.status, detail="run accepted")


@router.get("/agent-runs/{run_id}", response_model=AgentRunResponse)
async def get_agent_run(
    run_id: str, repository: RunRepositoryDep, bindings: SessionBindingStoreDep
) -> AgentRunResponse:
    """Return a run's status together with its TrueForge session bindings."""
    return await _agent_run_response(run_id, repository, bindings)


@router.post("/runs/{run_id}/approval", response_model=ApprovalDecisionResponse)
async def approve_run(run_id: str, body: ApproveRunRequest) -> ApprovalDecisionResponse:
    """Record explicit human approval of the recommended world, and commit it.

    This is a decision, not a mutation request: the body carries no action, no
    parameters, and no target. BRANCHPOINT commits exactly the action it already
    bound to this run's approval, through the destructive MCP tool, and then
    verifies reality independently. Re-submitting is idempotent — a run a human
    already approved is returned as-is rather than committed twice.
    """
    settings: Settings = get_settings()
    try:
        settings.resolve_model()
    except ModelNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    coordinator = build_approval_coordinator()
    try:
        run = await coordinator.approve(
            run_id,
            actor=body.actor,
            expected_world_id=body.expected_world_id,
            expected_action_id=body.expected_action_id,
            expected_action_fingerprint=body.expected_action_fingerprint,
        )
    except RunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ApprovalNotAvailableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ApprovalMismatchError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except CommitFailedError as exc:
        # The run itself carries what happened; this is not a client error.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    except TrueForgeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"TrueForge failure: {exc}"
        ) from exc

    return _approval_response(run)


def _approval_response(run) -> ApprovalDecisionResponse:
    """Render the post-approval state a frontend needs."""
    approval = run.approval
    assert approval is not None  # an approved run always carries its approval
    world = run.require_world(approval.selected_world_id)
    return ApprovalDecisionResponse(
        run_id=run.run_id,
        world_id=approval.selected_world_id,
        action_id=approval.action_id,
        action_name=world.candidate_action.name,
        approval_status=str(approval.status),
        run_status=run.status,
        commit_status=str(run.commit_receipt.status) if run.commit_receipt else None,
        verification_status=str(run.verification.status) if run.verification else None,
        detail=(
            f"{world.candidate_action.name} committed and independently verified"
            if run.status is RunStatus.SUCCEEDED
            else f"run is {run.status}: {run.failure_reason or 'see run detail'}"
        ),
    )


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


@router.post("/runs/{run_id}/rejection", response_model=HumanDecisionResponse)
async def reject_run(run_id: str, body: RejectRunRequest) -> HumanDecisionResponse:
    """Record a human's refusal of the recommended world.

    Governance, not safety: the world's verdict, its evidence, and every
    counterexample are untouched. What changes is that a person declined to act,
    which is a fact BRANCHPOINT stores and nothing else may assert on their
    behalf.

    This route cannot commit. It never reaches the commit operator or the
    capability store, and the run it leaves behind is terminal ``REJECTED``,
    which every existing commit gate already refuses.
    """
    coordinator = build_approval_coordinator()
    try:
        run = await coordinator.reject(run_id, actor=body.actor, reason=body.reason)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ApprovalNotAvailableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    approval = run.approval
    assert approval is not None  # a rejected run always carries its decision
    return HumanDecisionResponse(
        run_id=run.run_id,
        world_id=approval.selected_world_id,
        approval_status=str(approval.status),
        run_status=run.status,
        actor=approval.actor,
        reason=approval.reason,
        decided_at=approval.decided_at,
        commit_possible=False,
        detail="human rejection recorded; nothing was committed and reality is unchanged",
    )


@router.get("/runs/{run_id}/worlds/{world_id}", response_model=WorldInspectionResponse)
async def get_run_world(
    run_id: str, world_id: str, repository: RunRepositoryDep
) -> WorldInspectionResponse:
    """Return one world with its evidence, counterexamples, and veto linkage.

    Read-only. Everything it reports is already stored on the world; this route
    stops hiding it behind counts.
    """
    run = await repository.get(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"run {run_id} not found")
    world = run.world(world_id)
    if world is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"world {world_id} not found in run {run_id}",
        )
    return WorldInspectionResponse.from_domain(run_id, world)


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
