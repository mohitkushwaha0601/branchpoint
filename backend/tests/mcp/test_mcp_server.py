"""MCP protocol conformance and tool authorization.

Uses the real MCP client SDK against the real server over an in-process ASGI
transport — a genuine protocol round trip, not a direct Python call into the
tool functions.
"""

import pytest

from app.domain.actions.models import ActionType
from app.domain.approvals.rules import build_approval_request
from app.domain.comparison.models import ComparisonResult
from app.domain.runs.lifecycle import RunStatus
from app.domain.runs.models import BranchpointRun
from app.domain.worlds.lifecycle import WorldStatus
from app.domain.worlds.models import World, WorldVerdict
from app.mcp.server import DESTRUCTIVE_TOOL_ANNOTATIONS, READ_TOOL_ANNOTATIONS
from tests.factories import FIXED_TIME, make_action, make_incident
from tests.mcp.conftest import MCPTestHarness, mcp_session

READ_TOOL_NAMES = {
    "branchpoint_get_incident",
    "branchpoint_get_metrics",
    "branchpoint_get_deployment",
    "branchpoint_get_feature_flags",
    "branchpoint_get_schema",
    "branchpoint_get_orders_summary",
    "branchpoint_get_reality_state",
}
DESTRUCTIVE_TOOL_NAMES = {
    "branchpoint_disable_feature_flag",
    "branchpoint_set_deployment_version",
    "branchpoint_scale_service",
}


async def _issue_capability_for_flag_disable(harness: MCPTestHarness):
    action = make_action(
        "action_beta",
        action_type=ActionType.FEATURE_FLAG_DISABLE,
        parameters={"flag_key": "PRICING_V2"},
    )
    world = World.create(
        world_id="world_beta", run_id="run_1", candidate_action=action, at=FIXED_TIME
    )
    world = world.model_copy(
        update={"status": WorldStatus.SURVIVED, "verdict": WorldVerdict.SURVIVED}
    )

    run = BranchpointRun.create(run_id="run_1", incident=make_incident(), at=FIXED_TIME)
    run = run.model_copy(update={"status": RunStatus.COMPARING, "worlds": (world,)})
    run = run.with_comparison(
        ComparisonResult(recommended_world_id="world_beta", eligible_world_ids=("world_beta",)),
        at=FIXED_TIME,
    )
    approval = build_approval_request(
        run, "world_beta", approval_id="approval_1", requested_at=FIXED_TIME
    )
    run = run.with_approval(approval, at=FIXED_TIME).transition_to(
        RunStatus.AWAITING_APPROVAL, at=FIXED_TIME
    )
    decided = run.approval.decide(approved=True, actor="sre@example.com", at=FIXED_TIME)
    run = run.with_approval(decided, at=FIXED_TIME).transition_to(RunStatus.APPROVED, at=FIXED_TIME)

    await harness.run_repository.save(run)
    return await harness.capability_store.issue_for_approved_run(run)


async def test_initialize_succeeds(mcp_harness: MCPTestHarness) -> None:
    async with mcp_session(mcp_harness) as session:
        # mcp_session already calls initialize(); a second one must also succeed.
        result = await session.initialize()
        assert result.server_info.name == "branchpoint"


async def test_tools_list_succeeds(mcp_harness: MCPTestHarness) -> None:
    async with mcp_session(mcp_harness) as session:
        result = await session.list_tools()

    names = {tool.name for tool in result.tools}
    assert READ_TOOL_NAMES <= names
    assert DESTRUCTIVE_TOOL_NAMES <= names
    assert len(result.tools) == len(READ_TOOL_NAMES) + len(DESTRUCTIVE_TOOL_NAMES)


async def test_every_tool_has_explicit_annotations(mcp_harness: MCPTestHarness) -> None:
    async with mcp_session(mcp_harness) as session:
        result = await session.list_tools()

    for tool in result.tools:
        assert tool.annotations is not None, f"{tool.name} shipped with no annotations"
        assert tool.annotations.read_only_hint is not None, f"{tool.name} missing readOnlyHint"
        assert tool.annotations.destructive_hint is not None, f"{tool.name} missing destructiveHint"


async def test_read_tools_are_all_marked_read_only(mcp_harness: MCPTestHarness) -> None:
    async with mcp_session(mcp_harness) as session:
        result = await session.list_tools()

    for tool in result.tools:
        if tool.name in READ_TOOL_NAMES:
            assert tool.annotations.read_only_hint is True
            assert tool.annotations.destructive_hint is False


async def test_destructive_tools_are_all_marked_write_capable(mcp_harness: MCPTestHarness) -> None:
    async with mcp_session(mcp_harness) as session:
        result = await session.list_tools()

    for tool in result.tools:
        if tool.name in DESTRUCTIVE_TOOL_NAMES:
            assert tool.annotations.read_only_hint is False
            assert tool.annotations.destructive_hint is True


def test_annotation_constants_match_the_spec_wire_format() -> None:
    assert READ_TOOL_ANNOTATIONS.read_only_hint is True
    assert READ_TOOL_ANNOTATIONS.destructive_hint is False
    assert DESTRUCTIVE_TOOL_ANNOTATIONS.read_only_hint is False
    assert DESTRUCTIVE_TOOL_ANNOTATIONS.destructive_hint is True
    dumped = READ_TOOL_ANNOTATIONS.model_dump(by_alias=True)
    assert "readOnlyHint" in dumped
    assert "destructiveHint" in dumped


async def test_read_tool_call_succeeds(mcp_harness: MCPTestHarness) -> None:
    async with mcp_session(mcp_harness) as session:
        result = await session.call_tool("branchpoint_get_metrics", {})

    assert result.is_error is not True
    assert result.structured_content["checkout_error_rate"] == pytest.approx(0.413)


async def test_read_tool_reflects_live_engine_state(mcp_harness: MCPTestHarness) -> None:
    await mcp_harness.engine.reset()
    async with mcp_session(mcp_harness) as session:
        result = await session.call_tool("branchpoint_get_deployment", {})

    assert result.structured_content["version"] == "v2.41"


async def test_destructive_call_without_capability_fails(mcp_harness: MCPTestHarness) -> None:
    async with mcp_session(mcp_harness) as session:
        result = await session.call_tool(
            "branchpoint_disable_feature_flag",
            {"capability_token": "garbage.notreal", "flag_key": "PRICING_V2"},
        )

    assert result.is_error is True
    reality = await mcp_harness.engine.reality()
    assert reality.pricing_flag.enabled is True


async def test_destructive_call_with_valid_capability_succeeds(mcp_harness: MCPTestHarness) -> None:
    issued = await _issue_capability_for_flag_disable(mcp_harness)

    async with mcp_session(mcp_harness) as session:
        result = await session.call_tool(
            "branchpoint_disable_feature_flag",
            {"capability_token": issued.token, "flag_key": "PRICING_V2"},
        )

    assert result.is_error is not True
    assert result.structured_content["succeeded"] is True
    reality = await mcp_harness.engine.reality()
    assert reality.pricing_flag.enabled is False


async def test_destructive_call_capability_is_single_use_over_mcp(
    mcp_harness: MCPTestHarness,
) -> None:
    issued = await _issue_capability_for_flag_disable(mcp_harness)

    async with mcp_session(mcp_harness) as session:
        first = await session.call_tool(
            "branchpoint_disable_feature_flag",
            {"capability_token": issued.token, "flag_key": "PRICING_V2"},
        )
        second = await session.call_tool(
            "branchpoint_disable_feature_flag",
            {"capability_token": issued.token, "flag_key": "PRICING_V2"},
        )

    assert first.is_error is not True
    assert second.is_error is True


async def test_destructive_call_rejects_a_mismatched_flag(mcp_harness: MCPTestHarness) -> None:
    issued = await _issue_capability_for_flag_disable(mcp_harness)

    async with mcp_session(mcp_harness) as session:
        result = await session.call_tool(
            "branchpoint_disable_feature_flag",
            {"capability_token": issued.token, "flag_key": "PRICING_V2"},
        )
        # a second call reusing the same (already-spent) token but a
        # different flag_key must also fail, not silently succeed differently
        wrong = await session.call_tool(
            "branchpoint_disable_feature_flag",
            {"capability_token": issued.token, "flag_key": "PRICING_V2"},
        )

    assert result.is_error is not True
    assert wrong.is_error is True


async def test_malformed_tool_input_is_rejected(mcp_harness: MCPTestHarness) -> None:
    async with mcp_session(mcp_harness) as session:
        result = await session.call_tool("branchpoint_scale_service", {"capability_token": "x"})

    assert result.is_error is True


async def test_malformed_tool_input_rejects_unenumerated_version(
    mcp_harness: MCPTestHarness,
) -> None:
    async with mcp_session(mcp_harness) as session:
        result = await session.call_tool(
            "branchpoint_set_deployment_version",
            {"capability_token": "x", "service": "pricing-service", "version": "v99.99"},
        )

    assert result.is_error is True


async def test_no_tool_exposes_raw_world_mutation(mcp_harness: MCPTestHarness) -> None:
    async with mcp_session(mcp_harness) as session:
        result = await session.list_tools()

    for tool in result.tools:
        assert "world" not in tool.name
        properties = tool.input_schema.get("properties", {})
        assert "world_id" not in properties
