"""Independent verification of reality after a commit.

A successful commit only proves the mutation was applied. Verification asks the
separate question of whether reality actually recovered.
"""

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum

from app.domain.primitives import DomainModel, ScalarValue


class VerificationStatus(StrEnum):
    """Outcome of post-commit verification."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    INCONCLUSIVE = "INCONCLUSIVE"


class VerificationCheck(DomainModel):
    """One post-commit check against reality.

    ``passed`` is ``None`` when the check could not be evaluated.
    """

    key: str
    description: str
    passed: bool | None = None
    observed: ScalarValue = None
    expected: ScalarValue = None
    evidence_id: str | None = None


class VerificationResult(DomainModel):
    """The aggregate result of verifying reality after a commit."""

    verification_id: str
    run_id: str
    commit_id: str
    status: VerificationStatus
    started_at: datetime
    completed_at: datetime
    checks: tuple[VerificationCheck, ...] = ()
    evidence_ids: tuple[str, ...] = ()


def derive_verification_status(checks: Sequence[VerificationCheck]) -> VerificationStatus:
    """Derive a verification status deterministically from its checks."""
    if not checks:
        return VerificationStatus.INCONCLUSIVE
    if any(check.passed is False for check in checks):
        return VerificationStatus.FAILED
    if any(check.passed is None for check in checks):
        return VerificationStatus.INCONCLUSIVE
    return VerificationStatus.PASSED
