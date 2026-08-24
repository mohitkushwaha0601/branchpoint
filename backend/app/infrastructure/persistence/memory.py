"""In-memory adapters.

Phase 1 stores runs and events in the process only. These are the seams a real
datastore replaces later; nothing else in the system knows where runs live.
"""

import asyncio
from collections.abc import Sequence

from app.domain.events import RunEvent
from app.domain.runs.models import BranchpointRun


class InMemoryRunRepository:
    """Stores runs in a dictionary, newest first on listing."""

    def __init__(self) -> None:
        self._runs: dict[str, BranchpointRun] = {}
        self._lock = asyncio.Lock()

    async def save(self, run: BranchpointRun) -> None:
        """Persist ``run``, replacing any earlier version of it."""
        async with self._lock:
            self._runs[run.run_id] = run

    async def get(self, run_id: str) -> BranchpointRun | None:
        """Return the stored run, or ``None`` when it does not exist."""
        async with self._lock:
            return self._runs.get(run_id)

    async def list_runs(self) -> Sequence[BranchpointRun]:
        """Return every stored run, newest first."""
        async with self._lock:
            runs = tuple(self._runs.values())
        return sorted(runs, key=lambda run: (run.created_at, run.run_id), reverse=True)


class InMemoryEventSink:
    """Collects run events in arrival order."""

    def __init__(self) -> None:
        self._events: list[RunEvent] = []
        self._lock = asyncio.Lock()

    async def emit(self, event: RunEvent) -> None:
        """Record one run event."""
        async with self._lock:
            self._events.append(event)

    async def events(self) -> Sequence[RunEvent]:
        """Return every recorded event in arrival order."""
        async with self._lock:
            return tuple(self._events)

    async def events_for(self, run_id: str) -> Sequence[RunEvent]:
        """Return the events belonging to ``run_id`` in arrival order."""
        async with self._lock:
            return tuple(event for event in self._events if event.run_id == run_id)
