"""Assembling one run's TrueForge harness trace.

The session ids come from BRANCHPOINT's own binding store, so a trace can only
ever describe sessions this run actually created — a caller cannot ask for
someone else's session by naming it.

TrueForge being down degrades the answer rather than the page: the bindings
BRANCHPOINT persisted are still returned, marked ``unavailable``, so the run
view keeps working and says plainly why the timeline is empty.
"""

from dataclasses import dataclass, field

from app.infrastructure.trueforge.client import TrueForgeClient
from app.infrastructure.trueforge.errors import TrueForgeError
from app.infrastructure.trueforge.harness import (
    HarnessTraceEntry,
    SessionTraceContext,
    normalize_session_events,
)
from app.infrastructure.trueforge.sessions import (
    InMemorySessionBindingStore,
    TrueForgeSessionBinding,
)


@dataclass(frozen=True)
class HarnessTrace:
    """What one run's harness looked like, as far as it can be read."""

    run_id: str
    #: ``available`` when TrueForge answered for every bound session.
    trueforge_status: str
    detail: str
    bindings: tuple[TrueForgeSessionBinding, ...] = ()
    entries: tuple[HarnessTraceEntry, ...] = field(default_factory=tuple)


class HarnessTraceService:
    """Reads TrueForge's own event log for the sessions a run is bound to."""

    def __init__(self, *, client: TrueForgeClient, bindings: InMemorySessionBindingStore) -> None:
        self._client = client
        self._bindings = bindings

    async def trace(self, run_id: str) -> HarnessTrace:
        """Build the trace for ``run_id``. Never raises for TrueForge trouble."""
        bound = tuple(await self._bindings.list_for_run(run_id))
        if not bound:
            return HarnessTrace(
                run_id=run_id,
                trueforge_status="available",
                detail="no TrueForge sessions bound to this run yet",
            )

        entries: list[HarnessTraceEntry] = []
        failures: list[str] = []

        for binding in bound:
            context = SessionTraceContext(
                session_id=binding.trueforge_session_id,
                purpose=str(binding.purpose),
                world_id=binding.world_id,
            )
            try:
                events = await self._client.list_session_events(binding.trueforge_session_id)
            except TrueForgeError as exc:
                # One unreadable session must not blank the whole timeline: the
                # other sessions' real activity is still worth showing.
                failures.append(f"{binding.trueforge_session_id}: {exc}")
                continue
            entries.extend(normalize_session_events(context, events))

        # Ordered by TrueForge's own timestamps so the story reads in the order
        # the harness actually did the work, across sessions.
        entries.sort(key=lambda entry: (entry.timestamp, entry.trace_id))

        if failures:
            return HarnessTrace(
                run_id=run_id,
                trueforge_status="unavailable",
                detail=f"could not read {len(failures)} of {len(bound)} session(s)",
                bindings=bound,
                entries=tuple(entries),
            )

        return HarnessTrace(
            run_id=run_id,
            trueforge_status="available",
            detail=f"read {len(bound)} TrueForge session(s)",
            bindings=bound,
            entries=tuple(entries),
        )
