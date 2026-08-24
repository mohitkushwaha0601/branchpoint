"""Deterministic builders for domain objects used across tests."""

from datetime import UTC, datetime

from app.domain.actions.models import (
    ActionSource,
    ActionSourceKind,
    ActionTarget,
    ActionType,
    CandidateAction,
    RiskClass,
)
from app.domain.evidence.models import Evidence, EvidenceKind, EvidenceSeverity
from app.domain.incidents.models import (
    Incident,
    IncidentSeverity,
    MetricObservation,
    ObservedState,
)
from app.domain.worlds.lifecycle import WorldStatus
from app.domain.worlds.models import (
    AdversarialReport,
    Counterexample,
    ExecutionOutcome,
    World,
    WorldExecutionReport,
)
from app.domain.worlds.verdicts import derive_verdict

FIXED_TIME = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


def make_incident(incident_id: str = "incident_1") -> Incident:
    """Return a generic incident."""
    return Incident(
        incident_id=incident_id,
        title="Checkout error rate elevated",
        goal="Return checkout error rate below 1%",
        severity=IncidentSeverity.CRITICAL,
        detected_at=FIXED_TIME,
        affected_services=("checkout", "pricing-service"),
    )


def make_observed_state() -> ObservedState:
    """Return a structured observation of degraded reality."""
    return ObservedState(
        observed_at=FIXED_TIME,
        source="test-telemetry",
        metrics=(
            MetricObservation(
                name="checkout_error_rate",
                value=0.41,
                observed_at=FIXED_TIME,
                unit="ratio",
                baseline=0.004,
                threshold=0.01,
            ),
        ),
    )


def make_action(
    action_id: str = "action_1",
    *,
    name: str = "Disable pricing v2 flag",
    action_type: ActionType = ActionType.FEATURE_FLAG_DISABLE,
    reversible: bool = True,
    risk_class: RiskClass = RiskClass.LOW,
    parameters: dict[str, bool | float | str] | None = None,
) -> CandidateAction:
    """Return a candidate action."""
    return CandidateAction(
        action_id=action_id,
        name=name,
        description=f"{name} in production",
        action_type=action_type,
        target=ActionTarget(service="pricing-service"),
        expected_outcome="Checkout error rate returns below threshold",
        risk_class=risk_class,
        reversible=reversible,
        source=ActionSource(kind=ActionSourceKind.PLANNER, name="test-planner"),
        parameters=parameters or {},
    )


def make_evidence(
    evidence_id: str = "evidence_1",
    *,
    kind: EvidenceKind = EvidenceKind.METRIC,
    passed: bool | None = True,
    machine_verifiable: bool = True,
    severity: EvidenceSeverity = EvidenceSeverity.INFO,
    world_id: str | None = None,
    claim: str = "checkout error rate below threshold",
) -> Evidence:
    """Return one piece of evidence."""
    return Evidence(
        evidence_id=evidence_id,
        kind=kind,
        source="test-harness",
        claim=claim,
        world_id=world_id,
        passed=passed,
        machine_verifiable=machine_verifiable,
        severity=severity,
        recorded_at=FIXED_TIME,
    )


def make_outcome(
    *,
    succeeded: bool = True,
    goal_achieved: bool = True,
    goal_attainment: float = 1.0,
    invariants_preserved: bool = True,
    regressions_detected: int = 0,
    blast_radius: int = 1,
    reversible: bool = True,
    cost_delta: float = 0.0,
    summary: str = "counterfactual execution completed",
) -> ExecutionOutcome:
    """Return a measured execution outcome."""
    return ExecutionOutcome(
        succeeded=succeeded,
        goal_achieved=goal_achieved,
        goal_attainment=goal_attainment,
        invariants_preserved=invariants_preserved,
        regressions_detected=regressions_detected,
        blast_radius=blast_radius,
        reversible=reversible,
        cost_delta=cost_delta,
        summary=summary,
    )


def make_counterexample(
    attack_id: str,
    world_id: str,
    *,
    status,
    evidence_ids: tuple[str, ...] = (),
    title: str = "Migration replay regression",
) -> Counterexample:
    """Return a DOPPELGÄNGER counterexample."""
    return Counterexample(
        attack_id=attack_id,
        world_id=world_id,
        title=title,
        hypothesis="The action reintroduces an incompatible schema state",
        created_at=FIXED_TIME,
        reproduction_steps=("replay migration", "assert order rows intact"),
        evidence_ids=evidence_ids,
        status=status,
    )


def completed_world(
    *,
    world_id: str = "world_1",
    run_id: str = "run_1",
    action: CandidateAction | None = None,
    outcome: ExecutionOutcome | None = None,
    execution_evidence: tuple[Evidence, ...] = (),
    attack_evidence: tuple[Evidence, ...] = (),
    counterexamples: tuple[Counterexample, ...] = (),
) -> World:
    """Drive a world through its real lifecycle and settle its derived verdict."""
    world = World.create(
        world_id=world_id,
        run_id=run_id,
        candidate_action=action or make_action(),
        at=FIXED_TIME,
    )
    world = world.transition_to(WorldStatus.PREPARING, at=FIXED_TIME)
    world = world.transition_to(WorldStatus.EXECUTING, at=FIXED_TIME)
    world = world.record_execution(
        WorldExecutionReport(
            outcome=outcome or make_outcome(),
            evidence=execution_evidence or (make_evidence(f"{world_id}_metric"),),
        ),
        at=FIXED_TIME,
    )
    world = world.transition_to(WorldStatus.ATTACKING, at=FIXED_TIME)
    world = world.record_attacks(
        AdversarialReport(counterexamples=counterexamples, evidence=attack_evidence),
        at=FIXED_TIME,
    )
    world = world.transition_to(WorldStatus.EVALUATING, at=FIXED_TIME)
    verdict, reason = derive_verdict(world)
    return world.settle(verdict, reason, at=FIXED_TIME)
