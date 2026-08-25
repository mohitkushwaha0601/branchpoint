"""Typed views of the TrueForge v0.1.4 wire format.

Everything TrueForge returns is parsed into these models at the infrastructure
boundary, so no TrueForge-shaped dict ever reaches the application or domain
layers. Field names mirror the upstream OpenAPI spec exactly
(https://trueforge.dev/openapi.json, version 0.1.4).

Models are permissive (``extra="ignore"``) on purpose: an upstream additive
change should not break parsing of the fields we actually rely on.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TrueForgeModel(BaseModel):
    """Base for wire models: immutable, tolerant of unknown upstream fields."""

    model_config = ConfigDict(frozen=True, extra="ignore")


class TurnStatus(StrEnum):
    """Terminal and non-terminal turn states (TrueForge ``TurnState.status``)."""

    RUNNING = "running"
    DONE = "done"
    CANCELLED = "cancelled"
    ERROR = "error"


#: TrueForge event types we consume. Upstream emits more; we ignore the rest.
EVENT_THREAD_CREATED = "thread.created"
EVENT_THREAD_DONE = "thread.done"
EVENT_MODEL_MESSAGE = "model.message"
EVENT_TOOL_RESPONSE = "tool.response"
EVENT_SANDBOX_CREATED = "sandbox.created"
EVENT_TOOL_APPROVAL_REQUIRED = "tool.approval_required"

#: The root agent's thread id in TrueForge. Subagents get their own thread ids.
ROOT_THREAD_ID = "main"


class ToolCallView(TrueForgeModel):
    """One tool call the model requested."""

    id: str = ""
    name: str = ""
    arguments: str = ""


class TurnEvent(TrueForgeModel):
    """One event from a turn's event log.

    ``reasoning_content`` is deliberately **not** modelled: TrueForge exposes
    it on ``model.message``, and BRANCHPOINT must never surface private model
    reasoning in its own event stream.
    """

    type: str
    id: str = ""
    created_at: str = ""
    thread_id: str | None = None
    title: str = ""
    sandbox_id: str = ""
    tool_call_id: str = ""
    content: Any = None
    tool_calls: tuple[ToolCallView, ...] = ()
    agent_info: dict[str, Any] = Field(default_factory=dict)
    parent: dict[str, Any] = Field(default_factory=dict)
    tool_calls_awaiting_approval: tuple[dict[str, Any], ...] = ()

    @property
    def is_subagent(self) -> bool:
        """Whether this event came from a spawned subagent rather than the root agent."""
        return self.thread_id is not None and self.thread_id != ROOT_THREAD_ID

    @property
    def tool_names(self) -> tuple[str, ...]:
        """Names of tools this event requested, if any."""
        return tuple(call.name for call in self.tool_calls if call.name)


class PendingApproval(TrueForgeModel):
    """A tool call paused awaiting human approval.

    ``name``/``arguments`` mirror the paused call as TrueForge reports it, so a
    caller can check *what* it is about to allow before allowing it. Both
    default to empty because upstream is not obliged to repeat them on the
    required action — :meth:`TurnResult.paused_tool_call` falls back to the
    turn's ``tool.approval_required`` event, and a caller that still cannot
    identify the call must fail closed rather than approve blind.
    """

    thread_id: str
    tool_call_id: str
    source_event_id: str = ""
    name: str = ""
    arguments: str = ""


class TurnResult(TrueForgeModel):
    """The outcome of executing one turn, already translated from the wire."""

    turn_id: str
    session_id: str
    status: TurnStatus
    output_text: str = ""
    events: tuple[TurnEvent, ...] = ()
    pending_approvals: tuple[PendingApproval, ...] = ()
    error_detail: str = ""

    @property
    def is_paused_for_approval(self) -> bool:
        """Whether the turn stopped because a tool call needs human approval."""
        return bool(self.pending_approvals)

    def paused_tool_call(self, pending: PendingApproval) -> ToolCallView | None:
        """Resolve the full tool call one pending approval refers to.

        Prefers what the required action itself reported; otherwise looks the
        call up by id in this turn's ``tool.approval_required`` events. Returns
        ``None`` when neither identifies the call — the caller must then treat
        the approval as unidentifiable and refuse it.
        """
        if pending.name:
            return ToolCallView(
                id=pending.tool_call_id, name=pending.name, arguments=pending.arguments
            )
        for event in self.events:
            if event.type != EVENT_TOOL_APPROVAL_REQUIRED:
                continue
            for call in event.tool_calls:
                if call.id == pending.tool_call_id and call.name:
                    return call
        return None

    @property
    def subagent_thread_ids(self) -> tuple[str, ...]:
        """Thread ids of subagents spawned during this turn, in creation order."""
        return tuple(
            event.thread_id
            for event in self.events
            if event.type == EVENT_THREAD_CREATED and event.thread_id
        )

    @property
    def sandbox_ids(self) -> tuple[str, ...]:
        """Sandbox ids created during this turn."""
        return tuple(
            event.sandbox_id for event in self.events if event.type == EVENT_SANDBOX_CREATED
        )

    def tools_called(self) -> tuple[str, ...]:
        """Every tool name invoked during this turn, in order, including duplicates."""
        return tuple(name for event in self.events for name in event.tool_names)
