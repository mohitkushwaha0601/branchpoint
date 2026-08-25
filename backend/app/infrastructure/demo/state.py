"""Typed state for the checkout demo production environment.

This is BRANCHPOINT's Operational Digital Twin: a small, deterministic model of
a commerce production system (checkout-service, pricing-service, an orders
store, feature flags, capacity, and telemetry) used to demonstrate the Phase 1
domain end to end. It is demo-specific infrastructure, not core BRANCHPOINT
domain — the domain layer never imports anything from this package.

Every model here is frozen, so a snapshot can never be mutated in place; any
change produces a new ``DemoProductionState`` and the old one is untouched.
This is what makes world isolation structural rather than a deep-copy
convention that could silently be violated later.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DemoModel(BaseModel):
    """Immutable base for every demo state value object."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class ServiceDeployment(DemoModel):
    """The deployed version of a demo service."""

    service: str
    version: str
    previous_version: str | None
    deployed_at: datetime


class FeatureFlagState(DemoModel):
    """A demo feature flag."""

    key: str
    enabled: bool
    service: str


class ServiceCapacity(DemoModel):
    """Replica count and per-replica cost for a demo service."""

    service: str
    replicas: int = Field(ge=1)
    cost_per_replica_per_day: float = Field(ge=0.0)


class DatabaseState(DemoModel):
    """Baseline health of the orders database. Unaffected by any hero action."""

    latency_ms: float = Field(ge=0.0)


class CheckoutCapacity(DemoModel):
    """Baseline checkout-service CPU utilization. Unaffected by any hero action."""

    cpu_utilization: float = Field(ge=0.0, le=1.0)


class OrderRecord(DemoModel):
    """A synthetic order in the demo orders store.

    Orders created under ``v2.41`` may carry ``payment_revision`` — the field
    introduced in orders schema 41. A pricing-service deployment older than
    v2.41 has no code path that understands this field.
    """

    order_id: str
    created_under_version: str
    schema_version: int
    amount_cents: int = Field(ge=0)
    status: str
    payment_revision: str | None = None


class DemoProductionState(DemoModel):
    """One complete, deterministic snapshot of the demo production system."""

    pricing_deployment: ServiceDeployment
    pricing_flag: FeatureFlagState
    pricing_capacity: ServiceCapacity
    database: DatabaseState
    checkout_capacity: CheckoutCapacity
    orders_schema_version: int
    orders: tuple[OrderRecord, ...]
    snapshot_at: datetime
