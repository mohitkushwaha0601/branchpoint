"""In-process background work, with no unobserved failures.

Mission Control needs a run id before the TrueForge pipeline finishes, so the
drive has to happen after the HTTP response. This is the smallest thing that
can own that: named ``asyncio`` tasks, at most one per key, every one of which
has its result retrieved.

Deliberately not a job queue. There is no broker, no worker pool, and no
persistence — **one backend process is the deployment requirement**. A restart
loses in-flight drives exactly as it loses the in-memory run repository they
write to, so the two have the same durability and cannot disagree.

Failing a run is *not* this module's job. A caller hands in a coroutine that has
already decided what its own failure means in domain terms; the runner's only
guarantee is that an exception escaping that coroutine is logged rather than
swallowed by the event loop.
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)


class BackgroundTaskRunner:
    """At most one live task per key, each with its exception observed."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def start(self, key: str, work: Callable[[], Coroutine[Any, Any, None]]) -> bool:
        """Schedule ``work`` under ``key``.

        Returns ``False`` — having scheduled nothing — when a task for that key
        is still running. That is what keeps one run to one drive: a second POST
        for the same run cannot start a second pipeline over the same state.
        """
        existing = self._tasks.get(key)
        if existing is not None and not existing.done():
            return False

        task = asyncio.create_task(work(), name=f"branchpoint:{key}")
        self._tasks[key] = task
        task.add_done_callback(self._observe)
        return True

    def _observe(self, task: asyncio.Task[None]) -> None:
        """Retrieve the outcome so Python never reports it as never-retrieved.

        Reaching the ``exception`` branch means the caller's own failure
        handling raised, which is a bug rather than a run outcome — it is logged
        with a traceback instead of vanishing into the loop's exception handler.
        """
        if task.cancelled():
            logger.info("background task %s cancelled", task.get_name())
            return
        error = task.exception()
        if error is not None:
            logger.error(
                "background task %s failed to handle its own error",
                task.get_name(),
                exc_info=error,
            )

    def is_running(self, key: str) -> bool:
        """Whether work for ``key`` is still in flight."""
        task = self._tasks.get(key)
        return task is not None and not task.done()

    def task_count(self, key: str) -> int:
        """How many tasks this runner is tracking for ``key`` — never above one."""
        return 1 if key in self._tasks else 0

    async def wait(self, key: str) -> None:
        """Await the task for ``key``, if there is one.

        For tests and shutdown. Exceptions stay observed by ``_observe``; this
        never re-raises, because a caller waiting on a run's drive wants the
        run's recorded outcome, not the task's.
        """
        task = self._tasks.get(key)
        if task is None:
            return
        await asyncio.wait({task})

    async def drain(self) -> None:
        """Wait for every tracked task to finish. Used on shutdown."""
        pending = {task for task in self._tasks.values() if not task.done()}
        if pending:
            await asyncio.wait(pending)

    async def cancel_all(self) -> None:
        """Cancel everything in flight and wait for it to unwind."""
        pending = {task for task in self._tasks.values() if not task.done()}
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.wait(pending)
