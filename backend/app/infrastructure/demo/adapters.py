"""Phase 1 port implementations backed by :class:`DemoProductionEngine`.

Each adapter is honest: every field it reports is derived from measured demo
state, never authored from the candidate action's name or type. This is what
lets the unmodified Phase 1 comparator make a real decision instead of
replaying a scripted one.
"""

from datetime import datetime

from app.domain.commits.models import CommitReceipt, OperationReceipt
from app.domain.evidence.models import Evidence, EvidenceKind
from app.domain.incidents.models import (
    DeploymentState,
    FeatureFlagState,
    Incident,
    InvariantStatement,
    MetricDirection,
    MetricObservation,
    ObservedState,
    ServiceState,
)
from app.domain.primitives import new_id, utc_now
from app.domain.runs.models import BranchpointRun
from app.domain.verification.models import VerificationCheck
from app.domain.worlds.models import ExecutionOutcome, World, WorldExecutionReport
from app.infrastructure.demo.actions import compute_blast_radius
from app.infrastructure.demo.capability import CapabilityStore
from app.infrastructure.demo.engine import DemoProductionEngine
from app.infrastructure.demo.evidence import (
    check_result_to_evidence,
    check_result_to_verification_check,
)
from app.infrastructure.demo.metrics import (
    RECOVERY_SLO_ERROR_RATE_THRESHOLD,
    RECOVERY_SLO_P95_MS_THRESHOLD,
    MetricsSnapshot,
    compute_metrics,
)
from app.infrastructure.demo.workload import run_compatibility_suite, run_execution_suite


def _metric_observation(
    name: str,
    *,
    value: float,
    unit: str,
    threshold: float | None,
    direction: MetricDirection,
    observed_at: datetime,
) -> MetricObservation:
    return MetricObservation(
        name=name,
        value=value,
        observed_at=observed_at,
        unit=unit,
        threshold=threshold,
        direction=direction,
    )


class DemoRealityReader:
    """Observes :class:`DemoProductionState` and reports it as typed :class:`ObservedState`."""

    def __init__(self, engine: DemoProductionEngine) -> None:
        self._engine = engine

    async def observe(self, incident: Incident) -> ObservedState:
        """Return the observed state of demo reality for ``incident``."""
        state = await self._engine.reality()
        metrics = compute_metrics(state)
        now = utc_now()

        return ObservedState(
            observed_at=now,
            source="demo-production-engine",
            metrics=(
                _metric_observation(
                    "checkout_error_rate",
                    value=metrics.checkout_error_rate,
                    unit="ratio",
                    threshold=RECOVERY_SLO_ERROR_RATE_THRESHOLD,
                    direction=MetricDirection.LOWER_IS_BETTER,
                    observed_at=now,
                ),
                _metric_observation(
                    "checkout_p95_ms",
                    value=metrics.checkout_p95_ms,
                    unit="ms",
                    threshold=RECOVERY_SLO_P95_MS_THRESHOLD,
                    direction=MetricDirection.LOWER_IS_BETTER,
                    observed_at=now,
                ),
                _metric_observation(
                    "pricing_timeout_rate",
                    value=metrics.pricing_timeout_rate,
                    unit="ratio",
                    threshold=None,
                    direction=MetricDirection.LOWER_IS_BETTER,
                    observed_at=now,
                ),
                _metric_observation(
                    "affected_users",
                    value=float(metrics.affected_users),
                    unit="users",
                    threshold=None,
                    direction=MetricDirection.LOWER_IS_BETTER,
                    observed_at=now,
                ),
                _metric_observation(
                    "daily_infra_cost_usd",
                    value=metrics.daily_infra_cost_usd,
                    unit="usd",
                    threshold=None,
                    direction=MetricDirection.LOWER_IS_BETTER,
                    observed_at=now,
                ),
            ),
            deployments=(
                DeploymentState(
                    service=state.pricing_deployment.service,
                    version=state.pricing_deployment.version,
                    deployed_at=state.pricing_deployment.deployed_at,
                    previous_version=state.pricing_deployment.previous_version,
                    rollback_available=state.pricing_deployment.previous_version is not None,
                ),
            ),
            feature_flags=(
                FeatureFlagState(
                    key=state.pricing_flag.key,
                    enabled=state.pricing_flag.enabled,
                    service=state.pricing_flag.service,
                ),
            ),
            services=(
                ServiceState(
                    name="pricing-service",
                    healthy=not metrics.regression_active,
                    version=state.pricing_deployment.version,
                    replicas=state.pricing_capacity.replicas,
                    error_rate=metrics.checkout_error_rate,
                ),
            ),
            invariants=(
                InvariantStatement(
                    key="checkout_within_recovery_slo",
                    description=(
                        f"checkout_error_rate <= {RECOVERY_SLO_ERROR_RATE_THRESHOLD:.3f} "
                        f"and checkout_p95_ms <= {RECOVERY_SLO_P95_MS_THRESHOLD:.0f}"
                    ),
                    holds=(
                        metrics.checkout_error_rate <= RECOVERY_SLO_ERROR_RATE_THRESHOLD
                        and metrics.checkout_p95_ms <= RECOVERY_SLO_P95_MS_THRESHOLD
                    ),
                ),
            ),
            metadata={"orders_schema_version": str(state.orders_schema_version)},
        )


class DemoWorldExecutor:
    """Executes a candidate action inside its own isolated demo world.

    Runs only the execution-time suite (aggregate metrics and general orders
    sanity). The order-specific compatibility suite is reserved for the
    adversarial phase — see :class:`~app.infrastructure.demo.hero.HeroAdversarialTester`.
    """

    def __init__(self, engine: DemoProductionEngine) -> None:
        self._engine = engine

    async def execute(self, world: World) -> WorldExecutionReport:
        """Apply ``world``'s action to an isolated snapshot and measure the result."""
        before = await self._engine.snapshot_world(world.world_id)
        after = await self._engine.apply_to_world(world.world_id, world.candidate_action)

        before_metrics = compute_metrics(before)
        after_metrics = compute_metrics(after)
        checks = run_execution_suite(after)
        evidence = tuple(
            check_result_to_evidence(check, source="demo-world-executor", world_id=world.world_id)
            for check in checks
        ) + (
            Evidence(
                evidence_id=new_id("evidence"),
                kind=EvidenceKind.COST,
                source="demo-world-executor",
                claim="daily infrastructure cost impact",
                world_id=world.world_id,
                observed=after_metrics.daily_infra_cost_usd,
                expected=before_metrics.daily_infra_cost_usd,
                passed=True,
                machine_verifiable=True,
                recorded_at=utc_now(),
            ),
        )

        goal_check = next(check for check in checks if check.name == "recovery_slo")
        regressions_detected = sum(1 for check in checks if not check.passed)
        cost_delta = after_metrics.daily_infra_cost_usd - before_metrics.daily_infra_cost_usd
        goal_attainment = _goal_attainment(before_metrics, after_metrics)

        outcome = ExecutionOutcome(
            succeeded=True,
            goal_achieved=goal_check.passed,
            invariants_preserved=all(
                check.passed for check in checks if check.name == "data_integrity"
            ),
            reversible=True,
            goal_attainment=goal_attainment,
            regressions_detected=regressions_detected,
            blast_radius=compute_blast_radius(before, after),
            cost_delta=cost_delta,
            summary=(
                f"{world.candidate_action.name}: checkout_error_rate "
                f"{before_metrics.checkout_error_rate:.3f} -> {after_metrics.checkout_error_rate:.3f}"
            ),
        )
        return WorldExecutionReport(outcome=outcome, evidence=evidence)


def _goal_attainment(before: MetricsSnapshot, after: MetricsSnapshot) -> float:
    """How much of the possible error-rate recovery this world achieved, in [0, 1]."""
    threshold = RECOVERY_SLO_ERROR_RATE_THRESHOLD
    total_possible_reduction = before.checkout_error_rate - threshold
    if total_possible_reduction <= 0:
        return 1.0
    shortfall = max(0.0, after.checkout_error_rate - threshold)
    attainment = 1.0 - min(1.0, shortfall / total_possible_reduction)
    return max(0.0, min(1.0, attainment))


class DemoRealityMutator:
    """Applies the approved action to reality through the capability gate.

    Issues and immediately spends its own capability for every commit, so the
    orchestrator's own path is gated exactly like a destructive MCP tool call —
    the capability layer is never bypassed for either ingress.
    """

    def __init__(self, engine: DemoProductionEngine, capability_store: CapabilityStore) -> None:
        self._engine = engine
        self._capability_store = capability_store

    async def apply(self, run: BranchpointRun, world: World) -> tuple[OperationReceipt, ...]:
        """Perform the approved action against reality and return its operation receipt(s)."""
        issued = await self._capability_store.issue_for_approved_run(run)
        return await self._engine.apply_to_reality(
            run=run,
            world=world,
            capability_store=self._capability_store,
            capability_token=issued.token,
        )


class DemoRealityVerifier:
    """Independently re-derives metrics from post-commit reality and checks recovery."""

    def __init__(self, engine: DemoProductionEngine) -> None:
        self._engine = engine

    async def verify(
        self, run: BranchpointRun, commit_receipt: CommitReceipt
    ) -> tuple[VerificationCheck, ...]:
        """Return post-commit checks against the current reality snapshot."""
        state = await self._engine.reality()
        checks = run_execution_suite(state) + run_compatibility_suite(state)
        return tuple(
            check_result_to_verification_check(
                check, evidence_id=f"{commit_receipt.commit_id}:{check.name}"
            )
            for check in checks
        )
