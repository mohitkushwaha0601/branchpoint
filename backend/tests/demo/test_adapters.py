"""Phase 1 port adapters backed by the demo engine."""

from app.domain.actions.models import ActionType, RiskClass
from app.domain.commits.models import CommitReceipt
from app.domain.incidents.models import Incident, IncidentSeverity
from app.domain.primitives import utc_now
from app.domain.runs.models import BranchpointRun
from app.domain.verification.models import VerificationStatus, derive_verification_status
from app.domain.worlds.lifecycle import WorldStatus
from app.domain.worlds.models import World
from app.infrastructure.demo.adapters import (
    DemoRealityReader,
    DemoRealityVerifier,
    DemoWorldExecutor,
)
from app.infrastructure.demo.engine import DemoProductionEngine
from tests.factories import make_action, make_incident


async def test_reality_reader_emits_correct_observed_state() -> None:
    engine = DemoProductionEngine()
    reader = DemoRealityReader(engine)
    incident = Incident(
        incident_id="incident_1",
        title="checkout errors",
        goal="recover checkout",
        severity=IncidentSeverity.CRITICAL,
        detected_at=utc_now(),
    )

    observed = await reader.observe(incident)

    error_rate_metric = next(m for m in observed.metrics if m.name == "checkout_error_rate")
    assert error_rate_metric.value == 0.413
    assert observed.deployments[0].version == "v2.41"
    assert observed.feature_flags[0].enabled is True
    assert observed.services[0].replicas == 4
    assert observed.violated_invariants  # recovery SLO is breached in the initial incident


async def test_world_executor_derives_outcome_from_measurements_not_action_name() -> None:
    engine = DemoProductionEngine()
    executor = DemoWorldExecutor(engine)

    beta_action = make_action(
        "beta",
        name="totally different name",
        action_type=ActionType.FEATURE_FLAG_DISABLE,
        parameters={"flag_key": "PRICING_V2"},
        risk_class=RiskClass.LOW,
    )
    world = World.create(
        world_id="world_1", run_id="run_1", candidate_action=beta_action, at=utc_now()
    )
    world = world.transition_to(WorldStatus.PREPARING).transition_to(WorldStatus.EXECUTING)

    report = await executor.execute(world)

    # goal_attainment, blast_radius, and cost_delta must match the flag-disable
    # world's real measured outcome regardless of the action's display name.
    assert report.outcome.goal_attainment == 1.0
    assert report.outcome.blast_radius == 1
    assert report.outcome.cost_delta == 0.0


async def test_reality_verifier_checks_actual_reality_not_the_commit_receipt() -> None:
    engine = DemoProductionEngine()
    verifier = DemoRealityVerifier(engine)
    run = BranchpointRun.create(run_id="run_1", incident=make_incident(), at=utc_now())
    receipt = CommitReceipt(
        commit_id="commit_1",
        run_id="run_1",
        world_id="world_1",
        action_id="action_1",
        action_fingerprint="whatever-the-receipt-claims",
        started_at=utc_now(),
    )

    # Reality is still the unmodified initial incident: verification must fail
    # even though the (fabricated) receipt above claims nothing about status.
    checks = await verifier.verify(run, receipt)
    status = derive_verification_status(checks)

    assert status is VerificationStatus.FAILED
    recovery_check = next(check for check in checks if check.key == "recovery_slo")
    assert recovery_check.passed is False

    # Now actually mutate reality through the real capability-gated path and
    # verify again: the verifier is honest in both directions, not tuned to fail.
    await _commit_flag_disable_to_reality(engine)

    checks_after = await verifier.verify(run, receipt)
    assert derive_verification_status(checks_after) is VerificationStatus.PASSED


async def _commit_flag_disable_to_reality(engine: DemoProductionEngine) -> None:
    """Drive a real flag-disable world to reality through the full approval and
    capability path, exactly as the orchestrator would."""
    from app.domain.approvals.rules import build_approval_request
    from app.domain.comparison.models import ComparisonResult
    from app.domain.runs.lifecycle import RunStatus
    from app.domain.worlds.models import WorldVerdict
    from app.infrastructure.demo.capability import CapabilityStore
    from tests.factories import FIXED_TIME

    action = make_action(
        "beta", action_type=ActionType.FEATURE_FLAG_DISABLE, parameters={"flag_key": "PRICING_V2"}
    )
    world = World.create(
        world_id="world_beta", run_id="run_1", candidate_action=action, at=FIXED_TIME
    )
    world = world.model_copy(
        update={"status": WorldStatus.SURVIVED, "verdict": WorldVerdict.SURVIVED}
    )

    run = BranchpointRun.create(run_id="run_1", incident=make_incident(), at=FIXED_TIME)
    run = run.model_copy(update={"status": RunStatus.COMPARING, "worlds": (world,)})
    run = run.with_comparison(
        ComparisonResult(recommended_world_id="world_beta", eligible_world_ids=("world_beta",)),
        at=FIXED_TIME,
    )
    approval = build_approval_request(
        run, "world_beta", approval_id="approval_1", requested_at=FIXED_TIME
    )
    run = run.with_approval(approval, at=FIXED_TIME).transition_to(
        RunStatus.AWAITING_APPROVAL, at=FIXED_TIME
    )
    decided = run.approval.decide(approved=True, actor="sre@example.com", at=FIXED_TIME)
    run = run.with_approval(decided, at=FIXED_TIME).transition_to(RunStatus.APPROVED, at=FIXED_TIME)

    capability_store = CapabilityStore()
    issued = await capability_store.issue_for_approved_run(run)
    await engine.apply_to_reality(
        run=run, world=world, capability_store=capability_store, capability_token=issued.token
    )
