"""The BRANCHPOINT hero scenario: the obvious action loses.

Checkout error rate is ~41% after pricing-service v2.41 ships. The obvious fix
is a rollback. It measures best on every raw dimension — and it is still
rejected, because a DOPPELGÄNGER reproduces a migration regression against it.
The unglamorous feature-flag disable wins on evidence.
"""

from app.application.orchestration.orchestrator import BranchpointOrchestrator
from app.application.world_engine.comparator import compare_worlds
from app.domain.actions.models import ActionType, RiskClass
from app.domain.commits.models import CommitStatus
from app.domain.comparison.models import RejectionReason
from app.domain.events import RunEventType
from app.domain.evidence.models import EvidenceKind, EvidenceSeverity
from app.domain.runs.lifecycle import RunStatus
from app.domain.verification.models import VerificationCheck, VerificationStatus
from app.domain.worlds.models import (
    AdversarialReport,
    CounterexampleStatus,
    WorldExecutionReport,
    WorldVerdict,
)
from app.infrastructure.persistence.memory import InMemoryEventSink, InMemoryRunRepository
from tests.doubles import (
    RecordingMutator,
    ScriptedAdversarialTester,
    ScriptedWorldExecutor,
    SequentialIds,
    StubPlanner,
    StubRealityReader,
    StubVerifier,
)
from tests.factories import (
    FIXED_TIME,
    completed_world,
    make_action,
    make_counterexample,
    make_evidence,
    make_incident,
    make_observed_state,
    make_outcome,
)

ALPHA = make_action(
    "action_alpha",
    name="Roll back pricing-service to v2.40",
    action_type=ActionType.ROLLBACK,
    risk_class=RiskClass.HIGH,
    parameters={"version": "v2.40"},
)
BETA = make_action(
    "action_beta",
    name="Disable pricing_v2 feature flag",
    action_type=ActionType.FEATURE_FLAG_DISABLE,
    risk_class=RiskClass.LOW,
    parameters={"flag": "pricing_v2"},
)
GAMMA = make_action(
    "action_gamma",
    name="Scale pricing-service to 12 replicas",
    action_type=ActionType.SCALE,
    risk_class=RiskClass.MEDIUM,
    parameters={"replicas": 12.0},
)

# Alpha measures best on every raw dimension: full recovery, smallest blast
# radius, and it even saves money.
ALPHA_OUTCOME = make_outcome(
    goal_achieved=True, goal_attainment=1.0, blast_radius=1, cost_delta=-0.05
)
BETA_OUTCOME = make_outcome(goal_achieved=True, goal_attainment=1.0, blast_radius=2, cost_delta=0.0)
GAMMA_OUTCOME = make_outcome(
    goal_achieved=False,
    goal_attainment=0.55,
    regressions_detected=1,
    blast_radius=3,
    cost_delta=0.42,
    summary="error rate fell to 18%, still above threshold",
)

EXECUTION_REPORTS = {
    "action_alpha": WorldExecutionReport(
        outcome=ALPHA_OUTCOME,
        evidence=(
            make_evidence("alpha_metric", kind=EvidenceKind.METRIC, passed=True),
            make_evidence("alpha_exec", kind=EvidenceKind.EXECUTION_RESULT, passed=True),
        ),
    ),
    "action_beta": WorldExecutionReport(
        outcome=BETA_OUTCOME,
        evidence=(
            make_evidence("beta_metric", kind=EvidenceKind.METRIC, passed=True),
            make_evidence("beta_invariant", kind=EvidenceKind.INVARIANT, passed=True),
        ),
    ),
    "action_gamma": WorldExecutionReport(
        outcome=GAMMA_OUTCOME,
        evidence=(
            make_evidence("gamma_metric", kind=EvidenceKind.METRIC, passed=True),
            make_evidence("gamma_cost", kind=EvidenceKind.COST, passed=True),
        ),
    ),
}

MIGRATION_REGRESSION = make_evidence(
    "alpha_migration_replay",
    kind=EvidenceKind.TEST_RESULT,
    passed=False,
    machine_verifiable=True,
    severity=EvidenceSeverity.CRITICAL,
    claim="orders written under v2.41 remain readable after rollback",
)

ADVERSARIAL_REPORTS = {
    "action_alpha": AdversarialReport(
        counterexamples=(
            make_counterexample(
                "attack_alpha",
                "world_1",
                status=CounterexampleStatus.REPRODUCED,
                evidence_ids=("alpha_migration_replay",),
                title="v2.41 order rows unreadable after rollback",
            ),
        ),
        evidence=(MIGRATION_REGRESSION,),
    ),
    # Beta is attacked just as hard; the attack simply does not reproduce.
    "action_beta": AdversarialReport(
        counterexamples=(
            make_counterexample(
                "attack_beta",
                "world_2",
                status=CounterexampleStatus.NOT_REPRODUCED,
                evidence_ids=("beta_attack_probe",),
                title="Disabling the flag strands in-flight carts",
            ),
        ),
        evidence=(
            make_evidence(
                "beta_attack_probe",
                kind=EvidenceKind.DATA_INTEGRITY,
                passed=True,
                machine_verifiable=True,
                claim="in-flight carts survive the flag flip",
            ),
        ),
    ),
    "action_gamma": AdversarialReport(),
}


def build_orchestrator() -> tuple[BranchpointOrchestrator, InMemoryEventSink, RecordingMutator]:
    """Wire the hero scenario with in-memory doubles."""
    mutator = RecordingMutator()
    events = InMemoryEventSink()
    orchestrator = BranchpointOrchestrator(
        repository=InMemoryRunRepository(),
        events=events,
        reality_reader=StubRealityReader(make_observed_state()),
        planner=StubPlanner((ALPHA, BETA, GAMMA)),
        world_executor=ScriptedWorldExecutor(EXECUTION_REPORTS),
        adversarial_tester=ScriptedAdversarialTester(ADVERSARIAL_REPORTS),
        mutator=mutator,
        verifier=StubVerifier(
            (
                VerificationCheck(
                    key="checkout_error_rate",
                    description="checkout error rate is below 1%",
                    passed=True,
                    observed=0.004,
                    expected=0.01,
                ),
            )
        ),
        clock=lambda: FIXED_TIME,
        id_factory=SequentialIds(),
    )
    return orchestrator, events, mutator


async def test_rollback_is_vetoed_and_the_feature_flag_wins() -> None:
    orchestrator, _, _ = build_orchestrator()

    run = await orchestrator.drive_to_approval(make_incident())

    worlds = {world.candidate_action.action_id: world for world in run.worlds}
    assert worlds["action_alpha"].verdict is WorldVerdict.VETOED
    assert worlds["action_beta"].verdict is WorldVerdict.SURVIVED
    assert worlds["action_gamma"].verdict is WorldVerdict.SURVIVED

    assert run.comparison is not None
    assert run.comparison.recommended_world_id == worlds["action_beta"].world_id
    assert run.status is RunStatus.AWAITING_APPROVAL

    rejected = {item.world_id: item for item in run.comparison.rejected_worlds}
    alpha_rejection = rejected[worlds["action_alpha"].world_id]
    assert RejectionReason.ADVERSARIAL_VETO in alpha_rejection.reasons
    assert "alpha_migration_replay" in alpha_rejection.evidence_ids

    ranks = {ranking.world_id: ranking.rank for ranking in run.comparison.rankings}
    assert ranks[worlds["action_beta"].world_id] < ranks[worlds["action_gamma"].world_id]


async def test_the_rollback_would_have_won_without_the_reproduced_attack() -> None:
    """Without the DOPPELGÄNGER, the obvious action wins on raw measurements."""
    alpha = completed_world(world_id="world_alpha", action=ALPHA, outcome=ALPHA_OUTCOME)
    beta = completed_world(world_id="world_beta", action=BETA, outcome=BETA_OUTCOME)
    gamma = completed_world(world_id="world_gamma", action=GAMMA, outcome=GAMMA_OUTCOME)

    result = compare_worlds([alpha, beta, gamma])

    assert result.recommended_world_id == "world_alpha"


async def test_hero_scenario_commits_only_the_approved_world() -> None:
    orchestrator, events, mutator = build_orchestrator()

    run = await orchestrator.drive_to_approval(make_incident())
    beta_world_id = run.comparison.recommended_world_id
    run = await orchestrator.decide_approval(
        run.run_id,
        approved=True,
        actor="sre@example.com",
        reason="survived adversarial testing with full recovery",
    )
    run = await orchestrator.commit(run.run_id)
    run = await orchestrator.verify(run.run_id)

    assert run.status is RunStatus.SUCCEEDED
    assert run.commit_receipt is not None
    assert run.commit_receipt.status is CommitStatus.SUCCEEDED
    assert run.verification is not None
    assert run.verification.status is VerificationStatus.PASSED

    # Exactly one action reached reality, and it is the approved one.
    assert mutator.applied == [(beta_world_id, "action_beta")]

    timeline = [event.event_type for event in await events.events_for(run.run_id)]
    assert timeline.count(RunEventType.COUNTEREXAMPLE_REPRODUCED) == 1
    assert timeline.count(RunEventType.WORLD_VETOED) == 1
    assert timeline.count(RunEventType.WORLD_SURVIVED) == 2
    assert timeline.count(RunEventType.COMMIT_COMPLETED) == 1
