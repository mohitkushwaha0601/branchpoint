"""The typed counterexample language BRANCHPOINT accepts, and its replay engine.

A DOPPELGÄNGER may explore however it likes — reading world state, writing and
running throwaway code in a TrueForge sandbox — but none of that is
authoritative. The *only* thing BRANCHPOINT accepts as grounds for a veto is a
:class:`CounterexampleSpec`: a narrow, typed structure whose every operation
maps to a deterministic demo primitive. No shell, no SQL, no arbitrary paths,
no model-supplied Python. Replay happens against an isolated world snapshot and
can never touch reality.

The assertion in a spec states the property the attacker believes should hold.
Replay *reproduces* the counterexample when that property does not hold in the
target world — that is, when the attacker was right that the world breaks it.
"""

from enum import StrEnum

from pydantic import Field

from app.domain.evidence.models import Evidence, EvidenceKind, EvidenceSeverity
from app.domain.primitives import new_id, utc_now
from app.infrastructure.demo.metrics import compute_metrics
from app.infrastructure.demo.state import DemoModel, DemoProductionState, OrderRecord
from app.infrastructure.demo.workload import (
    CheckResult,
    CheckSeverity,
    data_integrity,
    deployment_supports_payment_revision,
    healthy_checkout,
    legacy_checkout,
    modern_checkout,
    recovery_slo,
)


class CounterexampleType(StrEnum):
    """The class of weakness an attack claims to have found."""

    COMPATIBILITY = "COMPATIBILITY"
    DATA_INTEGRITY = "DATA_INTEGRITY"
    METRIC = "METRIC"
    INVARIANT = "INVARIANT"


class CounterexampleOperation(StrEnum):
    """The deterministic demo primitive a spec replays.

    Each maps to an existing workload check or metric computation. There is no
    escape hatch, by design: an operation not in this enum cannot be replayed.
    """

    RETRY_PAYMENT = "RETRY_PAYMENT"
    DESERIALIZE_ORDER = "DESERIALIZE_ORDER"
    EXECUTE_CHECK = "EXECUTE_CHECK"
    ASSERT_METRIC = "ASSERT_METRIC"
    ASSERT_INVARIANT = "ASSERT_INVARIANT"


class AssertionKind(StrEnum):
    """How the asserted property is evaluated."""

    CHECK_PASSES = "CHECK_PASSES"
    METRIC_AT_MOST = "METRIC_AT_MOST"
    METRIC_AT_LEAST = "METRIC_AT_LEAST"


#: Workload checks a spec may name. Anything else is rejected at validation.
REPLAYABLE_CHECKS: dict[str, object] = {
    "healthy_checkout": healthy_checkout,
    "recovery_slo": recovery_slo,
    "data_integrity": data_integrity,
    "legacy_checkout": legacy_checkout,
    "modern_checkout": modern_checkout,
}

#: Metrics a spec may assert on. Anything else is rejected at validation.
ASSERTABLE_METRICS: frozenset[str] = frozenset(
    {
        "checkout_error_rate",
        "checkout_p95_ms",
        "pricing_timeout_rate",
        "affected_users",
        "daily_infra_cost_usd",
    }
)


class OrderSelector(DemoModel):
    """Which order the operation runs against.

    Selection is declarative and deterministic: given the same world snapshot,
    the same selector always resolves to the same order.
    """

    created_under_version: str | None = None
    min_schema_version: int | None = None
    order_id: str | None = None

    def select(self, state: DemoProductionState) -> OrderRecord | None:
        """Resolve this selector against ``state``, or return ``None``.

        Selection vocabulary is deliberately generic (version, schema version,
        id) rather than naming any particular field. An attacker has to work
        out for itself which records are interesting.
        """
        candidates = list(state.orders)
        if self.order_id is not None:
            candidates = [order for order in candidates if order.order_id == self.order_id]
        if self.created_under_version is not None:
            candidates = [
                order
                for order in candidates
                if order.created_under_version == self.created_under_version
            ]
        if self.min_schema_version is not None:
            candidates = [
                order for order in candidates if order.schema_version >= self.min_schema_version
            ]
        if not candidates:
            return None
        return min(candidates, key=lambda order: order.order_id)


class CounterexampleAssertion(DemoModel):
    """The property the attacker claims should hold."""

    kind: AssertionKind
    check_name: str | None = None
    metric: str | None = None
    threshold: float | None = None


class CounterexampleSpec(DemoModel):
    """A structured, replayable attack. The only authoritative veto input."""

    counterexample_type: CounterexampleType
    target_world_id: str = Field(min_length=1)
    operation: CounterexampleOperation
    assertion: CounterexampleAssertion
    expected: str = Field(min_length=1, max_length=500)
    rationale: str = Field(min_length=1, max_length=2000)
    setup: OrderSelector = Field(default_factory=OrderSelector)


class SpecValidationError(Exception):
    """Raised when a counterexample spec is not replayable as written."""


class ReproductionResult(DemoModel):
    """The outcome of replaying a spec against an isolated world snapshot."""

    reproduced: bool
    detail: str
    evidence: tuple[Evidence, ...] = ()


def validate_spec(spec: CounterexampleSpec) -> None:
    """Reject a spec whose operation and assertion cannot be replayed.

    Runs before any replay, so an unsupported check name or metric never
    reaches the engine.
    """
    assertion = spec.assertion
    if assertion.kind is AssertionKind.CHECK_PASSES:
        if not assertion.check_name:
            raise SpecValidationError("CHECK_PASSES requires assertion.check_name")
        if assertion.check_name not in REPLAYABLE_CHECKS:
            raise SpecValidationError(
                f"unknown check {assertion.check_name!r}; "
                f"replayable checks are {sorted(REPLAYABLE_CHECKS)}"
            )
        return

    if not assertion.metric:
        raise SpecValidationError(f"{assertion.kind} requires assertion.metric")
    if assertion.metric not in ASSERTABLE_METRICS:
        raise SpecValidationError(
            f"unknown metric {assertion.metric!r}; assertable metrics are {sorted(ASSERTABLE_METRICS)}"
        )
    if assertion.threshold is None:
        raise SpecValidationError(f"{assertion.kind} requires assertion.threshold")


def _compatibility_check(spec: CounterexampleSpec, state: DemoProductionState) -> CheckResult:
    """Replay a compatibility/payment-retry operation against a selected order."""
    order = spec.setup.select(state)
    version = state.pricing_deployment.version
    if order is None:
        return CheckResult(
            name=str(spec.operation).lower(),
            passed=True,
            expected=spec.expected,
            observed="no order in this world matches the spec's selector",
            severity=CheckSeverity.INFO,
            details="the attack's premise does not hold in this world",
        )

    supported = deployment_supports_payment_revision(version)
    if spec.operation is CounterexampleOperation.RETRY_PAYMENT:
        original_key = f"{order.order_id}:{order.payment_revision}"
        retry_key = original_key if supported else f"{order.order_id}:legacy"
        passed = retry_key == original_key
        observed = f"retry idempotency key == {retry_key!r}"
        details = (
            "retry recomputed a legacy dedupe key that does not match the original charge"
            if not passed
            else "retry recomputed the original payment_revision-derived dedupe key"
        )
    else:
        passed = supported
        observed = (
            f"pricing-service {version} cannot interpret payment_revision on {order.order_id}"
            if not passed
            else f"pricing-service {version} deserializes {order.order_id}"
        )
        details = "deployment schema support vs. the order's schema version"

    return CheckResult(
        name=str(spec.operation).lower(),
        passed=passed,
        expected=spec.expected,
        observed=observed,
        severity=CheckSeverity.INFO if passed else CheckSeverity.CRITICAL,
        details=details,
        artifact=f"order:{order.order_id}",
    )


def _metric_check(spec: CounterexampleSpec, state: DemoProductionState) -> CheckResult:
    """Replay a metric assertion against the world's derived metrics."""
    metrics = compute_metrics(state)
    assertion = spec.assertion
    assert assertion.metric is not None and assertion.threshold is not None  # validated
    value = float(getattr(metrics, assertion.metric))
    if assertion.kind is AssertionKind.METRIC_AT_MOST:
        passed = value <= assertion.threshold
        comparison = f"<= {assertion.threshold}"
    else:
        passed = value >= assertion.threshold
        comparison = f">= {assertion.threshold}"

    return CheckResult(
        name=f"assert_{assertion.metric}",
        passed=passed,
        expected=f"{assertion.metric} {comparison}",
        observed=f"{assertion.metric} = {value}",
        severity=CheckSeverity.INFO if passed else CheckSeverity.HIGH,
        details="metric derived deterministically from world state",
    )


def _named_check(spec: CounterexampleSpec, state: DemoProductionState) -> CheckResult:
    """Replay one of the named deterministic workload checks."""
    check_name = spec.assertion.check_name
    assert check_name is not None  # validated
    return REPLAYABLE_CHECKS[check_name](state)  # type: ignore[operator]


def reproduce(spec: CounterexampleSpec, state: DemoProductionState) -> ReproductionResult:
    """Replay ``spec`` against an isolated world snapshot.

    ``state`` must be a world snapshot, never reality — the caller is
    responsible for that, and nothing here can mutate what it is given
    (every demo state model is frozen).
    """
    validate_spec(spec)

    if spec.operation in (
        CounterexampleOperation.RETRY_PAYMENT,
        CounterexampleOperation.DESERIALIZE_ORDER,
    ):
        result = _compatibility_check(spec, state)
    elif spec.operation is CounterexampleOperation.EXECUTE_CHECK:
        result = _named_check(spec, state)
    else:
        result = _metric_check(spec, state)

    # The attacker asserted a property should hold. The counterexample is
    # reproduced exactly when the world violates it.
    reproduced = not result.passed
    evidence = (
        Evidence(
            evidence_id=new_id("evidence"),
            kind=(
                EvidenceKind.DATA_INTEGRITY
                if spec.counterexample_type
                in (CounterexampleType.COMPATIBILITY, CounterexampleType.DATA_INTEGRITY)
                else EvidenceKind.TEST_RESULT
            ),
            source="branchpoint-counterexample-replay",
            claim=f"{result.name}: {result.expected}",
            world_id=spec.target_world_id,
            observed=result.observed,
            expected=result.expected,
            passed=result.passed,
            severity=_evidence_severity(result.severity),
            machine_verifiable=True,
            artifact=result.artifact,
            recorded_at=utc_now(),
        ),
    )
    detail = (
        f"replay reproduced the counterexample: {result.observed}"
        if reproduced
        else f"replay did not reproduce the counterexample: {result.observed}"
    )
    return ReproductionResult(reproduced=reproduced, detail=detail, evidence=evidence)


def _evidence_severity(severity: CheckSeverity) -> EvidenceSeverity:
    return {
        CheckSeverity.INFO: EvidenceSeverity.INFO,
        CheckSeverity.LOW: EvidenceSeverity.LOW,
        CheckSeverity.MEDIUM: EvidenceSeverity.MEDIUM,
        CheckSeverity.HIGH: EvidenceSeverity.HIGH,
        CheckSeverity.CRITICAL: EvidenceSeverity.CRITICAL,
    }[severity]
