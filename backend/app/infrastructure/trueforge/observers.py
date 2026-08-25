"""Event hook shared by the TrueForge adapters.

The adapters run inside the Phase 1 orchestrator, which owns its own event
sink and knows nothing about TrueForge. Rather than threading the sink through
the domain, each adapter accepts this small callback and reports what actually
happened — sessions created, subagents spawned, sandboxes used, counterexamples
proposed and replayed.

Only observable facts are reported. ``TurnEvent.reasoning_content`` exists
upstream and is deliberately never read here, so private model reasoning cannot
reach BRANCHPOINT's event stream.
"""

from collections.abc import Callable

from app.domain.events import RunEventType
from app.domain.primitives import ScalarValue

#: (event_type, summary, world_id, payload) -> None
AgentEventEmitter = Callable[[RunEventType, str, str | None, dict[str, ScalarValue]], None]


def null_emitter(
    event_type: RunEventType,
    summary: str,
    world_id: str | None = None,
    payload: dict[str, ScalarValue] | None = None,
) -> None:
    """Default no-op emitter, so adapters work without an event sink wired in."""
    return None
