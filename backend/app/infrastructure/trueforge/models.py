"""Typed views of the TrueForge v0.1.4 wire format.

Everything TrueForge returns is parsed into these models at the infrastructure
boundary, so no TrueForge-shaped dict ever reaches the application or domain
layers. Field names mirror the upstream OpenAPI spec exactly
(https://trueforge.dev/openapi.json, version 0.1.4).

Models are permissive (``extra="ignore"``) on purpose: an upstream additive
change should not break parsing of the fields we actually rely on.
"""

import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.infrastructure.trueforge.errors import ToolCallResolutionError


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

#: Event types TrueForge emits tool calls on. A paused approval is only ever
#: resolved against one of these, by id — never against the turn's prose, and
#: never by assuming a turn's single tool call must be the paused one. Widening
#: this set widens what BRANCHPOINT will agree to approve, so it is a named
#: constant rather than an inline check.
TOOL_CALL_SOURCE_EVENT_TYPES: tuple[str, ...] = (EVENT_MODEL_MESSAGE,)

#: ``tool_info.type`` for a tool served over MCP.
TOOL_INFO_TYPE_MCP = "mcp"

#: ``tool_info.type`` for one of TrueForge's own local/system tools — which is
#: what the deferred ``call_tool`` wrapper is.
TOOL_INFO_TYPE_SYSTEM = "truefoundry-system"

#: TrueForge's deferred-tool wrapper. When a tool is not preloaded into the
#: model's context, TrueForge exposes a single generic entry point instead: the
#: model calls ``call_tool`` and names its real target in the arguments, and
#: TrueForge resolves and invokes that MCP tool itself.
#:
#: The wrapper is one of TrueForge's own local tools, so on the event stream its
#: ``tool_info`` describes **the wrapper** — ``{type: "truefoundry-system",
#: name: "call_tool"}`` — not the operation it will perform. TrueForge builds
#: ``model.message`` events with ``resolveUnderlyingTool: false`` specifically so
#: the event log matches the streamed deltas, so the underlying MCP identity is
#: never reported there. It lives **only** inside the wrapper's own arguments,
#: which is therefore the single authority on what a deferred call will do.
DEFERRED_TOOL_NAME = "call_tool"

#: The exact key set of a ``call_tool`` wrapper. Exact, not minimum: an
#: unrecognised key means BRANCHPOINT is reading a wrapper it does not fully
#: understand, and it must not approve what it cannot fully read.
DEFERRED_WRAPPER_KEYS = frozenset({"mcp_server", "tool_name", "input"})


class ToolCallForm(StrEnum):
    """How a tool call was expressed on the wire."""

    #: The model named the MCP tool itself.
    DIRECT = "DIRECT"
    #: The model called ``call_tool`` and named the MCP tool in its arguments.
    DEFERRED = "DEFERRED"


class ResolvedToolInvocation(BaseModel):
    """What a tool call will *effectively* do, once its wire form is resolved.

    The point of this type is that authorization never reads the raw wire
    again. Both forms collapse to the same three questions — which tool, on
    which server, with which arguments — so a caller cannot accidentally check
    a wrapper's name when it meant to check its target.

    ``raw_function_name`` is retained for diagnostics only. Nothing may
    authorize against it.
    """

    model_config = ConfigDict(frozen=True)

    form: ToolCallForm
    effective_tool_name: str
    effective_server_name: str
    effective_arguments: dict[str, Any]
    raw_function_name: str


def _decode_object(raw: str, what: str) -> dict[str, Any]:
    """Decode ``raw`` into exactly one JSON object, or refuse it.

    Never coerces: something BRANCHPOINT cannot read as an object is something
    it cannot check, and therefore something it must not approve.
    """
    if not raw.strip():
        raise ToolCallResolutionError(f"{what} were empty")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ToolCallResolutionError(f"{what} were unparseable: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ToolCallResolutionError(f"{what} were not an object")
    return parsed


class ToolFunctionView(TrueForgeModel):
    """The function payload of a tool call: its name and raw JSON arguments.

    ``arguments`` is deliberately kept as the **raw string** TrueForge sent. It
    is parsed exactly once, at the verification boundary that cares, so nothing
    upstream of that decision can be changed by a lenient re-serialisation.
    """

    name: str = ""
    arguments: str = ""


class ToolInfoView(TrueForgeModel):
    """TrueForge's enrichment describing where a tool call is routed.

    Only the fields BRANCHPOINT actually reasons about are modelled; upstream
    sends more and is free to keep adding to it.
    """

    type: str = ""
    name: str = ""
    server_name: str = ""


class ToolCallView(TrueForgeModel):
    """One tool call the model requested, in TrueForge's enriched wire shape.

    The name and arguments are **nested** under ``function``, with MCP routing
    described separately under ``tool_info``. Both are optional on the wire, so
    every accessor below is total: an unidentifiable call resolves to the empty
    string rather than raising, and every caller compares that against an
    expected value — which fails closed by construction.
    """

    id: str = ""
    function: ToolFunctionView | None = None
    tool_info: ToolInfoView | None = None

    def resolve(self) -> ResolvedToolInvocation:
        """Resolve this call into the one invocation it will actually perform.

        Exactly two forms are accepted, and anything else raises:

        **DIRECT** — the model named the MCP tool itself. ``tool_info.name``,
        when present, must agree with it.

        **DEFERRED** — the model called ``call_tool``. Its arguments must be
        exactly ``{mcp_server, tool_name, input}``, and ``tool_info``, when
        present, must agree with *the wrapper's target* rather than with
        ``call_tool``. That disagreement between ``function.name`` and
        ``tool_info.name`` is the expected shape here, not a conflict.

        Raises :class:`ToolCallResolutionError` on anything it cannot read
        unambiguously. It never returns a partially-understood invocation.
        """
        function = self.function
        if function is None or not function.name:
            raise ToolCallResolutionError(
                f"tool call {self.id or '<unnamed>'} has no function name"
            )
        if function.name == DEFERRED_TOOL_NAME:
            return self._resolve_deferred(function)
        return self._resolve_direct(function)

    def _resolve_direct(self, function: ToolFunctionView) -> ResolvedToolInvocation:
        """Resolve a call that names its MCP tool directly."""
        info = self.tool_info
        if info is not None and info.name and info.name != function.name:
            raise ToolCallResolutionError(
                f"tool_info.name {info.name!r} disagrees with direct call "
                f"function.name {function.name!r}"
            )
        return ResolvedToolInvocation(
            form=ToolCallForm.DIRECT,
            effective_tool_name=function.name,
            # Only TrueForge states the server for a direct call, and only when
            # it sends tool_info. Empty means "not stated", never "any server":
            # callers enforce the server whenever one is stated.
            effective_server_name=info.server_name if info is not None else "",
            effective_arguments=_decode_object(function.arguments, "direct call arguments"),
            raw_function_name=function.name,
        )

    def _resolve_deferred(self, function: ToolFunctionView) -> ResolvedToolInvocation:
        """Resolve a ``call_tool`` wrapper into the MCP call it stands for.

        The wrapper's **arguments are the sole authority** on what will run: it
        is TrueForge that resolves ``mcp_server``/``tool_name`` and invokes
        them. ``tool_info`` here identifies the *transport wrapper*, so it is
        only ever cross-checked for internal consistency — it can never supply,
        override, or vouch for the underlying operation.
        """
        wrapper = _decode_object(function.arguments, "deferred call_tool arguments")
        if set(wrapper) != DEFERRED_WRAPPER_KEYS:
            raise ToolCallResolutionError(
                f"deferred call_tool wrapper carries {sorted(wrapper)}, "
                f"expected exactly {sorted(DEFERRED_WRAPPER_KEYS)}"
            )

        server, tool, inner = wrapper["mcp_server"], wrapper["tool_name"], wrapper["input"]
        if not isinstance(server, str) or not server:
            raise ToolCallResolutionError(
                "deferred call_tool mcp_server was not a non-empty string"
            )
        if not isinstance(tool, str) or not tool:
            raise ToolCallResolutionError("deferred call_tool tool_name was not a non-empty string")
        if not isinstance(inner, dict):
            raise ToolCallResolutionError("deferred call_tool input was not an object")

        self._assert_wrapper_metadata_consistent(server, tool)

        return ResolvedToolInvocation(
            form=ToolCallForm.DEFERRED,
            effective_tool_name=tool,
            effective_server_name=server,
            effective_arguments=inner,
            raw_function_name=DEFERRED_TOOL_NAME,
        )

    def _assert_wrapper_metadata_consistent(self, server: str, tool: str) -> None:
        """Cross-check a deferred wrapper's ``tool_info``, when it carries one.

        Two representations are accepted, and each is checked against what it
        actually claims to describe:

        * **wrapper identity** (what TrueForge 0.1.4 puts on the event stream):
          ``{type: "truefoundry-system", name: "call_tool"}``. It exposes no
          server, and none is expected of it.
        * **resolved MCP identity**, should TrueForge ever report it here:
          it must agree exactly with the wrapper's own target and server.

        Absent ``tool_info`` is accepted — there is then simply nothing to
        cross-check, and the envelope was already validated. Any other type is
        refused rather than interpreted.
        """
        info = self.tool_info
        if info is None:
            return

        if info.type == TOOL_INFO_TYPE_SYSTEM:
            if info.name != DEFERRED_TOOL_NAME:
                raise ToolCallResolutionError(
                    f"deferred wrapper tool_info names system tool {info.name!r}, "
                    f"expected {DEFERRED_TOOL_NAME!r}"
                )
            return

        if info.type == TOOL_INFO_TYPE_MCP:
            if info.name != tool:
                raise ToolCallResolutionError(
                    f"tool_info.name {info.name!r} disagrees with deferred tool_name {tool!r}"
                )
            if info.server_name != server:
                raise ToolCallResolutionError(
                    f"tool_info.server_name {info.server_name!r} disagrees with deferred "
                    f"mcp_server {server!r}"
                )
            return

        raise ToolCallResolutionError(
            f"deferred wrapper carries unrecognised tool_info.type {info.type!r}"
        )

    @property
    def effective_name(self) -> str:
        """The tool this call effectively targets, or ``""`` if unresolvable.

        **Reporting only.** It swallows resolution failures so a timeline or a
        log line cannot explode; nothing may authorize against it.
        """
        try:
            return self.resolve().effective_tool_name
        except ToolCallResolutionError:
            return ""


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
        """Names of tools this event requested, if any.

        Skips any call whose name cannot be established unambiguously, so this
        stays usable for reporting without ever inventing a name.
        """
        return tuple(call.effective_name for call in self.tool_calls if call.effective_name)


class PendingApproval(TrueForgeModel):
    """A tool call paused awaiting human approval.

    This is a **reference**, not a description: TrueForge's required action
    carries the thread, the tool call id, and the id of the event that emitted
    the call — and nothing about what the call actually is. Resolving it to a
    real tool name and arguments is :meth:`TurnResult.paused_tool_call`'s job,
    and it is done by following those references, never by assuming.
    """

    thread_id: str
    tool_call_id: str
    source_event_id: str = ""


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
        """Resolve the tool call one pending approval refers to, or ``None``.

        Follows TrueForge's own reference chain exactly:

            required_action → tool_call_id + source_event_id
                → the event whose ``id`` is that source_event_id
                → the tool call within it whose ``id`` is that tool_call_id

        Returns ``None`` — meaning *refuse this approval* — whenever any link
        is missing or ambiguous: no source_event_id, no such event, more than
        one event or call with that id, or no matching call. It never falls
        back to "the turn only made one call, so that must be it": a resolution
        that guesses is a resolution that can be steered.
        """
        if not pending.tool_call_id or not pending.source_event_id:
            return None

        sources = [
            event
            for event in self.events
            if event.id == pending.source_event_id and event.type in TOOL_CALL_SOURCE_EVENT_TYPES
        ]
        if len(sources) != 1:
            return None

        matches = [call for call in sources[0].tool_calls if call.id == pending.tool_call_id]
        if len(matches) != 1:
            return None
        return matches[0]

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
