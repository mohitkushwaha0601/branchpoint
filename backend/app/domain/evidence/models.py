"""Evidence primitives.

Evidence is the currency of BRANCHPOINT: every consequential conclusion must be
traceable to evidence rather than to model confidence.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from app.domain.primitives import DomainModel, ScalarValue, utc_now


class EvidenceKind(StrEnum):
    """The category of check that produced a piece of evidence."""

    METRIC = "METRIC"
    TEST_RESULT = "TEST_RESULT"
    INVARIANT = "INVARIANT"
    COST = "COST"
    DATA_INTEGRITY = "DATA_INTEGRITY"
    EXECUTION_RESULT = "EXECUTION_RESULT"
    COUNTEREXAMPLE = "COUNTEREXAMPLE"
    POLICY = "POLICY"
    VERIFICATION = "VERIFICATION"


class EvidenceSeverity(StrEnum):
    """How serious a failing piece of evidence is."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Evidence(DomainModel):
    """A single machine-checkable (or human-supplied) observation about a world.

    ``passed`` carries the outcome of the check for the world that produced it:
    ``False`` means the claim did not hold. Only evidence with
    ``machine_verifiable=True`` may be used to disqualify a world.
    """

    evidence_id: str
    kind: EvidenceKind
    source: str
    claim: str
    world_id: str | None = None
    observed: ScalarValue = None
    expected: ScalarValue = None
    passed: bool | None = None
    severity: EvidenceSeverity = EvidenceSeverity.INFO
    machine_verifiable: bool = False
    artifact: str | None = None
    recorded_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _machine_verifiable_evidence_must_have_an_outcome(self) -> "Evidence":
        """A machine-verifiable check without a pass/fail outcome proves nothing."""
        if self.machine_verifiable and self.passed is None:
            raise ValueError("machine-verifiable evidence must set passed to True or False")
        return self

    @property
    def is_failing(self) -> bool:
        """Whether this evidence records a failed check."""
        return self.passed is False

    @property
    def disqualifies(self) -> bool:
        """Whether this evidence is strong enough to disqualify a world on its own."""
        return self.machine_verifiable and self.is_failing
