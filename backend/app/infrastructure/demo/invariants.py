"""The invariants and SLOs BRANCHPOINT itself declares.

An adversary chooses *which* invariant to test. It never chooses what that
invariant says. Every threshold below belongs to BRANCHPOINT, is defined
alongside the metric it constrains, and is applied by the replay engine
regardless of what a model submitted — so an attacker cannot invent the
requirement it then "proves" was violated.

This is the boundary that keeps a veto meaningful. Relative quality — one world
recovering further than another, costing less, or touching fewer services — is
a *comparator* concern and is deliberately unrepresentable here: nothing in this
registry can reference a second world.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from app.infrastructure.demo.metrics import (
    RECOVERY_SLO_ERROR_RATE_THRESHOLD,
    RECOVERY_SLO_P95_MS_THRESHOLD,
)
from app.infrastructure.demo.state import DemoProductionState
from app.infrastructure.demo.workload import (
    CheckResult,
    data_integrity,
    order_deserialization_or_compatibility,
    payment_retry,
)


class DeclaredInvariant(StrEnum):
    """The hard invariants and SLOs a counterexample may assert against."""

    RECOVERY_ERROR_RATE_SLO = "RECOVERY_ERROR_RATE_SLO"
    RECOVERY_LATENCY_SLO = "RECOVERY_LATENCY_SLO"
    DATA_INTEGRITY = "DATA_INTEGRITY"
    PAYMENT_IDEMPOTENCY = "PAYMENT_IDEMPOTENCY"
    SCHEMA_COMPATIBILITY = "SCHEMA_COMPATIBILITY"


class MetricBound(StrEnum):
    """The direction in which a declared metric threshold binds."""

    AT_MOST = "AT_MOST"
    AT_LEAST = "AT_LEAST"


@dataclass(frozen=True)
class MetricInvariant:
    """A declared bound on one derived metric, with BRANCHPOINT's own threshold."""

    invariant: DeclaredInvariant
    metric: str
    bound: MetricBound
    threshold: float
    description: str


@dataclass(frozen=True)
class CheckInvariant:
    """A declared invariant evaluated by a deterministic workload check."""

    invariant: DeclaredInvariant
    check: Callable[[DemoProductionState], CheckResult]
    description: str


#: Declared metric SLOs. The threshold is BRANCHPOINT's, taken from the same
#: constants the ordinary execution suite measures against, so a counterexample
#: and a routine check can never disagree about what "recovered" means.
METRIC_INVARIANTS: dict[DeclaredInvariant, MetricInvariant] = {
    DeclaredInvariant.RECOVERY_ERROR_RATE_SLO: MetricInvariant(
        invariant=DeclaredInvariant.RECOVERY_ERROR_RATE_SLO,
        metric="checkout_error_rate",
        bound=MetricBound.AT_MOST,
        threshold=RECOVERY_SLO_ERROR_RATE_THRESHOLD,
        description="checkout error rate must meet the recovery SLO",
    ),
    DeclaredInvariant.RECOVERY_LATENCY_SLO: MetricInvariant(
        invariant=DeclaredInvariant.RECOVERY_LATENCY_SLO,
        metric="checkout_p95_ms",
        bound=MetricBound.AT_MOST,
        threshold=RECOVERY_SLO_P95_MS_THRESHOLD,
        description="checkout p95 latency must meet the recovery SLO",
    ),
}

#: Declared invariants evaluated by a named deterministic check rather than a
#: numeric bound. These have no threshold to invent in the first place.
CHECK_INVARIANTS: dict[DeclaredInvariant, CheckInvariant] = {
    DeclaredInvariant.DATA_INTEGRITY: CheckInvariant(
        invariant=DeclaredInvariant.DATA_INTEGRITY,
        check=data_integrity,
        description="the orders store stays internally consistent",
    ),
    DeclaredInvariant.PAYMENT_IDEMPOTENCY: CheckInvariant(
        invariant=DeclaredInvariant.PAYMENT_IDEMPOTENCY,
        check=payment_retry,
        description="retrying a payment cannot charge twice",
    ),
    DeclaredInvariant.SCHEMA_COMPATIBILITY: CheckInvariant(
        invariant=DeclaredInvariant.SCHEMA_COMPATIBILITY,
        check=order_deserialization_or_compatibility,
        description="every existing order stays readable by the active deployment",
    ),
}


def metric_invariant_for(metric: str) -> MetricInvariant | None:
    """Return the declared invariant bounding ``metric``, or ``None``.

    ``None`` means BRANCHPOINT declares no threshold for that metric, so no
    counterexample can assert one: the metric is observable and comparable, but
    not by itself grounds for a veto.
    """
    for definition in METRIC_INVARIANTS.values():
        if definition.metric == metric:
            return definition
    return None


#: Every metric BRANCHPOINT declares a threshold for.
CONSTRAINED_METRICS: frozenset[str] = frozenset(
    definition.metric for definition in METRIC_INVARIANTS.values()
)


__all__ = [
    "CHECK_INVARIANTS",
    "CONSTRAINED_METRICS",
    "METRIC_INVARIANTS",
    "CheckInvariant",
    "DeclaredInvariant",
    "MetricBound",
    "MetricInvariant",
    "metric_invariant_for",
]
