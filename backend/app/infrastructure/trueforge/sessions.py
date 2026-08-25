"""Mapping between BRANCHPOINT domain ids and TrueForge session ids.

BRANCHPOINT does not store conversations, turns, or events of its own —
TrueForge already persists all of that (SQLite in standalone mode). This module
stores only the minimum needed to reconnect a domain run or world to the
TrueForge session that reasoned about it, so a run can be resumed after a
restart without BRANCHPOINT rebuilding session storage.

The binding lives in infrastructure on purpose: no TrueForge identifier ever
appears on a domain model.
"""

import asyncio
from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.domain.primitives import utc_now


class SessionPurpose(StrEnum):
    """What a bound TrueForge session was created to do."""

    PLANNER = "PLANNER"
    ADVERSARY = "ADVERSARY"
    COMMIT_OPERATOR = "COMMIT_OPERATOR"


class SessionStatus(StrEnum):
    """Lifecycle of a binding, independent of TrueForge's own turn state."""

    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TrueForgeSessionBinding(BaseModel):
    """One BRANCHPOINT run/world bound to one TrueForge session.

    ``last_turn_id`` and ``pending_tool_call_id`` are audit metadata: they let a
    resumed process find the exact paused tool call again instead of starting a
    new turn and risking a duplicate commit.
    """

    model_config = ConfigDict(frozen=True)

    run_id: str
    purpose: SessionPurpose
    trueforge_session_id: str
    created_at: datetime
    updated_at: datetime
    world_id: str | None = None
    status: SessionStatus = SessionStatus.ACTIVE
    last_turn_id: str | None = None
    pending_thread_id: str | None = None
    pending_tool_call_id: str | None = None


class InMemorySessionBindingStore:
    """In-memory binding store.

    Matches the rest of the backend's current persistence. The interface is
    deliberately storage-shaped (``upsert``/``get``/``list_for_run``) so a real
    table can replace it without touching callers.
    """

    def __init__(self) -> None:
        self._bindings: dict[tuple[str, str | None, SessionPurpose], TrueForgeSessionBinding] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _key(
        run_id: str, world_id: str | None, purpose: SessionPurpose
    ) -> tuple[str, str | None, SessionPurpose]:
        return (run_id, world_id, purpose)

    async def upsert(
        self,
        *,
        run_id: str,
        purpose: SessionPurpose,
        trueforge_session_id: str,
        world_id: str | None = None,
        status: SessionStatus = SessionStatus.ACTIVE,
        last_turn_id: str | None = None,
        pending_thread_id: str | None = None,
        pending_tool_call_id: str | None = None,
    ) -> TrueForgeSessionBinding:
        """Create or update the binding for one run/world/purpose."""
        now = utc_now()
        key = self._key(run_id, world_id, purpose)
        async with self._lock:
            existing = self._bindings.get(key)
            binding = TrueForgeSessionBinding(
                run_id=run_id,
                world_id=world_id,
                purpose=purpose,
                trueforge_session_id=trueforge_session_id,
                status=status,
                last_turn_id=last_turn_id,
                pending_thread_id=pending_thread_id,
                pending_tool_call_id=pending_tool_call_id,
                created_at=existing.created_at if existing else now,
                updated_at=now,
            )
            self._bindings[key] = binding
            return binding

    async def get(
        self, run_id: str, purpose: SessionPurpose, world_id: str | None = None
    ) -> TrueForgeSessionBinding | None:
        """Return the binding for one run/world/purpose, or ``None``."""
        async with self._lock:
            return self._bindings.get(self._key(run_id, world_id, purpose))

    async def list_for_run(self, run_id: str) -> Sequence[TrueForgeSessionBinding]:
        """Return every binding belonging to ``run_id``, oldest first."""
        async with self._lock:
            bindings = [b for b in self._bindings.values() if b.run_id == run_id]
        return sorted(bindings, key=lambda b: (b.created_at, b.purpose, b.world_id or ""))
