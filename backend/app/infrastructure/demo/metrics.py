"""Deterministic metrics derived purely from :class:`DemoProductionState`.

Every number here is a pure function of state. Given identical state, these
functions return identical metrics — no randomness, no model call. The causal
story is:

- ``PRICING_V2`` enabled on ``v2.41`` activates a pricing regression that drives
  checkout errors and latency far out of SLO.
- Disabling the flag, or rolling the deployment back to ``v2.40``, bypasses the
  regression entirely (the buggy code path simply does not run).
- Adding pricing-service replicas partially mitigates the regression's damage
  (queueing pressure eases) but cannot remove it: a floor remains because the
  root cause is still deployed and enabled.
"""

from pydantic import BaseModel, ConfigDict, Field

from app.infrastructure.demo.state import DemoProductionState

#: Fixed daily volume of checkout attempts, used only to translate an error
#: rate into an "affected users" headline count.
DAILY_CHECKOUT_ATTEMPTS = 19_370

#: Checkout error rate at the baseline replica count when the regression is
#: active (v2.41 deployed and PRICING_V2 enabled).
REGRESSION_BASE_ERROR_RATE = 0.413
REGRESSION_BASE_P95_MS = 4800.0
REGRESSION_BASE_TIMEOUT_RATE = 0.35
REGRESSION_BASE_REPLICAS = 4

#: A replica beyond the baseline count eases queueing pressure but can never
#: fully remove the regression: both metrics have a floor.
ERROR_RATE_MITIGATION_PER_REPLICA = 0.043
ERROR_RATE_FLOOR = 0.07
LATENCY_MITIGATION_MS_PER_REPLICA = 480.0
LATENCY_FLOOR_MS = 960.0
TIMEOUT_RATE_MITIGATION_PER_REPLICA = 0.03
TIMEOUT_RATE_FLOOR = 0.05

#: Checkout error rate once the regression is bypassed, by which deployment
#: version is currently live. v2.40 predates the regression entirely; v2.41
#: with the flag disabled falls back to a slightly-older legacy pricing path.
BYPASSED_ERROR_RATE_BY_VERSION = {"v2.40": 0.018}
BYPASSED_ERROR_RATE_LEGACY_FLAG_OFF = 0.014
BYPASSED_P95_MS_BY_VERSION = {"v2.40": 190.0}
BYPASSED_P95_MS_LEGACY_FLAG_OFF = 320.0
BYPASSED_TIMEOUT_RATE = 0.02

#: Recovery targets used by the deterministic recovery_slo workload check.
RECOVERY_SLO_ERROR_RATE_THRESHOLD = 0.02
RECOVERY_SLO_P95_MS_THRESHOLD = 500.0
HEALTHY_CHECKOUT_ERROR_RATE_THRESHOLD = 0.02


class MetricsSnapshot(BaseModel):
    """Every headline metric, derived from one :class:`DemoProductionState`."""

    model_config = ConfigDict(frozen=True)

    regression_active: bool
    checkout_error_rate: float = Field(ge=0.0, le=1.0)
    checkout_p95_ms: float = Field(ge=0.0)
    pricing_timeout_rate: float = Field(ge=0.0, le=1.0)
    affected_users: int = Field(ge=0)
    database_latency_ms: float = Field(ge=0.0)
    checkout_cpu_utilization: float = Field(ge=0.0, le=1.0)
    pricing_cpu_utilization: float = Field(ge=0.0, le=1.0)
    daily_infra_cost_usd: float = Field(ge=0.0)


def is_regression_active(state: DemoProductionState) -> bool:
    """Whether the pricing regression is currently active.

    The regression is v2.41's own code: it can only run when v2.41 is deployed
    *and* the flag routes traffic through it.
    """
    return state.pricing_flag.enabled and state.pricing_deployment.version == "v2.41"


def _extra_replicas(state: DemoProductionState) -> int:
    return max(0, state.pricing_capacity.replicas - REGRESSION_BASE_REPLICAS)


def _checkout_error_rate(state: DemoProductionState, *, regression_active: bool) -> float:
    if regression_active:
        extra = _extra_replicas(state)
        mitigated = REGRESSION_BASE_ERROR_RATE - ERROR_RATE_MITIGATION_PER_REPLICA * extra
        return max(ERROR_RATE_FLOOR, mitigated)
    if state.pricing_deployment.version in BYPASSED_ERROR_RATE_BY_VERSION:
        return BYPASSED_ERROR_RATE_BY_VERSION[state.pricing_deployment.version]
    return BYPASSED_ERROR_RATE_LEGACY_FLAG_OFF


def _checkout_p95_ms(state: DemoProductionState, *, regression_active: bool) -> float:
    if regression_active:
        extra = _extra_replicas(state)
        mitigated = REGRESSION_BASE_P95_MS - LATENCY_MITIGATION_MS_PER_REPLICA * extra
        return max(LATENCY_FLOOR_MS, mitigated)
    if state.pricing_deployment.version in BYPASSED_P95_MS_BY_VERSION:
        return BYPASSED_P95_MS_BY_VERSION[state.pricing_deployment.version]
    return BYPASSED_P95_MS_LEGACY_FLAG_OFF


def _pricing_timeout_rate(state: DemoProductionState, *, regression_active: bool) -> float:
    if regression_active:
        extra = _extra_replicas(state)
        mitigated = REGRESSION_BASE_TIMEOUT_RATE - TIMEOUT_RATE_MITIGATION_PER_REPLICA * extra
        return max(TIMEOUT_RATE_FLOOR, mitigated)
    return BYPASSED_TIMEOUT_RATE


def _pricing_cpu_utilization(state: DemoProductionState, *, regression_active: bool) -> float:
    load = 0.75 if regression_active else 0.55
    scaled = load * (REGRESSION_BASE_REPLICAS / state.pricing_capacity.replicas)
    return min(0.92, scaled)


def compute_metrics(state: DemoProductionState) -> MetricsSnapshot:
    """Derive every headline metric from ``state``. Pure and deterministic."""
    regression_active = is_regression_active(state)
    error_rate = _checkout_error_rate(state, regression_active=regression_active)

    return MetricsSnapshot(
        regression_active=regression_active,
        checkout_error_rate=error_rate,
        checkout_p95_ms=_checkout_p95_ms(state, regression_active=regression_active),
        pricing_timeout_rate=_pricing_timeout_rate(state, regression_active=regression_active),
        affected_users=round(DAILY_CHECKOUT_ATTEMPTS * error_rate),
        database_latency_ms=state.database.latency_ms,
        checkout_cpu_utilization=state.checkout_capacity.cpu_utilization,
        pricing_cpu_utilization=_pricing_cpu_utilization(
            state, regression_active=regression_active
        ),
        daily_infra_cost_usd=state.pricing_capacity.replicas
        * state.pricing_capacity.cost_per_replica_per_day,
    )


def daily_cost_delta_usd(before: DemoProductionState, after: DemoProductionState) -> float:
    """Change in daily pricing-service infrastructure cost between two snapshots."""
    before_cost = (
        before.pricing_capacity.replicas * before.pricing_capacity.cost_per_replica_per_day
    )
    after_cost = after.pricing_capacity.replicas * after.pricing_capacity.cost_per_replica_per_day
    return after_cost - before_cost
