"""Resolving TrueForge 0.1.4 tool calls into one unambiguous invocation.

TrueForge expresses the same MCP call two legitimate ways.

**Direct** — the tool is preloaded, so the model names it itself::

    function:  {name: "branchpoint_commit_recommended_world", arguments: "{...}"}
    tool_info: {type: "mcp", name: "branchpoint_commit_recommended_world", ...}

**Deferred** — the tool is *not* preloaded, so TrueForge exposes one generic
entry point and the model names its real target in the arguments::

    function:  {name: "call_tool",
                arguments: '{"mcp_server": "branchpoint",
                             "tool_name": "branchpoint_commit_recommended_world",
                             "input": {...}}'}
    tool_info: {type: "truefoundry-system", name: "call_tool"}

``tool_info`` here describes the **transport wrapper**, not the operation:
``call_tool`` is one of TrueForge's own local tools, and ``model.message``
events are built with ``resolveUnderlyingTool: false`` so the event log matches
the streamed deltas. The underlying MCP identity therefore appears *only* inside
the wrapper's arguments, which is the single authority on what will run.

Both forms collapse to the same effective invocation; everything else is
refused.
"""

import json

import pytest

from app.infrastructure.trueforge.errors import ToolCallResolutionError
from app.infrastructure.trueforge.models import (
    PendingApproval,
    ToolCallForm,
    ToolCallView,
    TurnEvent,
    TurnResult,
    TurnStatus,
)

TOOL = "branchpoint_commit_recommended_world"
SERVER = "branchpoint"
INPUT = {"run_id": "run_1", "world_id": "world_1", "expected_action_id": "action_1"}
DIRECT_ARGUMENTS = json.dumps(INPUT)


def wrapper(*, server: str = SERVER, tool: str = TOOL, inner: object = None) -> str:
    """A ``call_tool`` wrapper payload, serialised as TrueForge sends it."""
    return json.dumps(
        {"mcp_server": server, "tool_name": tool, "input": INPUT if inner is None else inner}
    )


def call(
    *,
    call_id: str = "call_1",
    function: dict | None = None,
    tool_info: dict | None = None,
) -> ToolCallView:
    """Parse one enriched tool call from its wire dict."""
    payload: dict = {"id": call_id}
    if function is not None:
        payload["function"] = function
    if tool_info is not None:
        payload["tool_info"] = tool_info
    return ToolCallView.model_validate(payload)


def direct_call(*, arguments: str = DIRECT_ARGUMENTS, name: str = TOOL, **kwargs) -> ToolCallView:
    return call(function={"name": name, "arguments": arguments}, **kwargs)


#: What TrueForge 0.1.4 actually puts on the event stream for a deferred call.
WRAPPER_INFO = {"type": "truefoundry-system", "name": "call_tool"}

#: The resolved-MCP representation, accepted only when it agrees exactly.
RESOLVED_INFO = {"type": "mcp", "name": TOOL, "server_name": SERVER}


def deferred_call(
    *, arguments: str | None = None, tool_info: dict | None = WRAPPER_INFO, **kwargs
) -> ToolCallView:
    """A deferred wrapper carrying the live wrapper-identity ``tool_info``."""
    return call(
        function={"name": "call_tool", "arguments": wrapper() if arguments is None else arguments},
        tool_info=tool_info,
        **kwargs,
    )


# ----- direct form -----------------------------------------------------------


def test_direct_call_resolves_to_its_own_name_and_arguments() -> None:
    invocation = direct_call().resolve()

    assert invocation.form is ToolCallForm.DIRECT
    assert invocation.effective_tool_name == TOOL
    assert invocation.effective_arguments == INPUT
    assert invocation.raw_function_name == TOOL


def test_direct_call_takes_its_server_from_tool_info_when_stated() -> None:
    invocation = direct_call(
        tool_info={"type": "mcp", "name": TOOL, "server_name": SERVER}
    ).resolve()

    assert invocation.effective_server_name == SERVER


def test_direct_call_without_tool_info_states_no_server() -> None:
    """Empty means "TrueForge did not say", never "any server will do"."""
    assert direct_call().resolve().effective_server_name == ""


def test_direct_call_whose_tool_info_names_a_different_tool_is_refused() -> None:
    with pytest.raises(ToolCallResolutionError, match="disagrees with direct call"):
        direct_call(tool_info={"type": "mcp", "name": "branchpoint_get_metrics"}).resolve()


# ----- deferred form ---------------------------------------------------------


def test_deferred_wrapper_resolves_to_its_target_not_to_call_tool() -> None:
    invocation = deferred_call().resolve()

    assert invocation.form is ToolCallForm.DEFERRED
    assert invocation.effective_tool_name == TOOL
    assert invocation.effective_server_name == SERVER
    assert invocation.effective_arguments == INPUT
    assert invocation.raw_function_name == "call_tool"


def test_the_live_wrapper_identity_tool_info_is_accepted() -> None:
    """The real shape: ``tool_info`` describes ``call_tool``, the wrapper itself.

    The effective operation still comes from the envelope — the metadata
    describing the wrapper is not a conflict with it.
    """
    invocation = deferred_call(tool_info=WRAPPER_INFO).resolve()

    assert invocation.effective_tool_name == TOOL
    assert invocation.effective_server_name == SERVER
    assert invocation.raw_function_name == "call_tool"


def test_a_deferred_wrapper_without_tool_info_is_accepted() -> None:
    """Nothing to cross-check is not the same as something inconsistent."""
    assert deferred_call(tool_info=None).resolve().effective_tool_name == TOOL


def test_a_system_tool_info_naming_something_other_than_call_tool_is_refused() -> None:
    with pytest.raises(ToolCallResolutionError, match="expected 'call_tool'"):
        deferred_call(tool_info={"type": "truefoundry-system", "name": "run_shell"}).resolve()


def test_the_resolved_mcp_representation_is_accepted_when_it_agrees_exactly() -> None:
    """Second supported form, should TrueForge ever report it on the event stream."""
    invocation = deferred_call(tool_info=RESOLVED_INFO).resolve()

    assert invocation.effective_tool_name == TOOL
    assert invocation.effective_server_name == SERVER


def test_deferred_input_becomes_the_effective_arguments() -> None:
    """The wrapper's envelope is never mistaken for the call's arguments."""
    invocation = deferred_call().resolve()

    assert invocation.effective_arguments == INPUT
    assert "mcp_server" not in invocation.effective_arguments
    assert "tool_name" not in invocation.effective_arguments


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        pytest.param('{"mcp_server": "branchpoint", ', "were unparseable", id="malformed JSON"),
        pytest.param("", "were empty", id="empty"),
        pytest.param("[1, 2]", "were not an object", id="not an object"),
        pytest.param(
            json.dumps({"tool_name": TOOL, "input": INPUT}),
            "expected exactly",
            id="missing mcp_server",
        ),
        pytest.param(
            json.dumps({"mcp_server": SERVER, "input": INPUT}),
            "expected exactly",
            id="missing tool_name",
        ),
        pytest.param(
            json.dumps({"mcp_server": SERVER, "tool_name": TOOL}),
            "expected exactly",
            id="missing input",
        ),
        pytest.param(
            json.dumps({"mcp_server": SERVER, "tool_name": TOOL, "input": INPUT, "raw": True}),
            "expected exactly",
            id="extra wrapper field",
        ),
        pytest.param(
            json.dumps({"mcp_server": SERVER, "tool_name": TOOL, "input": "not-an-object"}),
            "input was not an object",
            id="non-object input",
        ),
        pytest.param(
            json.dumps({"mcp_server": "", "tool_name": TOOL, "input": INPUT}),
            "mcp_server was not a non-empty string",
            id="empty mcp_server",
        ),
        pytest.param(
            json.dumps({"mcp_server": 7, "tool_name": TOOL, "input": INPUT}),
            "mcp_server was not a non-empty string",
            id="non-string mcp_server",
        ),
        pytest.param(
            json.dumps({"mcp_server": SERVER, "tool_name": "", "input": INPUT}),
            "tool_name was not a non-empty string",
            id="empty tool_name",
        ),
    ],
)
def test_a_wrapper_that_cannot_be_read_exactly_is_refused(arguments: str, expected: str) -> None:
    with pytest.raises(ToolCallResolutionError, match=expected):
        deferred_call(arguments=arguments).resolve()


def test_resolved_mcp_metadata_must_agree_with_the_wrapper_target() -> None:
    with pytest.raises(ToolCallResolutionError, match="disagrees with deferred tool_name"):
        deferred_call(
            tool_info={"type": "mcp", "name": "branchpoint_get_metrics", "server_name": SERVER}
        ).resolve()


def test_resolved_mcp_metadata_must_agree_with_the_wrapper_server() -> None:
    with pytest.raises(ToolCallResolutionError, match="disagrees with deferred mcp_server"):
        deferred_call(
            tool_info={"type": "mcp", "name": TOOL, "server_name": "someone-elses-server"}
        ).resolve()


def test_an_unrecognised_tool_info_type_is_refused() -> None:
    """Neither wrapper identity nor resolved MCP identity: refuse, do not interpret."""
    with pytest.raises(ToolCallResolutionError, match="unrecognised tool_info.type"):
        deferred_call(tool_info={"type": "builtin", "name": TOOL}).resolve()


# ----- neither form ----------------------------------------------------------


def test_a_call_with_no_function_is_refused() -> None:
    """``tool_info`` alone describes routing, not an invocation."""
    with pytest.raises(ToolCallResolutionError, match="has no function name"):
        call(tool_info={"type": "mcp", "name": TOOL, "server_name": SERVER}).resolve()


def test_a_call_with_nothing_at_all_is_refused() -> None:
    with pytest.raises(ToolCallResolutionError, match="has no function name"):
        call().resolve()


def test_the_flat_shape_is_refused() -> None:
    """``{id, name, arguments}`` is not a shape TrueForge sends.

    Unknown fields are ignored rather than adopted, so a flat call has no
    function at all — and is refused rather than half-understood.
    """
    flat = ToolCallView.model_validate(
        {"id": "call_1", "name": TOOL, "arguments": DIRECT_ARGUMENTS}
    )

    with pytest.raises(ToolCallResolutionError):
        flat.resolve()
    assert flat.effective_name == ""


def test_effective_name_reports_without_raising() -> None:
    """Reporting must degrade to silence, never to an exception or a guess."""
    assert deferred_call().effective_name == TOOL
    assert deferred_call(tool_info={"type": "truefoundry-system", "name": "x"}).effective_name == ""
    assert direct_call().effective_name == TOOL
    assert call().effective_name == ""
    assert deferred_call(arguments="{bad").effective_name == ""


def test_event_tool_names_report_effective_targets() -> None:
    """A deferred commit is reported as the commit tool, not as ``call_tool``."""
    event = TurnEvent.model_validate(
        {
            "type": "model.message",
            "id": "evt_1",
            "tool_calls": [
                {
                    "id": "c1",
                    "function": {"name": "call_tool", "arguments": wrapper()},
                    "tool_info": dict(WRAPPER_INFO),
                },
                {"id": "c2"},
                {"id": "c3", "function": {"name": TOOL, "arguments": DIRECT_ARGUMENTS}},
            ],
        }
    )

    assert event.tool_names == (TOOL, TOOL)


# ----- the reference chain ---------------------------------------------------


def turn(*events: dict, pending: PendingApproval | None = None) -> TurnResult:
    """A done turn with an event log and one optional pending approval."""
    return TurnResult(
        turn_id="turn_1",
        session_id="sess_1",
        status=TurnStatus.DONE,
        events=tuple(TurnEvent.model_validate(event) for event in events),
        pending_approvals=(pending,) if pending else (),
    )


def model_message(*, event_id: str = "evt_1", calls: list[dict]) -> dict:
    return {"type": "model.message", "id": event_id, "thread_id": "main", "tool_calls": calls}


def pending(*, call_id: str = "call_1", source: str = "evt_1") -> PendingApproval:
    return PendingApproval(thread_id="main", tool_call_id=call_id, source_event_id=source)


def deferred_wire(call_id: str = "call_1", *, inner: object = None) -> dict:
    """A deferred call exactly as it appears on the live event stream."""
    return {
        "id": call_id,
        "function": {"name": "call_tool", "arguments": wrapper(inner=inner)},
        "tool_info": dict(WRAPPER_INFO),
    }


def test_the_chain_resolves_a_real_deferred_paused_call() -> None:
    result = turn(model_message(calls=[deferred_wire()]), pending=pending())

    resolved = result.paused_tool_call(result.pending_approvals[0])

    assert resolved is not None
    assert resolved.resolve().effective_tool_name == TOOL


def test_the_chain_picks_the_referenced_call_not_the_only_call() -> None:
    """Selection is by id. A turn with one call proves nothing about which one."""
    calls = [deferred_wire("call_other", inner={"run_id": "other"}), deferred_wire("call_1")]
    result = turn(model_message(calls=calls), pending=pending())

    resolved = result.paused_tool_call(result.pending_approvals[0])

    assert resolved.id == "call_1"
    assert resolved.resolve().effective_arguments == INPUT


def test_the_chain_uses_the_named_source_event_not_any_event() -> None:
    """Another event carrying the same call id must not satisfy the reference."""
    decoy = model_message(
        event_id="evt_decoy", calls=[deferred_wire("call_1", inner={"run_id": "decoy"})]
    )
    real = model_message(event_id="evt_1", calls=[deferred_wire("call_1")])
    result = turn(decoy, real, pending=pending(source="evt_1"))

    resolved = result.paused_tool_call(result.pending_approvals[0])

    assert resolved.resolve().effective_arguments == INPUT


def test_a_missing_source_event_resolves_to_none() -> None:
    result = turn(model_message(calls=[deferred_wire()]), pending=pending(source="evt_missing"))

    assert result.paused_tool_call(result.pending_approvals[0]) is None


def test_a_missing_tool_call_resolves_to_none() -> None:
    result = turn(model_message(calls=[deferred_wire("call_other")]), pending=pending())

    assert result.paused_tool_call(result.pending_approvals[0]) is None


def test_an_absent_source_event_id_resolves_to_none() -> None:
    """Without a reference there is nothing to follow — and nothing to guess."""
    result = turn(model_message(calls=[deferred_wire()]), pending=pending(source=""))

    assert result.paused_tool_call(result.pending_approvals[0]) is None


def test_duplicate_source_event_ids_resolve_to_none() -> None:
    result = turn(
        model_message(calls=[deferred_wire()]),
        model_message(calls=[deferred_wire()]),
        pending=pending(),
    )

    assert result.paused_tool_call(result.pending_approvals[0]) is None


def test_duplicate_tool_call_ids_resolve_to_none() -> None:
    result = turn(
        model_message(calls=[deferred_wire(), deferred_wire(inner={"run_id": "other"})]),
        pending=pending(),
    )

    assert result.paused_tool_call(result.pending_approvals[0]) is None


def test_a_non_message_event_is_not_a_valid_source() -> None:
    """Only the event types TrueForge emits tool calls on may satisfy a reference."""
    result = turn(
        {"type": "tool.response", "id": "evt_1", "tool_calls": [deferred_wire()]},
        pending=pending(),
    )

    assert result.paused_tool_call(result.pending_approvals[0]) is None
