"""The TrueForge harness trace: real events in, redacted timeline out.

Every event shape here is TrueForge 0.1.4's own, taken from its published
vocabulary and client bundle rather than invented:

    thread.created · thread.done · model.message · tool.response
    sandbox.created · tool.approval_required · user.tool_approval

and its local tool names ``create_sub_agent`` / ``exec`` / ``call_tool``.

No model is called and no socket is opened: the fake transport serves the
events, and the real client parses them.
"""

import json

import pytest

from app.application.orchestration.harness_trace import HarnessTraceService
from app.infrastructure.trueforge.errors import TrueForgeUnavailableError
from app.infrastructure.trueforge.harness import (
    HarnessCategory,
    HarnessStatus,
    SessionTraceContext,
    normalize_session_events,
)
from app.infrastructure.trueforge.models import TurnEvent
from app.infrastructure.trueforge.sessions import (
    InMemorySessionBindingStore,
    SessionPurpose,
)

CONTEXT = SessionTraceContext(session_id="sess_1", purpose="ADVERSARY", world_id="world_alpha")

#: A credential-shaped string planted in every payload a redaction test reads,
#: so a leak shows up as this exact token rather than as a subtle omission.
SECRET = "sk-live-DO-NOT-LEAK-0123456789"


def event(**fields: object) -> TurnEvent:
    """Build one TrueForge event with sane defaults."""
    base: dict[str, object] = {
        "type": "model.message",
        "id": "evt_1",
        "created_at": "2026-08-26T18:42:00Z",
        "thread_id": "main",
    }
    base.update(fields)
    return TurnEvent.model_validate(base)


def mcp_call_event(tool: str = "branchpoint_get_metrics", call_id: str = "call_mcp") -> TurnEvent:
    """A direct MCP tool call, as TrueForge reports one."""
    return event(
        id=f"evt_{call_id}",
        tool_calls=[
            {
                "id": call_id,
                "function": {
                    "name": tool,
                    "arguments": json.dumps({"run_id": "run_1", "token": SECRET}),
                },
                "tool_info": {"type": "mcp", "name": tool, "server_name": "branchpoint"},
            }
        ],
    )


def exec_call_event(call_id: str = "call_exec") -> TurnEvent:
    """A sandbox exec call. Arguments carry `command` and `intent`."""
    return event(
        id=f"evt_{call_id}",
        thread_id="thread_sub_1",
        tool_calls=[
            {
                "id": call_id,
                "function": {
                    "name": "exec",
                    "arguments": json.dumps(
                        {
                            "command": f"python3 -c \"print('{SECRET}')\"",
                            "intent": "check schema deserialization",
                        }
                    ),
                },
                "tool_info": {"type": "truefoundry-system", "name": "exec"},
            }
        ],
    )


def exec_response_event(call_id: str = "call_exec", exit_code: int = 0) -> TurnEvent:
    """TrueForge 0.1.4 exec result: {"response": {"exitCode": n, "result": ...}}."""
    return event(
        type="tool.response",
        id=f"evt_resp_{call_id}",
        tool_call_id=call_id,
        content=json.dumps({"response": {"exitCode": exit_code, "result": SECRET}}),
    )


def subagent_call_event(call_id: str = "call_sub") -> TurnEvent:
    return event(
        id=f"evt_{call_id}",
        tool_calls=[
            {
                "id": call_id,
                "function": {
                    "name": "create_sub_agent",
                    "arguments": json.dumps({"name": "Compatibility Skeptic", "task": SECRET}),
                },
                "tool_info": {"type": "truefoundry-system", "name": "create_sub_agent"},
            }
        ],
    )


# ----- normalization ----------------------------------------------------------


def test_an_mcp_call_is_reported_by_tool_and_server() -> None:
    entries = normalize_session_events(CONTEXT, (mcp_call_event(),))

    assert len(entries) == 1
    entry = entries[0]
    assert entry.category is HarnessCategory.MCP_TOOL
    assert entry.tool_name == "branchpoint_get_metrics"
    assert entry.mcp_server == "branchpoint"
    assert entry.summary == "MCP · branchpoint_get_metrics"
    assert entry.world_id == "world_alpha"
    assert entry.purpose == "ADVERSARY"


def test_a_deferred_call_reports_the_tool_it_targets_not_the_wrapper() -> None:
    """`call_tool` names its real target in its arguments; the trace says that."""
    wrapper = event(
        tool_calls=[
            {
                "id": "call_1",
                "function": {
                    "name": "call_tool",
                    "arguments": json.dumps(
                        {
                            "mcp_server": "branchpoint",
                            "tool_name": "branchpoint_get_schema",
                            "input": {"run_id": "run_1"},
                        }
                    ),
                },
                "tool_info": {"type": "truefoundry-system", "name": "call_tool"},
            }
        ]
    )

    entry = normalize_session_events(CONTEXT, (wrapper,))[0]

    assert entry.category is HarnessCategory.MCP_TOOL
    assert entry.tool_name == "branchpoint_get_schema"
    assert entry.mcp_server == "branchpoint"


def test_sandbox_creation_is_reported_with_its_sandbox_id() -> None:
    created = event(type="sandbox.created", id="evt_sbx", sandbox_id="v1:daytona:abc")

    entry = normalize_session_events(CONTEXT, (created,))[0]

    assert entry.category is HarnessCategory.SANDBOX_CREATED
    assert entry.status is HarnessStatus.OK
    assert entry.sandbox_id == "v1:daytona:abc"
    assert entry.summary == "Daytona sandbox created"


def test_a_successful_exec_reports_exit_code_zero() -> None:
    entries = normalize_session_events(
        CONTEXT, (exec_call_event(), exec_response_event(exit_code=0))
    )

    call, response = entries
    assert call.category is HarnessCategory.SANDBOX_EXEC
    assert call.summary == "Sandbox exec · check schema deserialization"
    assert response.category is HarnessCategory.SANDBOX_EXEC
    assert response.status is HarnessStatus.OK
    assert response.exit_code == 0


def test_a_failing_exec_is_reported_as_failed() -> None:
    entries = normalize_session_events(
        CONTEXT, (exec_call_event(), exec_response_event(exit_code=2))
    )

    assert entries[1].status is HarnessStatus.FAILED
    assert entries[1].exit_code == 2


@pytest.mark.parametrize(
    "content",
    ["not json at all", "", None, 42, {"response": "not an object"}, {"response": {}}],
)
def test_a_malformed_exec_response_never_raises(content: object) -> None:
    """A trace row is diagnostics: an unreadable payload says less, not nothing."""
    entries = normalize_session_events(
        CONTEXT,
        (
            exec_call_event(),
            event(type="tool.response", id="evt_r", tool_call_id="call_exec", content=content),
        ),
    )

    assert len(entries) == 2
    assert entries[1].exit_code is None


def test_a_subagent_delegation_and_its_thread_are_both_reported() -> None:
    entries = normalize_session_events(
        CONTEXT,
        (
            subagent_call_event(),
            event(
                type="thread.created",
                id="evt_thread",
                thread_id="thread_sub_1",
                title="Compatibility Skeptic",
                parent={"thread_id": "main", "tool_call_id": "call_sub"},
            ),
            event(type="thread.done", id="evt_thread_done", thread_id="thread_sub_1"),
        ),
    )

    categories = [entry.category for entry in entries]
    assert HarnessCategory.SUBAGENT_CREATED in categories
    assert HarnessCategory.SUBAGENT_COMPLETED in categories
    assert any(entry.summary == "Subagent · Compatibility Skeptic" for entry in entries)


def test_the_root_thread_is_never_mistaken_for_a_subagent() -> None:
    entries = normalize_session_events(
        CONTEXT, (event(type="thread.created", id="e1", thread_id="main", title="root"),)
    )

    assert entries == ()


def test_an_approval_checkpoint_names_the_paused_tool() -> None:
    entries = normalize_session_events(
        CONTEXT,
        (
            mcp_call_event(tool="branchpoint_commit_recommended_world", call_id="call_c"),
            event(
                type="tool.approval_required",
                id="evt_approval",
                tool_calls_awaiting_approval=[{"id": "call_c"}],
            ),
        ),
    )

    approval = entries[1]
    assert approval.category is HarnessCategory.APPROVAL_REQUIRED
    assert approval.status is HarnessStatus.PENDING
    assert approval.tool_name == "branchpoint_commit_recommended_world"


def test_a_resumed_approval_is_read_from_trueforges_own_record() -> None:
    """The resume is the paused call producing a response — not a run-status guess."""
    entries = normalize_session_events(
        CONTEXT,
        (
            mcp_call_event(tool="branchpoint_commit_recommended_world", call_id="call_c"),
            event(
                type="tool.approval_required",
                id="evt_approval",
                tool_calls_awaiting_approval=[{"id": "call_c"}],
            ),
            event(
                type="tool.response",
                id="evt_committed",
                tool_call_id="call_c",
                content="committed",
            ),
        ),
    )

    resumed = entries[-1]
    assert resumed.category is HarnessCategory.APPROVAL_RESUMED
    assert resumed.status is HarnessStatus.OK
    assert resumed.tool_name == "branchpoint_commit_recommended_world"


def test_an_explicit_user_tool_approval_event_is_reported() -> None:
    entries = normalize_session_events(CONTEXT, (event(type="user.tool_approval", id="evt_ua"),))

    assert entries[0].category is HarnessCategory.APPROVAL_RESUMED


def test_nothing_is_reported_for_a_session_that_did_nothing() -> None:
    """No invented rows: an empty log produces an empty trace."""
    assert normalize_session_events(CONTEXT, ()) == ()
    assert normalize_session_events(CONTEXT, (event(content="just talking"),)) == ()


# ----- redaction --------------------------------------------------------------


def test_no_argument_result_or_credential_reaches_the_trace() -> None:
    """The load-bearing safety test for this whole surface."""
    entries = normalize_session_events(
        CONTEXT,
        (
            mcp_call_event(),
            subagent_call_event(),
            exec_call_event(),
            exec_response_event(),
            event(content=f"my key is {SECRET}"),
        ),
    )

    serialized = json.dumps([entry.model_dump() for entry in entries])
    assert SECRET not in serialized
    # The model-authored command is never surfaced either.
    assert "python3 -c" not in serialized
    assert "print(" not in serialized


def test_a_long_model_authored_label_is_clipped() -> None:
    entries = normalize_session_events(
        CONTEXT,
        (
            event(
                tool_calls=[
                    {
                        "id": "c1",
                        "function": {
                            "name": "exec",
                            "arguments": json.dumps({"intent": "x" * 5000}),
                        },
                        "tool_info": {"type": "truefoundry-system", "name": "exec"},
                    }
                ]
            ),
        ),
    )

    assert len(entries[0].summary) < 200


# ----- the service ------------------------------------------------------------


class StubClient:
    """Serves session events, or refuses, without a socket."""

    def __init__(self, events: dict[str, tuple[TurnEvent, ...]], *, down: bool = False):
        self._events = events
        self._down = down
        self.asked: list[str] = []

    async def list_session_events(self, session_id: str) -> tuple[TurnEvent, ...]:
        self.asked.append(session_id)
        if self._down:
            raise TrueForgeUnavailableError("could not reach TrueForge")
        return self._events.get(session_id, ())


async def bound_store() -> InMemorySessionBindingStore:
    store = InMemorySessionBindingStore()
    await store.upsert(
        run_id="run_1",
        purpose=SessionPurpose.PLANNER,
        trueforge_session_id="sess_planner",
    )
    await store.upsert(
        run_id="run_1",
        world_id="world_alpha",
        purpose=SessionPurpose.ADVERSARY,
        trueforge_session_id="sess_alpha",
    )
    return store


async def test_the_trace_reads_only_the_sessions_this_run_is_bound_to() -> None:
    client = StubClient({"sess_alpha": (mcp_call_event(),)})
    service = HarnessTraceService(client=client, bindings=await bound_store())

    trace = await service.trace("run_1")

    assert sorted(client.asked) == ["sess_alpha", "sess_planner"]
    assert trace.trueforge_status == "available"
    assert {entry.session_id for entry in trace.entries} == {"sess_alpha"}


async def test_a_run_with_no_bindings_traces_to_nothing() -> None:
    service = HarnessTraceService(client=StubClient({}), bindings=await bound_store())

    trace = await service.trace("run_unknown")

    assert trace.entries == ()
    assert trace.bindings == ()


async def test_trueforge_being_down_degrades_instead_of_failing() -> None:
    """The run page must keep working; the trace says why it is empty."""
    service = HarnessTraceService(client=StubClient({}, down=True), bindings=await bound_store())

    trace = await service.trace("run_1")

    assert trace.trueforge_status == "unavailable"
    assert trace.entries == ()
    # BRANCHPOINT's own bindings survive, so session ids are still shown.
    assert {b.trueforge_session_id for b in trace.bindings} == {
        "sess_planner",
        "sess_alpha",
    }


async def test_entries_are_ordered_by_trueforges_own_timestamps() -> None:
    late = mcp_call_event(call_id="late")
    early = mcp_call_event(call_id="early").model_copy(
        update={"created_at": "2026-08-26T18:00:00Z"}
    )
    client = StubClient({"sess_alpha": (late, early)})
    service = HarnessTraceService(client=client, bindings=await bound_store())

    trace = await service.trace("run_1")

    assert [entry.timestamp for entry in trace.entries] == [
        "2026-08-26T18:00:00Z",
        "2026-08-26T18:42:00Z",
    ]
