"""The real-world condition that starts a run, and the observed state of reality."""

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.domain.primitives import DomainModel


class IncidentSeverity(StrEnum):
    """How urgent the triggering condition is."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class MetricDirection(StrEnum):
    """Which direction of a metric counts as an improvement."""

    HIGHER_IS_BETTER = "HIGHER_IS_BETTER"
    LOWER_IS_BETTER = "LOWER_IS_BETTER"


class MetricObservation(DomainModel):
    """A measured metric with an optional baseline and breach threshold."""

    name: str
    value: float
    observed_at: datetime
    unit: str = ""
    baseline: float | None = None
    threshold: float | None = None
    direction: MetricDirection = MetricDirection.LOWER_IS_BETTER

    @property
    def breaches_threshold(self) -> bool:
        """Whether the measured value is on the wrong side of its threshold."""
        if self.threshold is None:
            return False
        if self.direction is MetricDirection.LOWER_IS_BETTER:
            return self.value > self.threshold
        return self.value < self.threshold


class DeploymentState(DomainModel):
    """The deployed version of a service at observation time."""

    service: str
    version: str
    deployed_at: datetime
    previous_version: str | None = None
    rollback_available: bool = True


class FeatureFlagState(DomainModel):
    """A feature flag and its rollout at observation time."""

    key: str
    enabled: bool
    service: str | None = None
    rollout_percentage: float | None = None


class ServiceState(DomainModel):
    """Health of a single service at observation time."""

    name: str
    healthy: bool
    version: str | None = None
    replicas: int | None = None
    error_rate: float | None = None


class InvariantStatement(DomainModel):
    """A named property of reality that must keep holding.

    ``holds`` is ``None`` when the invariant has not been evaluated.
    """

    key: str
    description: str
    holds: bool | None = None


class ObservedState(DomainModel):
    """Structured observations of reality, not free-form prose."""

    observed_at: datetime
    source: str
    metrics: tuple[MetricObservation, ...] = ()
    deployments: tuple[DeploymentState, ...] = ()
    feature_flags: tuple[FeatureFlagState, ...] = ()
    services: tuple[ServiceState, ...] = ()
    invariants: tuple[InvariantStatement, ...] = ()
    metadata: dict[str, str] = Field(default_factory=dict)

    @property
    def breached_metrics(self) -> tuple[MetricObservation, ...]:
        """Metrics currently on the wrong side of their threshold."""
        return tuple(metric for metric in self.metrics if metric.breaches_threshold)

    @property
    def violated_invariants(self) -> tuple[InvariantStatement, ...]:
        """Invariants known not to hold in observed reality."""
        return tuple(invariant for invariant in self.invariants if invariant.holds is False)


class Incident(DomainModel):
    """The condition that caused a BRANCHPOINT run to be opened."""

    incident_id: str
    title: str
    goal: str
    severity: IncidentSeverity
    detected_at: datetime
    description: str = ""
    affected_services: tuple[str, ...] = ()
    metadata: dict[str, str] = Field(default_factory=dict)
