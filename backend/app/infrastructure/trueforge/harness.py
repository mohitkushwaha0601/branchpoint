"""Normalizing TrueForge harness activity into a safe, BRANCHPOINT-facing trace.

A judge should not have to take a README's word for it that TrueForge really
did the work. This module turns TrueForge's own event log — the same log its UI
renders — into a small, redacted timeline BRANCHPOINT can serve to a browser.

**Everything here is derived from real emitted events.** Nothing is inferred
from BRANCHPOINT run status, and nothing is invented: if TrueForge emitted no
``sandbox.created``, no sandbox row appears, however loudly a model claimed to
have used one.

Redaction is by allowlist, not by blocklist. A normalized entry is built field
by field from a known-safe set — tool names, ids, categories, exit codes — and
the raw event never travels further. Tool arguments, tool results, model prose,
approval payloads, MCP configuration, and provider credentials therefore cannot
leak by omission: there is no path from them into the output at all.

Authority is unchanged by anything in this file. A harness trace is *provenance*
about the agent runtime; it is not evidence, it cannot mark a counterexample
reproduced, and it cannot veto a world.
"""

import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.infrastructure.trueforge.errors import ToolCallResolutionError
from app.infrastructure.trueforge.models import (
    EVENT_MODEL_MESSAGE,
    EVENT_SANDBOX_CREATED,
    EVENT_THREAD_CREATED,
    EVENT_THREAD_DONE,
    EVENT_TOOL_APPROVAL_REQUIRED,
    EVENT_TOOL_RESPONSE,
    EVENT_USER_TOOL_APPROVAL,
    MCP_WRAPPER_TOOL_NAMES,
    SANDBOX_EXEC_TOOL_NAMES,
    SUBAGENT_TOOL_NAME,
    TOOL_INFO_TYPE_MCP,
    ToolCallView,
    TurnEvent,
)

#: Upper bound on any model-authored string that reaches the browser. Sandbox
#: intents and subagent titles are short labels; a long one is a sign something
#: other than a label ended up there, and it is cut rather than trusted.
MAX_LABEL_CHARS = 120


class HarnessCategory(StrEnum):
    """What kind of harness work one trace entry represents."""

    SESSION = "SESSION"
    MCP_TOOL = "MCP_TOOL"
    SANDBOX_CREATED = "SANDBOX_CREATED"
    SANDBOX_EXEC = "SANDBOX_EXEC"
    SUBAGENT_CREATED = "SUBAGENT_CREATED"
    SUBAGENT_COMPLETED = "SUBAGENT_COMPLETED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_RESUMED = "APPROVAL_RESUMED"
    MODEL_TURN = "MODEL_TURN"


class HarnessStatus(StrEnum):
    """How a piece of harness work turned out."""

    OK = "OK"
    FAILED = "FAILED"
    PENDING = "PENDING"
    INFO = "INFO"


class HarnessTraceEntry(BaseModel):
    """One redacted row of TrueForge harness activity."""

    model_config = ConfigDict(frozen=True)

    trace_id: str
    timestamp: str
    session_id: str
    purpose: str
    world_id: str | None
    category: HarnessCategory
    status: HarnessStatus
    summary: str
    tool_name: str = ""
    mcp_server: str = ""
    thread_id: str = ""
    sandbox_id: str = ""
    #: Exit code of a sandbox execution, when TrueForge reported one.
    exit_code: int | None = None


def _clip(value: object) -> str:
    """Render an untrusted label as a bounded single-line string."""
    text = str(value).strip().replace("\n", " ").replace("\r", " ")
    return text[:MAX_LABEL_CHARS]


def _arguments_of(call: ToolCallView) -> dict[str, Any]:
    """Parse a tool call's arguments, or return nothing readable.

    Never raises: a trace row is diagnostics, and an unparseable argument blob
    means "say less", not "fail the request".
    """
    function = call.function
    if function is None or not function.arguments:
        return {}
    try:
        parsed = json.loads(function.arguments)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _exec_result(content: Any) -> tuple[int | None, bool]:
    """Read ``(exit_code, ok)`` out of a sandbox exec ``tool.response``.

    TrueForge 0.1.4 carries `{"response": {"exitCode": n, "result": "..."}}`.
    The **result text is never read** — only the exit code, which is the
    concrete outcome and cannot carry sandbox output into the browser.
    """
    payload: Any = content
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            return None, True
    if not isinstance(payload, dict):
        return None, True

    response = payload.get("response")
    source = response if isinstance(response, dict) else payload
    raw = source.get("exitCode", source.get("exit_code"))
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None, not bool(payload.get("isError", payload.get("is_error", False)))
    return raw, raw == 0


def _classify(call: ToolCallView) -> HarnessCategory | None:
    """Which harness feature a tool call exercises, by TrueForge's own naming."""
    function = call.function
    name = function.name if function is not None else ""
    info = call.tool_info

    if name in SANDBOX_EXEC_TOOL_NAMES:
        return HarnessCategory.SANDBOX_EXEC
    if name == SUBAGENT_TOOL_NAME:
        return HarnessCategory.SUBAGENT_CREATED
    if name in MCP_WRAPPER_TOOL_NAMES:
        return HarnessCategory.MCP_TOOL
    if info is not None and info.type == TOOL_INFO_TYPE_MCP:
        return HarnessCategory.MCP_TOOL
    return None


class SessionTraceContext(BaseModel):
    """Which BRANCHPOINT binding a session's events belong to."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    purpose: str
    world_id: str | None = None


def normalize_session_events(
    context: SessionTraceContext, events: tuple[TurnEvent, ...]
) -> tuple[HarnessTraceEntry, ...]:
    """Turn one session's raw TrueForge events into safe trace entries.

    Two passes: the first records what each tool call *was*, the second reads
    the responses that say how those calls turned out. That ordering is what
    lets an exec's exit code and an approval's resumption be reported from
    TrueForge's own record rather than guessed from BRANCHPOINT's run status.
    """
    entries: list[HarnessTraceEntry] = []
    # tool_call_id -> (category, tool_name, mcp_server) for the second pass.
    calls: dict[str, tuple[HarnessCategory, str, str]] = {}
    awaiting_approval: set[str] = set()

    def add(
        *,
        event: TurnEvent,
        category: HarnessCategory,
        status: HarnessStatus,
        summary: str,
        suffix: str = "",
        **extra: Any,
    ) -> None:
        entries.append(
            HarnessTraceEntry(
                trace_id=f"{context.session_id}:{event.id or len(entries)}{suffix}",
                timestamp=event.created_at,
                session_id=context.session_id,
                purpose=context.purpose,
                world_id=context.world_id,
                category=category,
                status=status,
                summary=summary,
                thread_id=event.thread_id or "",
                **extra,
            )
        )

    for event in events:
        if event.type == EVENT_SANDBOX_CREATED and event.sandbox_id:
            add(
                event=event,
                category=HarnessCategory.SANDBOX_CREATED,
                status=HarnessStatus.OK,
                summary="Daytona sandbox created",
                sandbox_id=event.sandbox_id,
            )

        elif event.type == EVENT_THREAD_CREATED and event.is_subagent:
            add(
                event=event,
                category=HarnessCategory.SUBAGENT_CREATED,
                status=HarnessStatus.OK,
                summary=f"Subagent · {_clip(event.title) or 'delegated investigation'}",
            )

        elif event.type == EVENT_THREAD_DONE and event.is_subagent:
            add(
                event=event,
                category=HarnessCategory.SUBAGENT_COMPLETED,
                status=HarnessStatus.OK,
                summary="Subagent finished",
            )

        elif event.type == EVENT_TOOL_APPROVAL_REQUIRED:
            for pending in event.tool_calls_awaiting_approval:
                tool_call_id = str(pending.get("id", ""))
                if tool_call_id:
                    awaiting_approval.add(tool_call_id)
            named = [calls[tid][1] for tid in awaiting_approval if tid in calls]
            add(
                event=event,
                category=HarnessCategory.APPROVAL_REQUIRED,
                status=HarnessStatus.PENDING,
                summary="Human approval required",
                tool_name=named[0] if named else "",
            )

        elif event.type == EVENT_USER_TOOL_APPROVAL:
            add(
                event=event,
                category=HarnessCategory.APPROVAL_RESUMED,
                status=HarnessStatus.OK,
                summary="Approval resumed by BRANCHPOINT",
            )

        elif event.type == EVENT_MODEL_MESSAGE:
            for call in event.tool_calls:
                category = _classify(call)
                if category is None:
                    continue
                tool_name, server = _describe(call, category)
                if call.id:
                    calls[call.id] = (category, tool_name, server)
                add(
                    event=event,
                    category=category,
                    status=HarnessStatus.PENDING,
                    summary=_summary_for(category, tool_name, call),
                    suffix=f":{call.id}",
                    tool_name=tool_name,
                    mcp_server=server,
                )

        elif event.type == EVENT_TOOL_RESPONSE and event.tool_call_id in calls:
            category, tool_name, server = calls[event.tool_call_id]
            if category is HarnessCategory.SANDBOX_EXEC:
                exit_code, ok = _exec_result(event.content)
                add(
                    event=event,
                    category=category,
                    status=HarnessStatus.OK if ok else HarnessStatus.FAILED,
                    summary="Sandbox exec completed",
                    tool_name=tool_name,
                    exit_code=exit_code,
                )
            elif event.tool_call_id in awaiting_approval:
                # A response to a call that TrueForge had paused is that call
                # having been allowed and run — its own record of the resume.
                awaiting_approval.discard(event.tool_call_id)
                add(
                    event=event,
                    category=HarnessCategory.APPROVAL_RESUMED,
                    status=HarnessStatus.OK,
                    summary=f"Approved call executed · {tool_name}",
                    tool_name=tool_name,
                    mcp_server=server,
                )
            else:
                add(
                    event=event,
                    category=category,
                    status=HarnessStatus.OK,
                    summary=f"{_prefix(category)} · {tool_name}",
                    tool_name=tool_name,
                    mcp_server=server,
                )

    return tuple(entries)


def _prefix(category: HarnessCategory) -> str:
    return {
        HarnessCategory.MCP_TOOL: "MCP",
        HarnessCategory.SANDBOX_EXEC: "Sandbox exec",
        HarnessCategory.SUBAGENT_CREATED: "Subagent",
    }.get(category, "TrueForge")


def _describe(call: ToolCallView, category: HarnessCategory) -> tuple[str, str]:
    """Return ``(tool_name, mcp_server)`` for a classified call.

    An MCP call is resolved through the same resolver the approval path uses, so
    a deferred ``call_tool`` wrapper reports the tool it actually targets rather
    than the wrapper's own name. A wrapper too malformed to resolve is reported
    as the wrapper it literally is, never as a guess at its target.
    """
    function = call.function
    raw_name = function.name if function is not None else ""

    if category is HarnessCategory.MCP_TOOL:
        try:
            resolved = call.resolve()
        except ToolCallResolutionError:
            return raw_name, ""
        return resolved.effective_tool_name, resolved.effective_server_name
    return raw_name, ""


def _summary_for(category: HarnessCategory, tool_name: str, call: ToolCallView) -> str:
    """A one-line description built only from allowlisted argument fields."""
    arguments = _arguments_of(call)

    if category is HarnessCategory.SANDBOX_EXEC:
        # TrueForge's exec arguments carry a short `intent` label alongside the
        # command. The command is model-authored and is deliberately not
        # surfaced; the intent is bounded and clipped.
        intent = _clip(arguments.get("intent", ""))
        return f"Sandbox exec · {intent}" if intent else "Sandbox exec"

    if category is HarnessCategory.SUBAGENT_CREATED:
        name = _clip(arguments.get("name", arguments.get("title", "")))
        return f"Subagent · {name}" if name else "Subagent delegated"

    return f"MCP · {tool_name}" if tool_name else "MCP call"
