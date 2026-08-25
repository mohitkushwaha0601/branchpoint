"""The TrueForge side of the commit: pause, inspect, resume — or deny.

These tests exercise the real ``TrueForgeCommitOperator`` against the fake
transport, so the actual request building and the actual
``user.tool_approval`` resume payload are under test. No model is called.

TrueForge's approval mechanism is the transport-level gate here, not the human
decision: the human already approved in BRANCHPOINT. What matters is that
BRANCHPOINT only ever *replays* that recorded decision onto a tool call that
matches it exactly, and denies anything else.
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
from app.infrastructure.trueforge.sessions import (
    InMemorySessionBindingStore,
    SessionPurpose,
    SessionStatus,
)
from app.mcp.server import COMMIT_TOOL_NAME, DESTRUCTIVE_TOOL_NAMES, READ_ONLY_TOOL_NAMES
from tests.factories import make_action
from tests.trueforge.fake_transport import FakeTrueForge, FakeTurn

RUN_ID = "run_1"
WORLD_ID = "world_beta"
ACTION_ID = "action_beta"


def make_run_and_world() -> tuple[BranchpointRun, World]:
    """A minimal run/world pair carrying the approved action's identifiers."""
    action = make_action(ACTION_ID, parameters={"flag_key": "PRICING_V2"})
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


def approval_required(
    *,
    name: str = COMMIT_TOOL_NAME,
    arguments: dict | None = None,
    call_id: str = "call_commit_1",
) -> list[dict]:
    """A ``tool.approval_required`` required action, shaped as TrueForge sends it."""
    payload = (
        arguments
        if arguments is not None
        else {"run_id": RUN_ID, "world_id": WORLD_ID, "expected_action_id": ACTION_ID}
    )
    return [
        {
            "type": "tool.approval_required",
            "thread_id": "main",
            "tool_calls": [
                {
                    "id": call_id,
                    "source_event_id": "evt_1",
                    "name": name,
                    "arguments": json.dumps(payload),
                }
            ],
        }
    ]


def paused_then_committed(**pause: object) -> FakeTrueForge:
    """Turn 1 pauses on the commit call; turn 2 is the resumed, completed turn."""
    return FakeTrueForge(
        [
            FakeTurn(output="", required_actions=approval_required(**pause)),
            FakeTurn(
                output="The commit tool reported SUCCEEDED and verification PASSED.",
                events=[
                    {
                        "type": "tool.response",
                        "id": "evt_tool_1",
                        "thread_id": "main",
                        "tool_call_id": "call_commit_1",
                        "tool_calls": [{"id": "call_commit_1", "name": COMMIT_TOOL_NAME}],
                        "content": "committed",
                    }
                ],
            ),
        ]
    )


def build_operator(
    fake: FakeTrueForge,
) -> tuple[TrueForgeCommitOperator, InMemorySessionBindingStore]:
    bindings = InMemorySessionBindingStore()
    operator = TrueForgeCommitOperator(fake.client(), model="fake/model", bindings=bindings)
    return operator, bindings


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


# ----- the sanctioned path ---------------------------------------------------


async def test_approved_commit_pauses_then_resumes_with_an_allow() -> None:
    """The happy path: pause at the gate, then one explicit allow."""
    fake = paused_then_committed()
    operator, bindings = build_operator(fake)
    run, world = make_run_and_world()

    report = await operator.commit(run, world)

    assert report.tool_called is True
    resume = fake.turn_requests[-1]["input"][0]
    assert resume["type"] == "user.tool_approval"
    assert resume["tool_call_id"] == "call_commit_1"
    assert resume["thread_id"] == "main"
    assert resume["approval"] == {"status": "allow"}

    binding = await bindings.get(RUN_ID, SessionPurpose.COMMIT_OPERATOR, world_id=WORLD_ID)
    assert binding is not None
    assert binding.status is SessionStatus.COMPLETED


async def test_the_operator_prompt_carries_identifiers_and_no_capability() -> None:
    """The model is told which run/world/action — never any capability material."""
    fake = paused_then_committed()
    operator, _ = build_operator(fake)
    run, world = make_run_and_world()

    await operator.commit(run, world)

    opening = str(fake.turn_requests[0])
    assert RUN_ID in opening and WORLD_ID in opening and ACTION_ID in opening
    assert "capability" not in opening.lower()
    assert "token" not in opening.lower()


# ----- fail closed -----------------------------------------------------------


async def test_a_turn_that_never_reaches_the_gate_commits_nothing() -> None:
    """No pause means no destructive call happened; that is an error, not a success."""
    fake = FakeTrueForge([FakeTurn(output="I decided not to call it.")])
    operator, bindings = build_operator(fake)
    run, world = make_run_and_world()

    with pytest.raises(CommitNotExecutedError, match="without reaching the destructive"):
        await operator.commit(run, world)

    binding = await bindings.get(RUN_ID, SessionPurpose.COMMIT_OPERATOR, world_id=WORLD_ID)
    assert binding.status is SessionStatus.FAILED


@pytest.mark.parametrize(
    ("pause", "expected"),
    [
        pytest.param(
            {"name": "branchpoint_disable_feature_flag"},
            "not the sanctioned",
            id="a different destructive tool",
        ),
        pytest.param(
            {"arguments": {"run_id": RUN_ID, "world_id": "world_alpha"}},
            "but the human approved",
            id="a different world",
        ),
        pytest.param(
            {
                "arguments": {
                    "run_id": RUN_ID,
                    "world_id": WORLD_ID,
                    "expected_action_id": "action_alpha",
                }
            },
            "but the human approved",
            id="a different action",
        ),
        pytest.param(
            {"arguments": {"run_id": "run_other", "world_id": WORLD_ID}},
            "but the human approved",
            id="a different run",
        ),
    ],
)
async def test_an_unsanctioned_paused_call_is_denied_not_allowed(
    pause: dict, expected: str
) -> None:
    """Anything other than the exact approved commit is denied at the gate."""
    fake = paused_then_committed(**pause)
    operator, _ = build_operator(fake)
    run, world = make_run_and_world()

    with pytest.raises(UnsanctionedToolCallError, match=expected):
        await operator.commit(run, world)

    resume = fake.turn_requests[-1]["input"][0]
    assert resume["type"] == "user.tool_approval"
    assert resume["approval"]["status"] == "deny"


async def test_an_unidentifiable_paused_call_is_denied() -> None:
    """A call whose name cannot be read is refused rather than approved blind."""
    fake = FakeTrueForge(
        [
            FakeTurn(
                output="",
                required_actions=[
                    {
                        "type": "tool.approval_required",
                        "thread_id": "main",
                        "tool_calls": [{"id": "call_unknown", "source_event_id": "evt_1"}],
                    }
                ],
            ),
            FakeTurn(output="denied"),
        ]
    )
    operator, _ = build_operator(fake)
    run, world = make_run_and_world()

    with pytest.raises(UnsanctionedToolCallError, match="could not be identified"):
        await operator.commit(run, world)


async def test_a_failed_turn_never_reports_a_commit() -> None:
    """A TrueForge error is an error — never a silent success."""
    fake = FakeTrueForge([FakeTurn(status="error", error="model provider exploded")])
    operator, _ = build_operator(fake)
    run, world = make_run_and_world()

    with pytest.raises(TurnFailedError):
        await operator.commit(run, world)
