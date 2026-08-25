"""One-time commit capability: the security boundary for mutating demo reality.

BRANCHPOINT domain approval (:mod:`app.domain.approvals.rules`) remains the
authoritative decision about *which* world and action may reach reality. This
module adds defense in depth on top of that decision: even a caller who can
invoke the mutation code path directly — including through an MCP tool call
that bypasses the orchestrator entirely — cannot mutate reality without a
capability token that was issued for that exact run, world, action, and
action-content fingerprint, and every token can be spent exactly once.

Tokens are cryptographically random opaque strings (``secrets.token_urlsafe``),
never JWTs, never logged, and never returned by any read path — only the
issuing call sees the raw token, exactly once.
"""

import asyncio
import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from app.domain.errors import InvariantViolationError
from app.domain.primitives import new_id, utc_now
from app.domain.runs.lifecycle import RunStatus
from app.domain.runs.models import BranchpointRun
from app.domain.worlds.models import World, WorldVerdict

#: The orchestrator's own ``commit()`` step transitions a run to COMMITTING
#: *before* it calls the RealityMutator port, so by the time a capability is
#: issued from inside that call, the run is COMMITTING even though the
#: approval that authorized it was granted while the run was APPROVED. Both
#: are acceptable: Phase 1's own ``assert_commit_allowed`` already ran this
#: exact check with the stricter APPROVED-only requirement immediately before
#: invoking the mutator, so by construction the run reaching this point was
#: validated. This is a capability-issuance-time re-check, not a relaxation of
#: Phase 1's own invariant.
_COMMIT_ISSUABLE_RUN_STATUSES = frozenset({RunStatus.APPROVED, RunStatus.COMMITTING})


def _assert_commit_capability_issuable(run: BranchpointRun) -> World:
    """Validate a run/approval/world exactly like ``assert_commit_allowed``,
    except it also accepts a run that is already COMMITTING.

    Duplicated rather than reused because Phase 1's ``assert_commit_allowed``
    requires ``RunStatus.APPROVED`` specifically, and must keep requiring it —
    that function is what the orchestrator itself calls at the top of
    ``commit()``, before it moves the run to COMMITTING and only then invokes
    the RealityMutator port that issues this capability.
    """
    approval = run.approval
    if approval is None or not approval.is_granted:
        raise InvariantViolationError(
            "commit requires approval", f"run {run.run_id} has no granted approval"
        )
    if run.status not in _COMMIT_ISSUABLE_RUN_STATUSES:
        raise InvariantViolationError(
            "capability requires an approved or committing run",
            f"run {run.run_id} is {run.status}",
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


#: Default time-to-live for an issued capability before it can no longer be spent.
DEFAULT_CAPABILITY_TTL_SECONDS = 300.0

_TOKEN_SEPARATOR = "."


class CapabilityError(Exception):
    """Base class for capability validation failures. Never includes the raw token."""


class CapabilityNotFoundError(CapabilityError):
    """Raised when a token does not name a known capability."""

    def __init__(self) -> None:
        super().__init__("capability token is invalid or unknown")


class CapabilityExpiredError(CapabilityError):
    """Raised when a capability's time-to-live has elapsed."""

    def __init__(self, capability_id: str) -> None:
        super().__init__(f"capability {capability_id} has expired")
        self.capability_id = capability_id


class CapabilityAlreadyUsedError(CapabilityError):
    """Raised when a capability has already been spent. Tokens are single-use."""

    def __init__(self, capability_id: str) -> None:
        super().__init__(f"capability {capability_id} has already been used")
        self.capability_id = capability_id


class CapabilityMismatchError(CapabilityError):
    """Raised when a capability does not authorize the exact operation requested."""

    def __init__(self, capability_id: str, field: str) -> None:
        super().__init__(f"capability {capability_id} does not authorize this {field}")
        self.capability_id = capability_id
        self.field = field


class CommitCapability(BaseModel):
    """A one-time authorization to mutate reality with one exact action.

    Carries no secret material: only ``token_hash`` is stored, never the raw
    token, so a leaked capability record (e.g. in a debug endpoint) cannot be
    replayed.
    """

    model_config = ConfigDict(frozen=True)

    capability_id: str
    token_hash: str
    run_id: str
    world_id: str
    action_id: str
    action_fingerprint: str
    issued_at: datetime
    expires_at: datetime | None
    used_at: datetime | None = None

    _REDACTED: ClassVar[str] = "***redacted***"

    def __repr__(self) -> str:
        """Never let a capability's hash print in a way easily mistaken for a live token."""
        return (
            f"CommitCapability(capability_id={self.capability_id!r}, "
            f"run_id={self.run_id!r}, world_id={self.world_id!r}, "
            f"action_id={self.action_id!r}, token_hash={self._REDACTED})"
        )


class IssuedCapability(BaseModel):
    """The one-time result of issuing a capability: the record plus its raw token.

    The raw token exists only on this object, returned once by
    :meth:`CapabilityStore.issue_for_approved_run`. Nothing else in the system
    holds it in plaintext.
    """

    model_config = ConfigDict(frozen=True)

    capability: CommitCapability
    token: str

    def __repr__(self) -> str:
        """Prevent the raw token from leaking into logs via an unguarded repr/print."""
        return f"IssuedCapability(capability={self.capability!r}, token=***redacted***)"


def _hash_token(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


class CapabilityStore:
    """In-memory issuance and single-use redemption of commit capabilities."""

    def __init__(
        self,
        *,
        ttl_seconds: float | None = DEFAULT_CAPABILITY_TTL_SECONDS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._capabilities: dict[str, CommitCapability] = {}
        self._lock = asyncio.Lock()
        self._ttl_seconds = ttl_seconds
        self._clock = clock or utc_now

    async def issue_for_approved_run(self, run: BranchpointRun) -> IssuedCapability:
        """Issue a capability for the exact world/action a granted approval authorized.

        Validates the run with the same invariants as Phase 1's own
        ``assert_commit_allowed`` before issuing anything, so this can never
        authorize a mutation Phase 1 itself would refuse.
        """
        world = _assert_commit_capability_issuable(run)
        approval = run.approval
        assert approval is not None  # guaranteed by assert_commit_allowed

        secret = secrets.token_urlsafe(32)
        capability_id = new_id("cap")
        issued_at = self._clock()
        expires_at = issued_at + timedelta(seconds=self._ttl_seconds) if self._ttl_seconds else None
        capability = CommitCapability(
            capability_id=capability_id,
            token_hash=_hash_token(secret),
            run_id=run.run_id,
            world_id=world.world_id,
            action_id=world.candidate_action.action_id,
            action_fingerprint=approval.action_fingerprint,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        async with self._lock:
            self._capabilities[capability_id] = capability
        return IssuedCapability(
            capability=capability, token=f"{capability_id}{_TOKEN_SEPARATOR}{secret}"
        )

    async def peek(self, token: str) -> CommitCapability:
        """Look up the capability a token names, without spending it.

        Used by callers (e.g. MCP tools) that need to resolve which run/world a
        token refers to before deciding which mutation to attempt.
        """
        capability_id, secret = self._split_token(token)
        async with self._lock:
            capability = self._capabilities.get(capability_id)
        if capability is None or not hmac.compare_digest(
            capability.token_hash, _hash_token(secret)
        ):
            raise CapabilityNotFoundError
        return capability

    async def consume(
        self,
        token: str,
        *,
        run_id: str,
        world_id: str,
        action_id: str,
        action_fingerprint: str,
    ) -> CommitCapability:
        """Atomically validate and spend a capability for one exact mutation.

        Validates identity, expiry, single-use, and that the token authorizes
        exactly this run/world/action/fingerprint — all under one lock, so a
        concurrent redemption of the same token can never succeed twice.
        """
        capability_id, secret = self._split_token(token)
        now = self._clock()

        async with self._lock:
            capability = self._capabilities.get(capability_id)
            if capability is None or not hmac.compare_digest(
                capability.token_hash, _hash_token(secret)
            ):
                raise CapabilityNotFoundError
            if capability.used_at is not None:
                raise CapabilityAlreadyUsedError(capability_id)
            if capability.expires_at is not None and now > capability.expires_at:
                raise CapabilityExpiredError(capability_id)
            if capability.run_id != run_id:
                raise CapabilityMismatchError(capability_id, "run")
            if capability.world_id != world_id:
                raise CapabilityMismatchError(capability_id, "world")
            if capability.action_id != action_id:
                raise CapabilityMismatchError(capability_id, "action")
            if not hmac.compare_digest(capability.action_fingerprint, action_fingerprint):
                raise CapabilityMismatchError(capability_id, "action_fingerprint")

            spent = capability.model_copy(update={"used_at": now})
            self._capabilities[capability_id] = spent
            return spent

    @staticmethod
    def _split_token(token: str | None) -> tuple[str, str]:
        if not token:
            raise CapabilityNotFoundError
        capability_id, separator, secret = token.partition(_TOKEN_SEPARATOR)
        if not separator or not capability_id or not secret:
            raise CapabilityNotFoundError
        return capability_id, secret
