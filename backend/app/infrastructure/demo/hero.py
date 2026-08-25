"""Deterministic demo test adapters for the checkout hero scenario.

``HeroCandidatePlanner`` and ``HeroAdversarialTester`` are explicitly DEMO TEST
ADAPTERS, not AI. They exist to prove the complete pre-TrueForge BRANCHPOINT
pipeline — observe, plan, fork, execute, attack, compare, approve, commit,
verify — runs correctly end to end with zero network dependencies. TrueForge
replaces both of these in a later phase; nothing about their existence implies
final agent behavior.

The adversarial tester's attack is not scripted to target any one action: it
runs the same deterministic compatibility suite against every world's
resulting state and only reproduces where that state actually breaks
compatibility. Against beta and gamma (which never touch the deployment
version) it genuinely does not reproduce.
"""

from app.domain.actions.models import (
    ActionSource,
    ActionSourceKind,
    ActionTarget,
    ActionType,
    CandidateAction,
    RiskClass,
)
from app.domain.incidents.models import Incident, ObservedState
from app.domain.primitives import new_id
from app.domain.worlds.models import AdversarialReport, Counterexample, CounterexampleStatus, World
from app.infrastructure.demo.actions import (
    FLAG_KEY_PARAM,
    PRICING_FLAG_KEY,
    TARGET_REPLICAS_PARAM,
    VERSION_PARAM,
)
from app.infrastructure.demo.engine import DemoProductionEngine
from app.infrastructure.demo.evidence import check_result_to_evidence
from app.infrastructure.demo.workload import run_compatibility_suite

ROLLBACK_TARGET_VERSION = "v2.40"
SCALE_TARGET_REPLICAS = 12


def _hero_source() -> ActionSource:
    return ActionSource(
        kind=ActionSourceKind.PLANNER,
        name="hero-demo-planner",
        rationale="deterministic demo test adapter, not an AI planner",
    )


class HeroCandidatePlanner:
    """Deterministic demo planner: always proposes exactly the three hero actions."""

    async def plan(
        self, incident: Incident, observed_state: ObservedState, *, run_id: str
    ) -> tuple[CandidateAction, ...]:
        """Return the alpha/beta/gamma hero candidate actions, regardless of input.

        A real planner would derive candidates from ``observed_state``; this
        one exists to exercise the deterministic pipeline, so it always
        proposes the same three actions.
        """
        return (
            CandidateAction(
                action_id=new_id("action"),
                name="Roll back pricing-service to v2.40",
                description="Redeploy pricing-service at the previous version, v2.40.",
                action_type=ActionType.ROLLBACK,
                target=ActionTarget(service="pricing-service"),
                expected_outcome="Checkout error rate and latency recover to baseline.",
                risk_class=RiskClass.HIGH,
                reversible=True,
                source=_hero_source(),
                parameters={VERSION_PARAM: ROLLBACK_TARGET_VERSION},
            ),
            CandidateAction(
                action_id=new_id("action"),
                name="Disable PRICING_V2 feature flag",
                description="Disable the PRICING_V2 flag, routing checkout to the legacy pricing path.",
                action_type=ActionType.FEATURE_FLAG_DISABLE,
                target=ActionTarget(service="pricing-service"),
                expected_outcome="Checkout error rate and latency recover to baseline.",
                risk_class=RiskClass.LOW,
                reversible=True,
                source=_hero_source(),
                parameters={FLAG_KEY_PARAM: PRICING_FLAG_KEY},
            ),
            CandidateAction(
                action_id=new_id("action"),
                name="Scale pricing-service to 12 replicas",
                description="Add pricing-service capacity to absorb the regression's load.",
                action_type=ActionType.SCALE,
                target=ActionTarget(service="pricing-service"),
                expected_outcome="Checkout error rate and latency improve materially.",
                risk_class=RiskClass.MEDIUM,
                reversible=True,
                source=_hero_source(),
                parameters={TARGET_REPLICAS_PARAM: SCALE_TARGET_REPLICAS},
            ),
        )


class HeroAdversarialTester:
    """Deterministic demo attacker: reproduces the known rollback compatibility test.

    Attacks every world by running the same compatibility suite against that
    world's resulting state. The attack only reproduces where the suite
    actually fails — it does not know or care which action produced the state
    it is checking.
    """

    def __init__(self, engine: DemoProductionEngine) -> None:
        self._engine = engine

    async def attack(self, world: World) -> AdversarialReport:
        """Run the compatibility suite against ``world``'s resulting state."""
        state = await self._engine.world_state(world.world_id)
        checks = run_compatibility_suite(state)
        evidence = tuple(
            check_result_to_evidence(
                check, source="hero-adversarial-tester", world_id=world.world_id
            )
            for check in checks
        )
        failing = tuple(check for check in checks if not check.passed)

        if not failing:
            counterexample = Counterexample(
                attack_id=new_id("attack"),
                world_id=world.world_id,
                title="Order compatibility probe",
                hypothesis=(
                    "The active pricing-service deployment cannot interpret a v2.41-created "
                    "order's payment_revision field."
                ),
                reproduction_steps=(
                    "select a v2.41-created order with payment_revision set",
                    "check the active deployment's declared orders-schema support",
                    "retry payment and compare the recomputed idempotency key",
                ),
                evidence_ids=tuple(item.evidence_id for item in evidence),
                status=CounterexampleStatus.NOT_REPRODUCED,
            )
            return AdversarialReport(counterexamples=(counterexample,), evidence=evidence)

        counterexample = Counterexample(
            attack_id=new_id("attack"),
            world_id=world.world_id,
            title="Rollback order-compatibility regression",
            hypothesis=(
                "A pricing-service deployment older than v2.41 cannot interpret "
                "payment_revision, breaking retry idempotency for v2.41-created orders."
            ),
            reproduction_steps=(
                "select a v2.41-created order with payment_revision set",
                "check the active deployment's declared orders-schema support",
                "retry payment and compare the recomputed idempotency key",
            ),
            evidence_ids=tuple(item.evidence_id for item in evidence),
            status=CounterexampleStatus.REPRODUCED,
        )
        return AdversarialReport(counterexamples=(counterexample,), evidence=evidence)
