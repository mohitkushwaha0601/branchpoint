"""Converts demo :class:`CheckResult` objects into Phase 1 domain contracts.

This is the only place demo infrastructure touches ``app.domain`` evidence
types, so the conversion rule lives in one spot rather than being duplicated
wherever a check result needs to become ``Evidence``.
"""

from app.domain.evidence.models import Evidence, EvidenceKind, EvidenceSeverity
from app.domain.primitives import new_id, utc_now
from app.domain.verification.models import VerificationCheck
from app.infrastructure.demo.workload import CheckResult, CheckSeverity

_SEVERITY_MAP: dict[CheckSeverity, EvidenceSeverity] = {
    CheckSeverity.INFO: EvidenceSeverity.INFO,
    CheckSeverity.LOW: EvidenceSeverity.LOW,
    CheckSeverity.MEDIUM: EvidenceSeverity.MEDIUM,
    CheckSeverity.HIGH: EvidenceSeverity.HIGH,
    CheckSeverity.CRITICAL: EvidenceSeverity.CRITICAL,
}

#: Checks whose failure represents a data/schema integrity break rather than a
#: plain assertion failure. This drives which ``EvidenceKind`` they become.
_DATA_INTEGRITY_CHECK_NAMES = frozenset(
    {"order_deserialization_or_compatibility", "payment_retry", "data_integrity"}
)


def check_result_to_evidence(
    result: CheckResult, *, source: str, world_id: str | None = None
) -> Evidence:
    """Convert one deterministic :class:`CheckResult` into machine-verifiable ``Evidence``."""
    kind = (
        EvidenceKind.DATA_INTEGRITY
        if result.name in _DATA_INTEGRITY_CHECK_NAMES
        else EvidenceKind.TEST_RESULT
    )
    return Evidence(
        evidence_id=new_id("evidence"),
        kind=kind,
        source=source,
        claim=f"{result.name}: {result.expected}",
        world_id=world_id,
        observed=result.observed,
        expected=result.expected,
        passed=result.passed,
        severity=_SEVERITY_MAP[result.severity],
        machine_verifiable=True,
        artifact=result.artifact,
        recorded_at=utc_now(),
    )


def check_result_to_verification_check(result: CheckResult, evidence_id: str) -> VerificationCheck:
    """Convert one deterministic :class:`CheckResult` into a post-commit ``VerificationCheck``."""
    return VerificationCheck(
        key=result.name,
        description=result.expected,
        passed=result.passed,
        observed=result.observed,
        expected=result.expected,
        evidence_id=evidence_id,
    )
