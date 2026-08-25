"""The TrueForge side of the commit: pause, identify, resume — or deny.

These tests exercise the real ``TrueForgeCommitOperator`` against the fake
transport, using **TrueForge 0.1.4's actual wire shape**: a required action
that carries only references (``thread_id``, ``tool_call_id``,
``source_event_id``), and the enriched tool call itself nested on the
``model.message`` event those references point at, with ``function.name`` /
``function.arguments`` and a separate ``tool_info``.

This distinction is not cosmetic. An earlier flat fixture (``{id, name,
arguments}`` on the required action) passed every test while the live path
denied a perfectly valid commit, because nothing in the suite ever exercised
the reference chain TrueForge really uses. ``test_flat_shape_is_not_relied_on``
below pins that gap shut.

No model is called anywhere in this file.
"""

import json

import pytest

from app.domain.incidents.models import Incident, IncidentSeverity
from app.domain.primitives import new_id, utc_now
from app.domain.runs.models import BranchpointRun
from app.domain.worlds.models import World
from app.infrastructure.trueforge.commit_operator import (
    COMMIT_OPERATOR_TOOLS,
    CommitNotExecutedError,
    TrueForgeCommitOperator,
    UnsanctionedToolCallError,
)
from app.infrastructure.trueforge.errors import TurnFailedError
from app.infrastructure.trueforge.models import DEFERRED_TOOL_NAME
from app.infrastructure.trueforge.sessions import (
    InMemorySessionBindingStore,
    SessionPurpose,
    SessionStatus,
)
from app.mcp.server import COMMIT_TOOL_NAME, DESTRUCTIVE_TOOL_NAMES, READ_ONLY_TOOL_NAMES
from tests.factories import make_action
from tests.trueforge.fake_transport import FakeTrueForge, FakeTurn

RUN_ID = "run_880c6716124b"
WORLD_ID = "world_34c4d38cba96"
ACTION_ID = "action_12346c1d3cd5"

#: Ids shaped like the ones the live run produced.
CALL_ID = "call_YO9cpiPGwuudxTAywYlHlSch"
SOURCE_EVENT_ID = "evt_model_message_1"

SERVER = "branchpoint"

APPROVED_ARGUMENTS = {
    "run_id": RUN_ID,
    "world_id": WORLD_ID,
    "expected_action_id": ACTION_ID,
}


def make_run_and_world() -> tuple[BranchpointRun, World]:
    """A run/world pair carrying the approved action's identifiers."""
    action = make_action(
        ACTION_ID, name="Disable Pricing V2", parameters={"flag_key": "PRICING_V2"}
    )
    run = BranchpointRun.create(
        run_id=RUN_ID,
        incident=Incident(
            incident_id=new_id("incident"),
            title="Checkout errors",
            goal="Recover checkout",
            severity=IncidentSeverity.CRITICAL,
            detected_at=utc_now(),
        ),
        at=utc_now(),
    )
    world = World.create(world_id=WORLD_ID, run_id=RUN_ID, candidate_action=action, at=utc_now())
    return run, world


# ----- the real wire shape ---------------------------------------------------


def _raw(arguments: object, default: object) -> str:
    """Embed a string argument payload verbatim; serialise anything else."""
    return (
        arguments
        if isinstance(arguments, str)
        else json.dumps(default if arguments is None else arguments)
    )


def tool_call(
    *,
    call_id: str = CALL_ID,
    function_name: str | None = COMMIT_TOOL_NAME,
    info_name: str | None = COMMIT_TOOL_NAME,
    info_server: str | None = SERVER,
    info_type: str = "mcp",
    arguments: object = None,
) -> dict:
    """A **direct** tool call, as TrueForge sends it when the tool is preloaded.

    ``function_name=None`` omits the whole ``function`` object;
    ``info_name=None`` omits ``tool_info``. A string ``arguments`` is embedded
    raw, so malformed JSON can be tested as TrueForge would really deliver it.
    """
    payload: dict = {"id": call_id}
    if function_name is not None:
        payload["function"] = {
            "name": function_name,
            "arguments": _raw(arguments, APPROVED_ARGUMENTS),
        }
    if info_name is not None:
        info: dict = {"type": info_type, "name": info_name}
        if info_server is not None:
            info["server_name"] = info_server
        payload["tool_info"] = info
    return payload


#: What TrueForge 0.1.4 puts on the event stream for a deferred call: the
#: identity of the *wrapper*, not of the operation it will perform.
WRAPPER_INFO = {"type": "truefoundry-system", "name": DEFERRED_TOOL_NAME}


def deferred_call(
    *,
    call_id: str = CALL_ID,
    server: str = SERVER,
    tool: str = COMMIT_TOOL_NAME,
    inner: object = None,
    arguments: object = None,
    tool_info: dict | None = None,
) -> dict:
    """A **deferred** ``call_tool`` wrapper, as the live run produced it.

    ``function.name`` is the generic ``call_tool`` entry point and ``tool_info``
    describes that wrapper. The real target — server, tool, and input — lives
    entirely inside ``function.arguments``, which is the only authority on what
    the call will do.
    """
    envelope = {
        "mcp_server": server,
        "tool_name": tool,
        "input": APPROVED_ARGUMENTS if inner is None else inner,
    }
    payload: dict = {
        "id": call_id,
        "function": {"name": DEFERRED_TOOL_NAME, "arguments": _raw(arguments, envelope)},
        "tool_info": dict(WRAPPER_INFO) if tool_info is None else tool_info,
    }
    return payload


def model_message(*, event_id: str = SOURCE_EVENT_ID, calls: list[dict] | None = None) -> dict:
    """A ``model.message`` event carrying the enriched tool calls it emitted."""
    return {
        "type": "model.message",
        "id": event_id,
        "created_at": "2026-08-25T12:00:00Z",
        "thread_id": "main",
        "content": "Calling the commit tool as instructed.",
        "reasoning_content": "PRIVATE CHAIN OF THOUGHT THAT MUST NOT LEAK",
        "tool_calls": calls if calls is not None else [deferred_call()],
    }


def required_action(
    *, call_id: str = CALL_ID, source_event_id: str = SOURCE_EVENT_ID
) -> list[dict]:
    """The required action: references only — no name, no arguments."""
    return [
        {
            "type": "tool.approval_required",
            "thread_id": "main",
            "tool_calls": [{"id": call_id, "source_event_id": source_event_id}],
        }
    ]


def paused_turn(
    *,
    calls: list[dict] | None = None,
    resumed_calls: list[dict] | None = None,
    events: list[dict] | None = None,
    call_id: str = CALL_ID,
    source_event_id: str = SOURCE_EVENT_ID,
) -> FakeTrueForge:
    """Turn 1 pauses on a tool call; turn 2 is the resumed, completed turn."""
    return FakeTrueForge(
        [
            FakeTurn(
                output="",
                events=events if events is not None else [model_message(calls=calls)],
                required_actions=required_action(call_id=call_id, source_event_id=source_event_id),
            ),
            FakeTurn(
                output="The commit tool reported SUCCEEDED and verification PASSED.",
                events=[model_message(event_id="evt_model_message_2", calls=resumed_calls)],
            ),
        ]
    )


def build_operator(
    fake: FakeTrueForge,
) -> tuple[TrueForgeCommitOperator, InMemorySessionBindingStore]:
    bindings = InMemorySessionBindingStore()
    operator = TrueForgeCommitOperator(fake.client(), model="fake/model", bindings=bindings)
    return operator, bindings


async def denied(fake: FakeTrueForge, match: str) -> None:
    """Assert the operator refuses, and that it actively *denied* the call."""
    operator, _ = build_operator(fake)
    run, world = make_run_and_world()

    with pytest.raises(UnsanctionedToolCallError, match=match):
        await operator.commit(run, world)

    resume = fake.turn_requests[-1]["input"][0]
    assert resume["type"] == "user.tool_approval"
    assert resume["approval"]["status"] == "deny"


# ----- the agent spec --------------------------------------------------------


def test_commit_operator_is_the_least_capable_agent_in_the_system() -> None:
    """One destructive tool, no read tools, no sandbox, no subagents."""
    operator, _ = build_operator(FakeTrueForge([]))
    spec = operator.agent_spec()
    mcp_server = spec["mcp_servers"][0]

    assert mcp_server["enable_tools"] == [COMMIT_TOOL_NAME]
    assert set(mcp_server["enable_tools"]) & set(READ_ONLY_TOOL_NAMES) == set()
    assert set(mcp_server["enable_tools"]) < set(DESTRUCTIVE_TOOL_NAMES)
    assert spec["config"]["sandbox"]["enabled"] is False
    assert spec["config"]["dynamic_sub_agents"]["enabled"] is False


def test_commit_operator_requires_approval_for_its_only_tool() -> None:
    """The destructive call cannot execute unless BRANCHPOINT resumes it."""
    operator, _ = build_operator(FakeTrueForge([]))
    require = operator.agent_spec()["mcp_servers"][0]["require_approval_for_tools"]

    assert COMMIT_TOOL_NAME in require
    assert "@destructive" in require
    assert set(COMMIT_OPERATOR_TOOLS) <= set(require)


# ----- a, b, c, n: identification succeeds on the real shape ------------------


async def test_real_nested_model_message_identifies_the_commit_tool() -> None:
    """a + b + c + n. The live shape resolves, and only then is it approved."""
    fake = paused_turn()
    operator, bindings = build_operator(fake)
    run, world = make_run_and_world()

    report = await operator.commit(run, world)

    resume = fake.turn_requests[-1]["input"][0]
    assert resume["type"] == "user.tool_approval"
    assert resume["approval"] == {"status": "allow"}
    assert resume["tool_call_id"] == CALL_ID
    assert resume["thread_id"] == "main"

    assert report.tool_called is True
    binding = await bindings.get(RUN_ID, SessionPurpose.COMMIT_OPERATOR, world_id=WORLD_ID)
    assert binding.status is SessionStatus.COMPLETED


async def test_identification_precedes_approval_in_the_request_order() -> None:
    """n. Nothing is allowed before the call has been resolved and checked.

    A denied run must never have sent an ``allow`` first — the request log is
    the evidence.
    """
    fake = paused_turn(calls=[tool_call(arguments={**APPROVED_ARGUMENTS, "world_id": "world_x"})])
    operator, _ = build_operator(fake)
    run, world = make_run_and_world()

    with pytest.raises(UnsanctionedToolCallError):
        await operator.commit(run, world)

    approvals = [
        item
        for request in fake.turn_requests
        for item in request["input"]
        if item["type"] == "user.tool_approval"
    ]
    assert [item["approval"]["status"] for item in approvals] == ["deny"]


async def test_only_the_referenced_call_is_approved_when_several_were_emitted() -> None:
    """The chain selects by id — never "the turn made one call, so that is it"."""
    fake = paused_turn(
        calls=[
            tool_call(call_id="call_other", arguments={**APPROVED_ARGUMENTS, "world_id": "w_x"}),
            tool_call(),
        ]
    )
    operator, _ = build_operator(fake)
    run, world = make_run_and_world()

    report = await operator.commit(run, world)

    assert report.tool_called is True
    assert fake.turn_requests[-1]["input"][0]["tool_call_id"] == CALL_ID


async def test_the_operator_prompt_carries_identifiers_and_no_capability() -> None:
    """The model is told which run/world/action — never any capability material."""
    fake = paused_turn()
    operator, _ = build_operator(fake)
    run, world = make_run_and_world()

    await operator.commit(run, world)

    opening = str(fake.turn_requests[0])
    assert RUN_ID in opening and WORLD_ID in opening and ACTION_ID in opening
    assert "capability" not in opening.lower()
    assert "token" not in opening.lower()


# ----- d, e, f, g, l: the reference chain fails closed ------------------------


async def test_wrong_source_event_id_is_denied() -> None:
    """d. A reference to an event that does not exist resolves to nothing."""
    await denied(
        paused_turn(source_event_id="evt_does_not_exist"),
        "could not be resolved from source event",
    )


async def test_missing_source_event_id_is_denied() -> None:
    """d. No reference at all is not an invitation to search the log."""
    await denied(paused_turn(source_event_id=""), "could not be resolved")


async def test_wrong_tool_call_id_is_denied() -> None:
    """e. The source event exists but carries no call with that id."""
    await denied(paused_turn(call_id="call_not_in_that_event"), "could not be resolved")


async def test_ambiguous_duplicate_call_ids_are_denied() -> None:
    """Two calls with the same id inside one event: refuse, do not pick one."""
    await denied(
        paused_turn(calls=[tool_call(), tool_call(arguments={**APPROVED_ARGUMENTS})]),
        "could not be resolved",
    )


async def test_ambiguous_duplicate_source_events_are_denied() -> None:
    """Two events with the same id: refuse, do not pick one."""
    await denied(
        paused_turn(events=[model_message(), model_message()]),
        "could not be resolved",
    )


async def test_missing_function_is_denied() -> None:
    """f. A call with no ``function`` and no ``tool_info`` names nothing."""
    await denied(
        paused_turn(calls=[tool_call(function_name=None, info_name=None)]),
        "has no function name",
    )


async def test_missing_function_arguments_are_denied_even_with_a_name() -> None:
    """f. A resolvable name does not excuse missing arguments."""
    await denied(
        paused_turn(calls=[tool_call(function_name=None)]),
        "has no function name",
    )


async def test_malformed_function_arguments_are_denied() -> None:
    """g. Unparseable arguments cannot be checked, so they cannot be approved."""
    await denied(
        paused_turn(calls=[tool_call(arguments='{"run_id": "run_1", ')]),
        "were unparseable",
    )


async def test_empty_function_arguments_are_denied() -> None:
    """g. An argument-less commit is not a commit BRANCHPOINT approved."""
    await denied(paused_turn(calls=[tool_call(arguments="")]), "were empty")


async def test_non_object_function_arguments_are_denied() -> None:
    """g. A JSON array is valid JSON and still not a commit call."""
    await denied(paused_turn(calls=[tool_call(arguments="[1, 2, 3]")]), "were not an object")


async def test_tool_info_and_function_name_disagreement_is_denied() -> None:
    """l. Two names for one call means BRANCHPOINT cannot say what it is allowing."""
    await denied(
        paused_turn(
            calls=[tool_call(function_name=COMMIT_TOOL_NAME, info_name="branchpoint_get_metrics")]
        ),
        "disagrees with direct call",
    )


async def test_a_different_tool_is_denied() -> None:
    """A resolvable call for the wrong tool is still the wrong tool."""
    await denied(
        paused_turn(
            calls=[
                tool_call(
                    function_name="branchpoint_disable_feature_flag",
                    info_name="branchpoint_disable_feature_flag",
                )
            ]
        ),
        "not the sanctioned",
    )


# ----- h, i, j, k: exact argument binding ------------------------------------


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        pytest.param(
            {**APPROVED_ARGUMENTS, "run_id": "run_someone_elses"},
            "but the human approved",
            id="h: wrong run",
        ),
        pytest.param(
            {**APPROVED_ARGUMENTS, "world_id": "world_alpha"},
            "but the human approved",
            id="i: wrong world",
        ),
        pytest.param(
            {**APPROVED_ARGUMENTS, "expected_action_id": "action_alpha"},
            "but the human approved",
            id="j: wrong action",
        ),
        pytest.param(
            {**APPROVED_ARGUMENTS, "force": "true"},
            "an approved commit takes exactly",
            id="k: extra argument",
        ),
        pytest.param(
            {"run_id": RUN_ID, "world_id": WORLD_ID},
            "an approved commit takes exactly",
            id="k: missing expected_action_id",
        ),
        pytest.param(
            {"run_id": RUN_ID, "world_id": WORLD_ID, "action_id": ACTION_ID},
            "an approved commit takes exactly",
            id="k: renamed argument",
        ),
    ],
)
async def test_commit_arguments_must_match_the_approval_exactly(
    arguments: dict, expected: str
) -> None:
    """h, i, j, k. Every argument is bound; nothing extra, nothing missing."""
    await denied(paused_turn(calls=[tool_call(arguments=arguments)]), expected)


async def test_non_string_commit_arguments_are_denied() -> None:
    """A typed-but-wrong argument is refused rather than coerced."""
    await denied(
        paused_turn(
            calls=[tool_call(arguments='{"run_id": 1, "world_id": 2, "expected_action_id": 3}')]
        ),
        "are not strings",
    )


# ----- m: the old flat shape must not be what makes this work ----------------


async def test_flat_shape_is_not_relied_on() -> None:
    """The earlier regression: flat ``{id, name, arguments}`` is not a real shape.

    If this ever passes as an *approval*, the suite has gone back to testing a
    shape TrueForge does not send, and the live gate will diverge again.
    """
    flat_required = [
        {
            "type": "tool.approval_required",
            "thread_id": "main",
            "tool_calls": [
                {
                    "id": CALL_ID,
                    "source_event_id": SOURCE_EVENT_ID,
                    "name": COMMIT_TOOL_NAME,
                    "arguments": json.dumps(APPROVED_ARGUMENTS),
                }
            ],
        }
    ]
    flat_event = {
        "type": "model.message",
        "id": SOURCE_EVENT_ID,
        "thread_id": "main",
        "content": "calling",
        "tool_calls": [
            {
                "id": CALL_ID,
                "name": COMMIT_TOOL_NAME,
                "arguments": json.dumps(APPROVED_ARGUMENTS),
            }
        ],
    }
    fake = FakeTrueForge(
        [
            FakeTurn(output="", events=[flat_event], required_actions=flat_required),
            FakeTurn(output="never reached"),
        ]
    )

    await denied(fake, "has no function name")


# ----- the deferred wrapper, end to end --------------------------------------


async def test_direct_preloaded_call_is_still_accepted() -> None:
    """1 + 22. If TrueForge ever preloads the tool, the direct form still works."""
    fake = paused_turn(calls=[tool_call()], resumed_calls=[tool_call()])
    operator, _ = build_operator(fake)
    run, world = make_run_and_world()

    report = await operator.commit(run, world)

    assert report.tool_called is True
    assert fake.turn_requests[-1]["input"][0]["approval"] == {"status": "allow"}


async def test_deferred_wrapper_is_accepted_and_reported_as_the_commit_tool() -> None:
    """3 + 4 + 5 + 21. The live shape: call_tool outside, commit tool inside."""
    fake = paused_turn()
    operator, _ = build_operator(fake)
    run, world = make_run_and_world()

    # The fixture is the live shape: the wrapper is all the metadata says, and
    # the real target is only ever visible inside the arguments.
    paused = fake.turns[0].events[0]["tool_calls"][0]
    assert paused["function"]["name"] == DEFERRED_TOOL_NAME
    assert paused["tool_info"] == {"type": "truefoundry-system", "name": DEFERRED_TOOL_NAME}
    assert COMMIT_TOOL_NAME not in json.dumps(paused["tool_info"])
    assert json.loads(paused["function"]["arguments"])["tool_name"] == COMMIT_TOOL_NAME

    report = await operator.commit(run, world)

    assert fake.turn_requests[-1]["input"][0]["approval"] == {"status": "allow"}
    assert report.tool_called is True


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        pytest.param(
            {"server": "someone-elses-server"},
            "not 'branchpoint'",
            id="6: wrong mcp_server",
        ),
        pytest.param(
            {"tool": "branchpoint_disable_feature_flag"},
            "effectively targets",
            id="7: wrong tool_name",
        ),
        pytest.param(
            {"arguments": '{"mcp_server": "branchpoint", '},
            "were unparseable",
            id="8: malformed wrapper JSON",
        ),
        pytest.param(
            {"arguments": json.dumps({"mcp_server": SERVER, "tool_name": COMMIT_TOOL_NAME})},
            "expected exactly",
            id="9: missing input",
        ),
        pytest.param(
            {"inner": "run_id=whatever"},
            "input was not an object",
            id="10: non-object input",
        ),
        pytest.param(
            {"inner": {**APPROVED_ARGUMENTS, "run_id": "run_someone_elses"}},
            "but the human approved",
            id="11: wrong run",
        ),
        pytest.param(
            {"inner": {**APPROVED_ARGUMENTS, "world_id": "world_alpha"}},
            "but the human approved",
            id="12: wrong world",
        ),
        pytest.param(
            {"inner": {**APPROVED_ARGUMENTS, "expected_action_id": "action_alpha"}},
            "but the human approved",
            id="13: wrong action",
        ),
        pytest.param(
            {"inner": {**APPROVED_ARGUMENTS, "force": "true"}},
            "an approved commit takes exactly",
            id="14: extra commit input",
        ),
        pytest.param(
            {"tool_info": {"type": "truefoundry-system", "name": "run_shell"}},
            "expected 'call_tool'",
            id="15: wrapper tool_info names another system tool",
        ),
        pytest.param(
            {
                "tool_info": {
                    "type": "mcp",
                    "name": "branchpoint_get_metrics",
                    "server_name": SERVER,
                }
            },
            "disagrees with deferred tool_name",
            id="16: resolved-MCP metadata names another tool",
        ),
        pytest.param(
            {"tool_info": {"type": "mcp", "name": COMMIT_TOOL_NAME, "server_name": "elsewhere"}},
            "disagrees with deferred mcp_server",
            id="16b: resolved-MCP metadata names another server",
        ),
        pytest.param(
            {"tool_info": {"type": "builtin", "name": COMMIT_TOOL_NAME}},
            "unrecognised tool_info.type",
            id="16c: unrecognised tool_info type",
        ),
    ],
)
async def test_a_deferred_wrapper_that_is_not_the_approved_commit_is_denied(
    kwargs: dict, expected: str
) -> None:
    """6-16. Every way a wrapper can differ from the approval is refused."""
    await denied(paused_turn(calls=[deferred_call(**kwargs)]), expected)


async def test_an_arbitrary_wrapper_function_is_denied() -> None:
    """17. Only ``call_tool`` is a wrapper; anything else is read as a direct call."""
    await denied(
        paused_turn(
            calls=[
                tool_call(
                    function_name="invoke_tool",
                    info_name=None,
                    arguments={"tool_name": COMMIT_TOOL_NAME, "input": APPROVED_ARGUMENTS},
                )
            ]
        ),
        "effectively targets 'invoke_tool'",
    )


async def test_a_wrapper_cannot_smuggle_a_commit_through_another_server() -> None:
    """A well-formed wrapper for the right tool on the wrong server is refused."""
    await denied(
        paused_turn(calls=[deferred_call(server="evil")]),
        "targets MCP server 'evil'",
    )


async def test_the_wrapper_envelope_is_never_mistaken_for_commit_arguments() -> None:
    """The envelope keys must not survive into the effective commit input."""
    await denied(
        paused_turn(
            calls=[
                deferred_call(
                    inner={
                        "mcp_server": SERVER,
                        "tool_name": COMMIT_TOOL_NAME,
                        "input": APPROVED_ARGUMENTS,
                    }
                )
            ]
        ),
        "an approved commit takes exactly",
    )


async def test_a_deferred_denial_never_sends_an_allow_first() -> None:
    """20. Resolution precedes approval, on the live shape too."""
    fake = paused_turn(calls=[deferred_call(inner={**APPROVED_ARGUMENTS, "world_id": "w_x"})])
    operator, _ = build_operator(fake)
    run, world = make_run_and_world()

    with pytest.raises(UnsanctionedToolCallError):
        await operator.commit(run, world)

    statuses = [
        item["approval"]["status"]
        for request in fake.turn_requests
        for item in request["input"]
        if item["type"] == "user.tool_approval"
    ]
    assert statuses == ["deny"]


# ----- turn-level fail-closed ------------------------------------------------


async def test_a_turn_that_never_reaches_the_gate_commits_nothing() -> None:
    """No pause means no destructive call happened; that is an error, not a success."""
    fake = FakeTrueForge([FakeTurn(output="I decided not to call it.")])
    operator, bindings = build_operator(fake)
    run, world = make_run_and_world()

    with pytest.raises(CommitNotExecutedError, match="without reaching the destructive"):
        await operator.commit(run, world)

    binding = await bindings.get(RUN_ID, SessionPurpose.COMMIT_OPERATOR, world_id=WORLD_ID)
    assert binding.status is SessionStatus.FAILED


async def test_a_failed_turn_never_reports_a_commit() -> None:
    """A TrueForge error is an error — never a silent success."""
    fake = FakeTrueForge([FakeTurn(status="error", error="model provider exploded")])
    operator, _ = build_operator(fake)
    run, world = make_run_and_world()

    with pytest.raises(TurnFailedError):
        await operator.commit(run, world)
