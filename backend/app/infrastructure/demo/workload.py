"""Deterministic executable checks against demo production state.

Every check is a pure function of state (plus, for the compatibility checks,
one order). None of them know or care which ``CandidateAction`` produced the
state they are checking — the same functions run against reality, world alpha,
world beta, and world gamma alike, and only fail where the state actually
fails them. This is what keeps the hero scenario honest rather than scripted.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.infrastructure.demo.metrics import (
    HEALTHY_CHECKOUT_ERROR_RATE_THRESHOLD,
    RECOVERY_SLO_ERROR_RATE_THRESHOLD,
    RECOVERY_SLO_P95_MS_THRESHOLD,
    MetricsSnapshot,
    compute_metrics,
)
from app.infrastructure.demo.state import DemoProductionState, OrderRecord

#: The orders schema version that introduced ``payment_revision``. A
#: pricing-service deployment older than this cannot interpret the field.
PAYMENT_REVISION_INTRODUCED_IN_SCHEMA = 41

#: Deployment version -> highest orders schema it understands.
DEPLOYMENT_SCHEMA_SUPPORT: dict[str, int] = {"v2.40": 40, "v2.41": 41}


class CheckSeverity(StrEnum):
    """How serious a failing check is."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class CheckResult(BaseModel):
    """The typed result of one deterministic workload/regression check."""

    model_config = ConfigDict(frozen=True)

    name: str
    passed: bool
    expected: str
    observed: str
    severity: CheckSeverity
    details: str = ""
    artifact: str | None = None


def deployment_supports_payment_revision(version: str) -> bool:
    """Whether ``version`` can interpret the ``payment_revision`` field."""
    supported_schema = DEPLOYMENT_SCHEMA_SUPPORT.get(version, 0)
    return supported_schema >= PAYMENT_REVISION_INTRODUCED_IN_SCHEMA


def healthy_checkout(state: DemoProductionState) -> CheckResult:
    """Whether checkout is currently within a basic health threshold."""
    metrics = compute_metrics(state)
    passed = metrics.checkout_error_rate <= HEALTHY_CHECKOUT_ERROR_RATE_THRESHOLD
    return CheckResult(
        name="healthy_checkout",
        passed=passed,
        expected=f"checkout_error_rate <= {HEALTHY_CHECKOUT_ERROR_RATE_THRESHOLD:.3f}",
        observed=f"checkout_error_rate = {metrics.checkout_error_rate:.4f}",
        severity=CheckSeverity.INFO if passed else CheckSeverity.MEDIUM,
        details="Aggregate checkout error rate measured against the basic health threshold.",
    )


def recovery_slo(state: DemoProductionState) -> CheckResult:
    """Whether checkout meets both the error-rate and latency recovery SLO."""
    metrics = compute_metrics(state)
    error_ok = metrics.checkout_error_rate <= RECOVERY_SLO_ERROR_RATE_THRESHOLD
    latency_ok = metrics.checkout_p95_ms <= RECOVERY_SLO_P95_MS_THRESHOLD
    passed = error_ok and latency_ok
    return CheckResult(
        name="recovery_slo",
        passed=passed,
        expected=(
            f"checkout_error_rate <= {RECOVERY_SLO_ERROR_RATE_THRESHOLD:.3f} "
            f"and checkout_p95_ms <= {RECOVERY_SLO_P95_MS_THRESHOLD:.0f}"
        ),
        observed=(
            f"checkout_error_rate = {metrics.checkout_error_rate:.4f}, "
            f"checkout_p95_ms = {metrics.checkout_p95_ms:.1f}"
        ),
        severity=CheckSeverity.INFO if passed else CheckSeverity.MEDIUM,
        details="Recovery is defined as meeting both the error-rate and p95 latency SLO together.",
    )


def data_integrity(state: DemoProductionState) -> CheckResult:
    """Baseline orders-store sanity: no negative amounts, no duplicate ids."""
    order_ids = [order.order_id for order in state.orders]
    no_duplicates = len(order_ids) == len(set(order_ids))
    no_negative_amounts = all(order.amount_cents >= 0 for order in state.orders)
    passed = no_duplicates and no_negative_amounts
    return CheckResult(
        name="data_integrity",
        passed=passed,
        expected="orders store has unique order ids and non-negative amounts",
        observed=f"{len(state.orders)} order(s), duplicates={not no_duplicates}",
        severity=CheckSeverity.INFO if passed else CheckSeverity.CRITICAL,
        details="Baseline orders-store sanity, independent of pricing-service version.",
    )


def legacy_checkout(state: DemoProductionState) -> CheckResult:
    """Whether the legacy (pre-v2.41) checkout path is currently in use and healthy."""
    metrics = compute_metrics(state)
    on_legacy_path = state.pricing_deployment.version == "v2.40" or not state.pricing_flag.enabled
    passed = on_legacy_path and metrics.checkout_error_rate <= HEALTHY_CHECKOUT_ERROR_RATE_THRESHOLD
    return CheckResult(
        name="legacy_checkout",
        passed=passed,
        expected="legacy pricing path in use and within health threshold",
        observed=(
            f"version={state.pricing_deployment.version}, "
            f"flag_enabled={state.pricing_flag.enabled}, "
            f"checkout_error_rate={metrics.checkout_error_rate:.4f}"
        ),
        severity=CheckSeverity.INFO if passed else CheckSeverity.LOW,
        details="Exercises the pre-v2.41 checkout code path specifically.",
    )


def modern_checkout(state: DemoProductionState) -> CheckResult:
    """Whether the modern (v2.41, flag-on) checkout path is currently in use and healthy."""
    metrics = compute_metrics(state)
    on_modern_path = state.pricing_deployment.version == "v2.41" and state.pricing_flag.enabled
    passed = on_modern_path and metrics.checkout_error_rate <= HEALTHY_CHECKOUT_ERROR_RATE_THRESHOLD
    return CheckResult(
        name="modern_checkout",
        passed=passed,
        expected="modern pricing path in use and within health threshold",
        observed=(
            f"version={state.pricing_deployment.version}, "
            f"flag_enabled={state.pricing_flag.enabled}, "
            f"checkout_error_rate={metrics.checkout_error_rate:.4f}"
        ),
        severity=CheckSeverity.INFO if passed else CheckSeverity.LOW,
        details="Exercises the v2.41 checkout code path specifically.",
    )


def _select_payment_revision_order(state: DemoProductionState) -> OrderRecord | None:
    """Return a deterministic order created under v2.41 with ``payment_revision`` set."""
    candidates = tuple(
        order
        for order in state.orders
        if order.created_under_version == "v2.41" and order.payment_revision is not None
    )
    if not candidates:
        return None
    return min(candidates, key=lambda order: order.order_id)


def order_deserialization_or_compatibility(state: DemoProductionState) -> CheckResult:
    """Whether the active pricing-service deployment can interpret a v2.41 order.

    This is the executable regression that makes rollback dangerous: v2.40's
    order reader has no ``payment_revision`` field in its known schema, so it
    cannot deserialize an order that carries one.
    """
    order = _select_payment_revision_order(state)
    if order is None:
        return CheckResult(
            name="order_deserialization_or_compatibility",
            passed=True,
            expected="every v2.41-created order deserializes under the active deployment",
            observed="no v2.41-created order with payment_revision exists in this snapshot",
            severity=CheckSeverity.INFO,
        )

    version = state.pricing_deployment.version
    compatible = deployment_supports_payment_revision(version)
    return CheckResult(
        name="order_deserialization_or_compatibility",
        passed=compatible,
        expected=f"pricing-service {version} deserializes order {order.order_id} (schema {order.schema_version})",
        observed=(
            f"pricing-service {version} supports orders schema up to "
            f"{DEPLOYMENT_SCHEMA_SUPPORT.get(version, 0)}; order requires schema {order.schema_version}"
        ),
        severity=CheckSeverity.INFO if compatible else CheckSeverity.CRITICAL,
        details=(
            "order.payment_revision is unrepresentable to a deployment older than v2.41"
            if not compatible
            else "deployment schema support covers this order's payment_revision field"
        ),
        artifact=f"order:{order.order_id}",
    )


def payment_retry(state: DemoProductionState) -> CheckResult:
    """Whether retrying payment on a v2.41 order is safely idempotent under the active deployment.

    The original charge was deduped using a key derived from
    ``payment_revision``. A deployment that cannot read that field falls back
    to a legacy dedupe key, so a retry is misclassified as a new payment.
    """
    order = _select_payment_revision_order(state)
    if order is None:
        return CheckResult(
            name="payment_retry",
            passed=True,
            expected="payment retry is idempotent",
            observed="no v2.41-created order with payment_revision exists in this snapshot",
            severity=CheckSeverity.INFO,
        )

    version = state.pricing_deployment.version
    original_key = f"{order.order_id}:{order.payment_revision}"
    retry_key = (
        original_key
        if deployment_supports_payment_revision(version)
        else f"{order.order_id}:legacy"
    )
    idempotent = retry_key == original_key
    return CheckResult(
        name="payment_retry",
        passed=idempotent,
        expected=f"retry idempotency key == {original_key!r}",
        observed=f"retry idempotency key == {retry_key!r}",
        severity=CheckSeverity.INFO if idempotent else CheckSeverity.CRITICAL,
        details=(
            "retry recomputed a legacy dedupe key that does not match the original charge, "
            "so the retry would be charged as a new payment"
            if not idempotent
            else "retry recomputed the same payment_revision-derived dedupe key as the original charge"
        ),
        artifact=f"order:{order.order_id}",
    )


def run_execution_suite(state: DemoProductionState) -> tuple[CheckResult, ...]:
    """Checks run at world-execution time: aggregate metrics only, no order inspection."""
    return (healthy_checkout(state), recovery_slo(state), data_integrity(state))


def run_compatibility_suite(state: DemoProductionState) -> tuple[CheckResult, ...]:
    """Checks that specifically probe v2.41 order compatibility against the active deployment.

    Reserved for the adversarial/attack phase, not ordinary execution: this is
    the check a DOPPELGÄNGER runs to try to invalidate a candidate.
    """
    return (order_deserialization_or_compatibility(state), payment_retry(state))


__all__ = [
    "MetricsSnapshot",
    "deployment_supports_payment_revision",
    "CheckResult",
    "CheckSeverity",
    "healthy_checkout",
    "recovery_slo",
    "data_integrity",
    "legacy_checkout",
    "modern_checkout",
    "order_deserialization_or_compatibility",
    "payment_retry",
    "run_execution_suite",
    "run_compatibility_suite",
]
