"""Role-specific MCP tool exposure: least privilege, and provider portability.

Each TrueForge role gets its own named subset of BRANCHPOINT's read-only MCP
inventory rather than the whole thing. Two independent reasons, both enforced
here:

*Least privilege.* The planner diagnoses reality; the DOPPELGÄNGER attacks one
counterfactual world. Neither needs the other's tools, and neither may reach a
destructive tool.

*Provider portability.* ``branchpoint_reproduce_counterexample`` takes a
``CounterexampleSpec``, whose JSON schema nests a ``$defs`` reference that
Google's function-declaration conversion rejects outright
(``UnsupportedFunctionalityError``: only references to direct children of
root-level ``$defs`` are supported). Any agent handed that tool cannot run on
Gemini. No role needs it: authoritative reproduction happens inside
BRANCHPOINT, in-process, after the adversary returns a spec — never as an
agent-issued tool call.

``READ_ONLY_TOOL_NAMES`` stays the canonical inventory of every read-only tool
and is deliberately *not* trimmed to suit any one provider.
"""

from app.infrastructure.trueforge.adversary import DOPPELGANGER_TOOLS
from app.infrastructure.trueforge.planner import PLANNER_TOOLS, TrueForgeCandidatePlanner
from app.infrastructure.trueforge.sessions import InMemorySessionBindingStore
from app.mcp.server import DESTRUCTIVE_TOOL_NAMES, READ_ONLY_TOOL_NAMES
from tests.trueforge.fake_transport import FakeTrueForge, FakeTurn

#: Every world-inspection tool. Meaningful to a DOPPELGÄNGER inside a world,
#: meaningless to a planner that runs before any world exists.
WORLD_INSPECTION_TOOLS = frozenset(
    {
        "branchpoint_get_world",
        "branchpoint_get_world_action",
        "branchpoint_get_world_metrics",
        "branchpoint_get_world_orders_summary",
        "branchpoint_get_compatibility_context",
    }
)

#: The tool whose ``CounterexampleSpec`` schema Google's conversion rejects.
REPRODUCTION_TOOL = "branchpoint_reproduce_counterexample"

#: The reality tools the planner is intended to have — spelled out literally
#: rather than derived from ``PLANNER_TOOLS``, so widening the constant fails
#: this test instead of silently redefining what "intended" means.
EXPECTED_PLANNER_TOOLS = frozenset(
    {
        "branchpoint_get_incident",
        "branchpoint_get_metrics",
        "branchpoint_get_deployment",
        "branchpoint_get_feature_flags",
        "branchpoint_get_schema",
        "branchpoint_get_orders_summary",
        "branchpoint_get_reality_state",
    }
)


def planner_enabled_tools() -> set[str]:
    """The tool names a production-wired planner actually sends to TrueForge."""
    planner = TrueForgeCandidatePlanner(
        FakeTrueForge([FakeTurn(output="{}")]).client(),
        model="fake/model",
        bindings=InMemorySessionBindingStore(),
        read_only_tools=PLANNER_TOOLS,
    )
    mcp_server = planner.agent_spec()["mcp_servers"][0]
    assert set(mcp_server["preload_tools"]) == set(mcp_server["enable_tools"])
    return set(mcp_server["enable_tools"])


# ----- planner ---------------------------------------------------------------


def test_planner_exposes_exactly_the_intended_reality_tools() -> None:
    assert planner_enabled_tools() == EXPECTED_PLANNER_TOOLS
    assert len(PLANNER_TOOLS) == len(set(PLANNER_TOOLS)) == len(EXPECTED_PLANNER_TOOLS)


def test_planner_cannot_reach_any_world_inspection_tool() -> None:
    """Worlds do not exist yet when the planner runs."""
    assert not planner_enabled_tools() & WORLD_INSPECTION_TOOLS


def test_planner_cannot_reach_the_counterexample_reproduction_tool() -> None:
    """The Gemini-incompatible ``CounterexampleSpec`` schema never reaches the planner."""
    assert REPRODUCTION_TOOL not in planner_enabled_tools()


def test_planner_cannot_reach_any_destructive_tool() -> None:
    assert not planner_enabled_tools() & set(DESTRUCTIVE_TOOL_NAMES)


def test_planner_default_tool_set_is_least_privilege() -> None:
    """A planner wired without an explicit tool list still gets only its own tools.

    The permissive fallback is the ``@read-only`` selector, which would hand it
    the whole inventory — including the reproduction tool. The default must not
    take that path.
    """
    planner = TrueForgeCandidatePlanner(
        FakeTrueForge([FakeTurn(output="{}")]).client(),
        model="fake/model",
        bindings=InMemorySessionBindingStore(),
    )
    assert set(planner.agent_spec()["mcp_servers"][0]["enable_tools"]) == EXPECTED_PLANNER_TOOLS


# ----- DOPPELGÄNGER ----------------------------------------------------------


def test_doppelganger_retains_the_required_world_inspection_tools() -> None:
    assert WORLD_INSPECTION_TOOLS <= set(DOPPELGANGER_TOOLS)


def test_doppelganger_cannot_reach_any_destructive_tool() -> None:
    assert not set(DOPPELGANGER_TOOLS) & set(DESTRUCTIVE_TOOL_NAMES)


def test_doppelganger_does_not_need_the_reproduction_tool() -> None:
    """Reproduction is BRANCHPOINT's job, in-process, after the spec comes back."""
    assert REPRODUCTION_TOOL not in DOPPELGANGER_TOOLS


# ----- the canonical inventory is untouched ----------------------------------


def test_global_mcp_inventory_remains_seventeen_tools() -> None:
    """Role scoping narrows what agents *see*, never what the server *exposes*."""
    inventory = set(READ_ONLY_TOOL_NAMES) | set(DESTRUCTIVE_TOOL_NAMES)
    assert len(READ_ONLY_TOOL_NAMES) == 13
    assert len(DESTRUCTIVE_TOOL_NAMES) == 4
    assert len(inventory) == 17


def test_canonical_inventory_still_carries_every_role_scoped_tool() -> None:
    """Both role sets are subsets of the read-only inventory, never additions to it."""
    read_only = set(READ_ONLY_TOOL_NAMES)
    assert set(PLANNER_TOOLS) < read_only
    assert set(DOPPELGANGER_TOOLS) < read_only
    assert REPRODUCTION_TOOL in read_only
    assert WORLD_INSPECTION_TOOLS <= read_only
