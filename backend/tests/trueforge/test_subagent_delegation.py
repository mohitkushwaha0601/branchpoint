"""The bounded subagent delegation, and why it changes no authority.

TrueForge's dynamic-subagent mechanism is model-directed: the harness exposes a
local ``create_sub_agent`` tool and the model decides to call it. So the brief
is the mechanism, and what these tests pin down is that asking for a delegation
grants nothing — not a tool, not a capability, and above all not the ability to
veto a world.
"""

import inspect
import json

import pytest

from app.domain.worlds.lifecycle import WorldStatus
from app.domain.worlds.models import CounterexampleStatus, WorldVerdict
from app.domain.worlds.verdicts import derive_verdict
from app.infrastructure.demo.engine import DemoProductionEngine
from app.infrastructure.trueforge.adversary import (
    DELEGATING_ACTION_TYPES,
    DOPPELGANGER_TOOLS,
    SANDBOX_EVIDENCE_SOURCE,
)
from app.infrastructure.trueforge.commit_operator import TrueForgeCommitOperator
from app.infrastructure.trueforge.models import SUBAGENT_TOOL_NAME
from app.infrastructure.trueforge.planner import PLANNER_TOOLS, TrueForgeCandidatePlanner
from app.infrastructure.trueforge.prompts import doppelganger_instructions
from app.infrastructure.trueforge.sessions import InMemorySessionBindingStore
from app.mcp.server import DESTRUCTIVE_TOOL_NAMES
from tests.trueforge.fake_transport import FakeTrueForge, FakeTurn
from tests.trueforge.test_adversary import (
    ALPHA_ACTION,
    BETA_ACTION,
    COMPATIBILITY_ATTACK,
    build_tester,
    executed_world,
)
from tests.trueforge.test_sandbox_boundary import (
    REPLAY_EVIDENCE_SOURCE,
    sandbox_events,
)

#: What a delegating adversary's session looks like: a real nested thread, and
#: a subagent that came back with prose.
SUBAGENT_PROSE = {
    "hypothesis": "My Compatibility Skeptic subagent confirms this rollback is broken.",
    "investigated": "Delegated to a subagent; it reported a schema risk.",
    "counterexample": None,
}


# ----- the brief asks for exactly one delegation, on the right world ----------


def test_the_rollback_world_is_told_to_delegate_exactly_once() -> None:
    instructions = doppelganger_instructions("run_1", "world_alpha", delegate_subagent=True)

    assert SUBAGENT_TOOL_NAME in instructions
    assert "Compatibility Skeptic" in instructions
    assert "EXACTLY ONE" in instructions
    assert "Do not let the subagent delegate further" in instructions


def test_other_worlds_are_not_told_to_delegate() -> None:
    """One delegation on the rollback is the point; a tree of them is not."""
    instructions = doppelganger_instructions("run_1", "world_beta", delegate_subagent=False)

    assert SUBAGENT_TOOL_NAME not in instructions
    assert "Compatibility Skeptic" not in instructions


async def test_only_the_rollback_world_gets_the_delegation_brief() -> None:
    engine = DemoProductionEngine()
    tester, _ = build_tester(FakeTrueForge([]), engine)

    rollback = tester.agent_spec("run_1", "world_alpha", delegate_subagent=True)
    other = tester.agent_spec("run_1", "world_beta", delegate_subagent=False)

    assert SUBAGENT_TOOL_NAME in rollback["instructions"]
    assert SUBAGENT_TOOL_NAME not in other["instructions"]


async def test_the_adversary_delegates_on_a_rollback_and_not_on_a_flag_flip() -> None:
    """Wired end to end: the action family decides, not a caller's flag."""
    engine = DemoProductionEngine()

    for action, world_id, expected in (
        (ALPHA_ACTION, "world_alpha", True),
        (BETA_ACTION, "world_beta", False),
    ):
        world = await executed_world(engine, world_id, action)
        fake = FakeTrueForge(
            [FakeTurn(output=json.dumps(COMPATIBILITY_ATTACK), events=sandbox_events())]
        )
        tester, _ = build_tester(fake, engine, sandbox_enabled=True)

        await tester.attack(world)

        instructions = fake.created_sessions[0]["agent"]["spec"]["instructions"]
        assert (SUBAGENT_TOOL_NAME in instructions) is expected, world_id


def test_rollback_is_the_only_delegating_family() -> None:
    assert [str(family) for family in DELEGATING_ACTION_TYPES] == ["ROLLBACK"]


# ----- delegating grants no capability ---------------------------------------


async def test_asking_for_a_delegation_exposes_no_extra_tool() -> None:
    """A subagent inherits this session's tools — which are read-only world tools."""
    engine = DemoProductionEngine()
    tester, _ = build_tester(FakeTrueForge([]), engine, sandbox_enabled=True)

    delegating = tester.agent_spec("run_1", "world_alpha", delegate_subagent=True)
    plain = tester.agent_spec("run_1", "world_alpha", delegate_subagent=False)

    assert delegating["mcp_servers"] == plain["mcp_servers"]
    enabled = set(delegating["mcp_servers"][0]["enable_tools"])
    assert enabled == set(DOPPELGANGER_TOOLS)
    assert not enabled & set(DESTRUCTIVE_TOOL_NAMES)
    assert delegating["config"]["sandbox"] == plain["config"]["sandbox"]


async def test_the_brief_tells_the_subagent_its_output_is_a_hypothesis() -> None:
    instructions = doppelganger_instructions("run_1", "world_alpha", delegate_subagent=True)

    assert "EXPLORATORY" in instructions
    assert "it is not evidence" in instructions
    assert "cannot veto anything" in instructions


# ----- subagent output stays non-authoritative -------------------------------


async def test_subagent_findings_are_recorded_machine_verifiable_false() -> None:
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    fake = FakeTrueForge([FakeTurn(output=json.dumps(SUBAGENT_PROSE), events=sandbox_events())])
    tester, _ = build_tester(fake, engine, sandbox_enabled=True)

    report = await tester.attack(world)

    session_evidence = [e for e in report.evidence if e.source == SANDBOX_EVIDENCE_SOURCE]
    assert session_evidence
    for evidence in session_evidence:
        assert evidence.machine_verifiable is False
        assert evidence.disqualifies is False


async def test_a_subagents_confident_prose_cannot_veto_a_world() -> None:
    """The whole point: a second model saying "broken" is still a model saying it."""
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    fake = FakeTrueForge([FakeTurn(output=json.dumps(SUBAGENT_PROSE), events=sandbox_events())])
    tester, _ = build_tester(fake, engine, sandbox_enabled=True)

    report = await tester.attack(world)
    attacked = world.record_attacks(report).transition_to(WorldStatus.EVALUATING)
    verdict, reason = derive_verdict(attacked)

    assert report.counterexamples[0].status is CounterexampleStatus.NOT_REPRODUCED
    assert not any(e.source == REPLAY_EVIDENCE_SOURCE for e in report.evidence)
    assert verdict is WorldVerdict.SURVIVED
    assert "no reproduced counterexample" in reason


@pytest.mark.parametrize("delegated", [True, False])
async def test_authoritative_replay_still_vetoes_either_way(delegated: bool) -> None:
    """Delegation does not change the one path that can veto."""
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    fake = FakeTrueForge(
        [FakeTurn(output=json.dumps(COMPATIBILITY_ATTACK), events=sandbox_events())]
    )
    tester, _ = build_tester(fake, engine, sandbox_enabled=delegated)

    report = await tester.attack(world)
    attacked = world.record_attacks(report).transition_to(WorldStatus.EVALUATING)
    verdict, reason = derive_verdict(attacked)

    replay = [e for e in report.evidence if e.source == REPLAY_EVIDENCE_SOURCE]
    assert any(e.machine_verifiable and e.is_failing for e in replay)
    assert report.counterexamples[0].status is CounterexampleStatus.REPRODUCED
    assert verdict is WorldVerdict.VETOED
    assert "reproduced counterexample" in reason


# ----- the optional TrueForge Skill ------------------------------------------


async def test_no_skill_is_mounted_by_default() -> None:
    """The hero path is untouched: no `skills` key unless one is configured."""
    tester, _ = build_tester(FakeTrueForge([]), DemoProductionEngine())

    spec = tester.agent_spec("run_1", "world_alpha")

    assert "skills" not in spec


async def test_a_configured_skill_is_mounted_by_name() -> None:
    tester, _ = build_tester(
        FakeTrueForge([]),
        DemoProductionEngine(),
        skill_name="incident-counterfactual-review",
    )

    spec = tester.agent_spec("run_1", "world_alpha")

    assert spec["skills"] == [{"name": "incident-counterfactual-review"}]


async def test_mounting_a_skill_grants_no_extra_capability() -> None:
    engine = DemoProductionEngine()
    plain, _ = build_tester(FakeTrueForge([]), engine)
    skilled, _ = build_tester(FakeTrueForge([]), engine, skill_name="a-skill")

    with_skill = skilled.agent_spec("run_1", "world_alpha")
    without = plain.agent_spec("run_1", "world_alpha")

    assert with_skill["mcp_servers"] == without["mcp_servers"]
    assert with_skill["config"] == without["config"]


async def test_no_other_role_can_be_given_a_skill() -> None:
    """The skill setting reaches the adversary's spec builder and nowhere else.

    TrueForge materialises a skill inside the sandbox, and the planner and the
    commit operator both run with the sandbox off — so a skill on either of them
    would be a resource TrueForge could not place, on the two roles that read
    and write reality. Neither builder accepts a skill name at all, and this
    pins that shut.
    """
    planner = TrueForgeCandidatePlanner(
        FakeTrueForge([]).client(),
        model="fake/model",
        bindings=InMemorySessionBindingStore(),
        read_only_tools=PLANNER_TOOLS,
    )
    operator = TrueForgeCommitOperator(
        FakeTrueForge([]).client(),
        model="fake/model",
        bindings=InMemorySessionBindingStore(),
    )

    assert "skills" not in planner.agent_spec()
    assert "skills" not in operator.agent_spec()
    # Neither builder even has somewhere to put one.
    for builder in (TrueForgeCandidatePlanner, TrueForgeCommitOperator):
        assert "skill_name" not in inspect.signature(builder.__init__).parameters
