"""Candidate actions: proposed mutations of reality that have not been taken."""

import hashlib
import json
from enum import StrEnum

from pydantic import Field

from app.domain.primitives import DomainModel, ScalarValue


class ActionType(StrEnum):
    """The mechanism a candidate action would use."""

    ROLLBACK = "ROLLBACK"
    FEATURE_FLAG_DISABLE = "FEATURE_FLAG_DISABLE"
    FEATURE_FLAG_ENABLE = "FEATURE_FLAG_ENABLE"
    SCALE = "SCALE"
    CONFIG_CHANGE = "CONFIG_CHANGE"
    RESTART = "RESTART"
    TRAFFIC_SHIFT = "TRAFFIC_SHIFT"
    DATA_REPAIR = "DATA_REPAIR"
    NO_OP = "NO_OP"


class RiskClass(StrEnum):
    """Declared risk of performing the action against reality."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ActionSourceKind(StrEnum):
    """Who proposed the action."""

    HUMAN = "HUMAN"
    PLANNER = "PLANNER"
    POLICY = "POLICY"


class ActionSource(DomainModel):
    """Provenance of a candidate action."""

    kind: ActionSourceKind
    name: str
    rationale: str = ""


class ActionTarget(DomainModel):
    """What the action would mutate."""

    service: str
    component: str | None = None
    environment: str = "production"


class CandidateAction(DomainModel):
    """A proposed mutation of reality.

    A candidate action is inert: it describes what *would* be done and never
    executes anything itself.
    """

    action_id: str
    name: str
    description: str
    action_type: ActionType
    target: ActionTarget
    expected_outcome: str
    risk_class: RiskClass
    reversible: bool
    source: ActionSource
    parameters: dict[str, ScalarValue] = Field(default_factory=dict)

    def fingerprint(self) -> str:
        """Return a deterministic content hash binding an approval to this exact action.

        Any change to the action — including its parameters — changes the
        fingerprint, so an approval cannot be silently transferred to a
        different action.
        """
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
