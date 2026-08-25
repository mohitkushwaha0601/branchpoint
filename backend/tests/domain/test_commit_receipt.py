"""Commit receipt completion semantics."""

from app.domain.commits.models import CommitReceipt, CommitStatus, OperationReceipt
from tests.factories import FIXED_TIME


def new_receipt() -> CommitReceipt:
    """Return a started commit receipt."""
    return CommitReceipt(
        commit_id="commit_1",
        run_id="run_1",
        world_id="world_1",
        action_id="action_1",
        action_fingerprint="fingerprint_1",
        started_at=FIXED_TIME,
    )


def test_commit_succeeds_when_every_operation_succeeds() -> None:
    receipt = new_receipt()

    completed = receipt.complete(
        (
            OperationReceipt(
                operation="disable_flag",
                target="pricing-service",
                succeeded=True,
                completed_at=FIXED_TIME,
            ),
        ),
        at=FIXED_TIME,
    )

    assert completed.status is CommitStatus.SUCCEEDED


def test_commit_fails_when_any_operation_fails() -> None:
    receipt = new_receipt()

    completed = receipt.complete(
        (
            OperationReceipt(
                operation="disable_flag",
                target="pricing-service",
                succeeded=True,
                completed_at=FIXED_TIME,
            ),
            OperationReceipt(
                operation="notify",
                target="pagerduty",
                succeeded=False,
                completed_at=FIXED_TIME,
            ),
        ),
        at=FIXED_TIME,
    )

    assert completed.status is CommitStatus.FAILED


def test_a_no_op_commit_with_no_operations_succeeds_vacuously() -> None:
    """A legitimate no-op commit — e.g. ActionType.NO_OP, or any action an
    adapter determines needs no work — must be representable as a success."""
    receipt = new_receipt()

    completed = receipt.complete((), at=FIXED_TIME)

    assert completed.status is CommitStatus.SUCCEEDED
    assert completed.operations == ()
