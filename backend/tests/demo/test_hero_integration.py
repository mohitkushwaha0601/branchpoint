"""The complete pre-TrueForge hero pipeline: observe -> plan -> fork -> execute
-> attack -> compare -> approve -> commit -> verify, driven entirely by the
real Phase 1 orchestrator and the real Phase 2 demo adapters.

No LLM, no TrueForge, no scripted "if action == rollback" branch anywhere in
this chain: alpha is vetoed because its state genuinely breaks a compatibility
check, not because anything here knows its name.
"""

from app.application.orchestration.orchestrator import BranchpointOrchestrator
from app.domain.commits.models import CommitStatus
from app.domain.incidents.models import Incident, IncidentSeverity
from app.domain.primitives import new_id, utc_now
from app.domain.runs.lifecycle import RunStatus
from app.domain.verification.models import VerificationStatus
from app.domain.worlds.models import WorldVerdict
from app.infrastructure.demo.adapters import (
    DemoRealityMutator,
    DemoRealityReader,
    DemoRealityVerifier,
    DemoWorldExecutor,
)
from app.infrastructure.demo.capability import CapabilityStore
from app.infrastructure.demo.engine import DemoProductionEngine
from app.infrastructure.demo.hero import HeroAdversarialTester, HeroCandidatePlanner
from app.infrastructure.persistence.memory import InMemoryEventSink, InMemoryRunRepository


def _build_hero_orchestrator() -> tuple[BranchpointOrchestrator, DemoProductionEngine]:
    engine = DemoProductionEngine()
    capability_store = CapabilityStore()
    orchestrator = BranchpointOrchestrator(
        repository=InMemoryRunRepository(),
        events=InMemoryEventSink(),
        reality_reader=DemoRealityReader(engine),
        planner=HeroCandidatePlanner(),
        world_executor=DemoWorldExecutor(engine),
        adversarial_tester=HeroAdversarialTester(engine),
        mutator=DemoRealityMutator(engine, capability_store),
        verifier=DemoRealityVerifier(engine),
    )
    return orchestrator, engine


def _incident() -> Incident:
    return Incident(
        incident_id=new_id("incident"),
        title="Checkout error rate at 41.3%",
        goal="Return checkout error rate below 2%",
        severity=IncidentSeverity.CRITICAL,
        detected_at=utc_now(),
        affected_services=("checkout", "pricing-service"),
    )


async def test_alpha_looks_attractive_before_adversarial_evidence() -> None:
    """After execution alone (before the attack phase), alpha's measured
    outcome must look good: this is what makes the veto meaningful."""
    orchestrator, _ = _build_hero_orchestrator()
    run = await orchestrator.create_run(_incident())
    run = await orchestrator.observe(run.run_id)
    run = await orchestrator.plan(run.run_id)
    run = await orchestrator.fork(run.run_id)
    run = await orchestrator.execute_worlds(run.run_id)

    alpha = next(w for w in run.worlds if w.candidate_action.action_type.value == "ROLLBACK")
    assert alpha.outcome is not None
    assert alpha.outcome.goal_achieved is True
    assert alpha.outcome.regressions_detected == 0
    assert all(item.passed for item in alpha.evidence)
    assert alpha.verdict is None  # not yet attacked, so not yet vetoed


async def test_alpha_is_vetoed_after_the_executable_rollback_counterexample() -> None:
    orchestrator, _ = _build_hero_orchestrator()
    run = await orchestrator.drive_to_approval(_incident())

    alpha = next(w for w in run.worlds if w.candidate_action.action_type.value == "ROLLBACK")
    assert alpha.verdict is WorldVerdict.VETOED
    reproduced = [cx for cx in alpha.counterexamples if cx.status.value == "REPRODUCED"]
    assert reproduced
    assert any(item.evidence_id in reproduced[0].evidence_ids for item in alpha.evidence)


async def test_beta_survives_the_full_pipeline() -> None:
    orchestrator, _ = _build_hero_orchestrator()
    run = await orchestrator.drive_to_approval(_incident())

    beta = next(
        w for w in run.worlds if w.candidate_action.action_type.value == "FEATURE_FLAG_DISABLE"
    )
    assert beta.verdict is WorldVerdict.SURVIVED


async def test_gamma_is_measured_honestly_not_forced_to_lose() -> None:
    orchestrator, _ = _build_hero_orchestrator()
    run = await orchestrator.drive_to_approval(_incident())

    gamma = next(w for w in run.worlds if w.candidate_action.action_type.value == "SCALE")
    assert gamma.verdict is WorldVerdict.SURVIVED  # not vetoed: nothing machine-verifiable failed
    assert gamma.outcome is not None
    assert gamma.outcome.goal_achieved is False  # but it loses on the comparator's own ranking
    assert gamma.outcome.cost_delta == 900.0


async def test_comparator_recommends_beta() -> None:
    orchestrator, _ = _build_hero_orchestrator()
    run = await orchestrator.drive_to_approval(_incident())

    beta = next(
        w for w in run.worlds if w.candidate_action.action_type.value == "FEATURE_FLAG_DISABLE"
    )
    assert run.comparison is not None
    assert run.comparison.recommended_world_id == beta.world_id
    assert run.status is RunStatus.AWAITING_APPROVAL


async def test_approved_beta_commits_and_verification_passes() -> None:
    orchestrator, engine = _build_hero_orchestrator()
    run = await orchestrator.drive_to_approval(_incident())

    run = await orchestrator.decide_approval(run.run_id, approved=True, actor="sre@example.com")
    assert run.status is RunStatus.APPROVED

    run = await orchestrator.commit(run.run_id)
    assert run.commit_receipt is not None
    assert run.commit_receipt.status is CommitStatus.SUCCEEDED

    run = await orchestrator.verify(run.run_id)
    assert run.verification is not None
    assert run.verification.status is VerificationStatus.PASSED
    assert run.status is RunStatus.SUCCEEDED

    reality = await engine.reality()
    assert reality.pricing_flag.enabled is False
    assert reality.pricing_deployment.version == "v2.41"  # only the flag changed, nothing else


async def test_rejecting_the_recommendation_never_touches_reality() -> None:
    orchestrator, engine = _build_hero_orchestrator()
    reality_before = await engine.reality()
    run = await orchestrator.drive_to_approval(_incident())

    run = await orchestrator.decide_approval(
        run.run_id, approved=False, actor="sre@example.com", reason="hold for change window"
    )

    assert run.status is RunStatus.REJECTED
    assert await engine.reality() == reality_before
