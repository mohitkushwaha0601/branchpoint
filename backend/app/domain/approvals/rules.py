"""Invariants guarding the transition from counterfactual to reality.

No consequential action reaches reality until it survives an adversarial
counterfactual and receives explicit approval.
"""

from datetime import datetime

from app.domain.approvals.models import Approval
from app.domain.errors import InvariantViolationError
from app.domain.runs.lifecycle import RunStatus
from app.domain.runs.models import BranchpointRun
from app.domain.worlds.models import World, WorldVerdict


def build_approval_request(
    run: BranchpointRun, world_id: str, *, approval_id: str, requested_at: datetime
) -> Approval:
    """Create a pending approval for one surviving, eligible world.

    Enforces that approval can only be requested after deterministic comparison,
    only for a world that survived, only for a world comparison found eligible,
    and only once per run.
    """
    if run.comparison is None or run.status is not RunStatus.COMPARING:
        raise InvariantViolationError(
            "approval follows comparison",
            f"run {run.run_id} must be COMPARING with a comparison result, is {run.status}",
        )
    if run.approval is not None:
        raise InvariantViolationError(
            "one approval per run",
            f"run {run.run_id} already has approval {run.approval.approval_id}",
        )

    world = run.require_world(world_id)
    if world.verdict is not WorldVerdict.SURVIVED:
        raise InvariantViolationError(
            "only surviving worlds may be selected",
            f"world {world_id} has verdict {world.verdict}",
        )
    if world_id not in run.comparison.eligible_world_ids:
        raise InvariantViolationError(
            "only eligible worlds may be selected",
            f"world {world_id} was rejected by deterministic comparison",
        )

    return Approval(
        approval_id=approval_id,
        run_id=run.run_id,
        selected_world_id=world_id,
        action_id=world.candidate_action.action_id,
        action_fingerprint=world.candidate_action.fingerprint(),
        requested_at=requested_at,
    )


def assert_commit_allowed(run: BranchpointRun) -> World:
    """Return the world that may be committed, or raise.

    A commit requires a granted approval that still binds the exact world and
    the exact action content that was approved.
    """
    approval = run.approval
    if approval is None or not approval.is_granted:
        raise InvariantViolationError(
            "commit requires approval",
            f"run {run.run_id} has no granted approval",
        )
    if run.status is not RunStatus.APPROVED:
        raise InvariantViolationError(
            "commit requires approved run",
            f"run {run.run_id} is {run.status}, expected {RunStatus.APPROVED}",
        )
    if run.selected_world_id != approval.selected_world_id:
        raise InvariantViolationError(
            "approval binds the selected world",
            f"run selects {run.selected_world_id}, approval selects {approval.selected_world_id}",
        )

    world = run.require_world(approval.selected_world_id)
    if world.verdict is not WorldVerdict.SURVIVED:
        raise InvariantViolationError(
            "only surviving worlds may be committed",
            f"world {world.world_id} has verdict {world.verdict}",
        )
    if world.candidate_action.action_id != approval.action_id:
        raise InvariantViolationError(
            "approval binds the exact action",
            f"world {world.world_id} now carries action {world.candidate_action.action_id}",
        )
    if world.candidate_action.fingerprint() != approval.action_fingerprint:
        raise InvariantViolationError(
            "approval is not transferable",
            f"action {approval.action_id} changed after it was approved",
        )
    return world
