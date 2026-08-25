"""TrueForge DOPPELGÄNGER: subagents, sandbox, replay, and fail-closed behaviour."""

import json

import pytest

from app.domain.actions.models import ActionType
from app.domain.primitives import utc_now
from app.domain.worlds.lifecycle import WorldStatus
from app.domain.worlds.models import CounterexampleStatus, World, WorldExecutionReport, WorldVerdict
from app.domain.worlds.verdicts import derive_verdict
from app.infrastructure.demo.adapters import DemoWorldExecutor
from app.infrastructure.demo.engine import DemoProductionEngine
from app.infrastructure.trueforge.adversary import (
    DOPPELGANGER_TOOLS,
    TrueForgeAdversarialTester,
)
from app.infrastructure.trueforge.errors import TrueForgeError, TurnFailedError
from app.infrastructure.trueforge.sessions import InMemorySessionBindingStore, SessionPurpose
from app.mcp.server import DESTRUCTIVE_TOOL_NAMES
from tests.factories import make_action
from tests.trueforge.fake_transport import (
    FakeTrueForge,
    FakeTurn,
    model_message_event,
    sandbox_created_event,
    thread_created_event,
    tool_response_event,
)

ALPHA_ACTION = make_action(
    "action_alpha",
    name="Roll back pricing-service to v2.40",
    action_type=ActionType.ROLLBACK,
    parameters={"version": "v2.40"},
)
BETA_ACTION = make_action(
    "action_beta",
    name="Disable PRICING_V2",
    action_type=ActionType.FEATURE_FLAG_DISABLE,
    parameters={"flag_key": "PRICING_V2"},
)

#: The counterexample a competent DOPPELGÄNGER should derive for a rollback:
#: expressed only in generic version/schema vocabulary.
COMPATIBILITY_ATTACK = {
    "hypothesis": "An older runtime cannot interpret records written by the newer one.",
    "investigated": "Compared world deployment version against order schema versions; "
    "ran a reproducer in the sandbox.",
    "counterexample": {
        "counterexample_type": "COMPATIBILITY",
        "operation": "RETRY_PAYMENT",
        "setup": {"created_under_version": "v2.41", "min_schema_version": 41, "order_id": None},
        "assertion": {"kind": "CHECK_PASSES", "check_name": "data_integrity"},
        "expected": "payment retry stays idempotent for records written by the newer version",
        "rationale": "The world's deployment predates the schema those records use.",
    },
}

NO_FINDING = {
    "hypothesis": "Probed compatibility, integrity, and metrics; found nothing replayable.",
    "investigated": "Ran several sandbox probes.",
    "counterexample": None,
}


def adversarial_events() -> list[dict]:
    """Events showing a real subagent + sandbox + tool usage."""
    return [
        thread_created_event("thread_doppel_1"),
        sandbox_created_event("sbx_alpha"),
        model_message_event("investigating", thread_id="thread_doppel_1"),
        tool_response_event("call_1", "world metrics", thread_id="thread_doppel_1"),
    ]


async def executed_world(engine: DemoProductionEngine, world_id: str, action) -> World:
    """Drive a world through real Phase 2 execution so it has a snapshot to attack."""
    executor = DemoWorldExecutor(engine)
    world = World.create(world_id=world_id, run_id="run_1", candidate_action=action, at=utc_now())
    world = world.transition_to(WorldStatus.PREPARING).transition_to(WorldStatus.EXECUTING)
    report: WorldExecutionReport = await executor.execute(world)
    world = world.record_execution(report)
    return world.transition_to(WorldStatus.ATTACKING)


def build_tester(fake: FakeTrueForge, engine: DemoProductionEngine, **kwargs):
    bindings = InMemorySessionBindingStore()
    tester = TrueForgeAdversarialTester(
        fake.client(), engine, model="fake/model", bindings=bindings, **kwargs
    )
    return tester, bindings


async def test_adversary_uses_a_real_subagent_and_sandbox() -> None:
    """With the sandbox opted into — it is off unless configured on."""
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    fake = FakeTrueForge(
        [FakeTurn(output=json.dumps(COMPATIBILITY_ATTACK), events=adversarial_events())]
    )
    tester, _ = build_tester(fake, engine, sandbox_enabled=True)

    report = await tester.attack(world)

    spec = fake.created_sessions[0]["agent"]["spec"]
    assert spec["config"]["dynamic_sub_agents"]["enabled"] is True
    assert spec["config"]["sandbox"]["enabled"] is True
    sandbox_evidence = [e for e in report.evidence if e.source == "trueforge-doppelganger"]
    assert sandbox_evidence, "sandbox/subagent provenance should be recorded"
    assert "subagents=1" in str(sandbox_evidence[0].observed)
    assert "sandboxes=1" in str(sandbox_evidence[0].observed)


async def test_sandbox_evidence_is_never_machine_verifiable() -> None:
    """Sandbox output is exploratory: it can never contribute to a veto."""
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    fake = FakeTrueForge(
        [FakeTurn(output=json.dumps(COMPATIBILITY_ATTACK), events=adversarial_events())]
    )
    tester, _ = build_tester(fake, engine, sandbox_enabled=True)

    report = await tester.attack(world)

    for evidence in report.evidence:
        if evidence.source == "trueforge-doppelganger":
            assert evidence.machine_verifiable is False
            assert evidence.disqualifies is False


async def test_reproduced_alpha_counterexample_produces_valid_evidence_and_vetoes() -> None:
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    fake = FakeTrueForge(
        [FakeTurn(output=json.dumps(COMPATIBILITY_ATTACK), events=adversarial_events())]
    )
    tester, _ = build_tester(fake, engine)

    report = await tester.attack(world)
    attacked = world.record_attacks(report).transition_to(WorldStatus.EVALUATING)
    verdict, reason = derive_verdict(attacked)

    assert report.counterexamples[0].status is CounterexampleStatus.REPRODUCED
    replay = [e for e in report.evidence if e.source == "branchpoint-counterexample-replay"]
    assert replay and replay[0].machine_verifiable and replay[0].disqualifies
    assert verdict is WorldVerdict.VETOED
    assert "reproduced counterexample" in reason


async def test_the_same_attack_does_not_veto_beta() -> None:
    """Beta is attacked with the identical spec and genuinely survives."""
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_beta", BETA_ACTION)
    fake = FakeTrueForge(
        [FakeTurn(output=json.dumps(COMPATIBILITY_ATTACK), events=adversarial_events())]
    )
    tester, _ = build_tester(fake, engine)

    report = await tester.attack(world)
    attacked = world.record_attacks(report).transition_to(WorldStatus.EVALUATING)
    verdict, _ = derive_verdict(attacked)

    assert report.counterexamples[0].status is CounterexampleStatus.NOT_REPRODUCED
    assert verdict is WorldVerdict.SURVIVED


async def test_prose_only_criticism_cannot_veto() -> None:
    """An adversary that only complains produces no veto."""
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    prose = {
        "hypothesis": "This rollback is extremely dangerous and obviously unsafe.",
        "investigated": "I thought about it carefully.",
        "counterexample": None,
    }
    fake = FakeTrueForge([FakeTurn(output=json.dumps(prose), events=adversarial_events())])
    tester, _ = build_tester(fake, engine)

    report = await tester.attack(world)
    attacked = world.record_attacks(report).transition_to(WorldStatus.EVALUATING)
    verdict, _ = derive_verdict(attacked)

    assert report.counterexamples[0].status is CounterexampleStatus.NOT_REPRODUCED
    assert verdict is WorldVerdict.SURVIVED


async def test_malformed_counterexample_spec_is_rejected_not_honoured() -> None:
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    malformed = json.loads(json.dumps(COMPATIBILITY_ATTACK))
    malformed["counterexample"]["operation"] = "DROP_DATABASE"
    fake = FakeTrueForge([FakeTurn(output=json.dumps(malformed), events=adversarial_events())])
    tester, _ = build_tester(fake, engine)

    report = await tester.attack(world)

    assert report.counterexamples[0].status is CounterexampleStatus.ERROR
    assert not any(e.source == "branchpoint-counterexample-replay" for e in report.evidence), (
        "a rejected spec must never produce replay evidence"
    )


async def test_arbitrary_code_cannot_enter_the_reproduction_engine() -> None:
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    injected = json.loads(json.dumps(COMPATIBILITY_ATTACK))
    injected["counterexample"]["assertion"] = {
        "kind": "CHECK_PASSES",
        "check_name": "__import__('os').system('rm -rf /')",
    }
    fake = FakeTrueForge([FakeTurn(output=json.dumps(injected), events=adversarial_events())])
    tester, _ = build_tester(fake, engine)

    report = await tester.attack(world)

    assert report.counterexamples[0].status is CounterexampleStatus.ERROR


async def test_turn_failure_raises_so_the_world_becomes_inconclusive() -> None:
    """A model/sandbox failure must never read as 'this world is safe'."""
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    fake = FakeTrueForge([FakeTurn(status="error", error="sandbox unavailable")])
    tester, _ = build_tester(fake, engine)

    with pytest.raises(TurnFailedError):
        await tester.attack(world)


async def test_adversary_cannot_reach_any_mutation_tool() -> None:
    engine = DemoProductionEngine()
    fake = FakeTrueForge([])
    tester, _ = build_tester(fake, engine)

    spec = tester.agent_spec("run_1", "world_alpha")
    enabled = set(spec["mcp_servers"][0]["enable_tools"])

    assert enabled == set(DOPPELGANGER_TOOLS)
    assert not enabled & set(DESTRUCTIVE_TOOL_NAMES)


async def test_adversary_is_told_the_run_id_its_world_tools_need() -> None:
    """Regression: every world tool is keyed on ``(run_id, world_id)``.

    The adversary has no tool that lists runs, so a brief naming only the world
    left it unable to call a single world tool. It then had nothing to reason
    from but reality and reported no finding — a silent loss of the entire
    adversarial evidence path.
    """
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    fake = FakeTrueForge([FakeTurn(output=json.dumps(NO_FINDING))])
    tester, _ = build_tester(fake, engine)

    instructions = tester.agent_spec(world.run_id, world.world_id)["instructions"]
    assert world.run_id in instructions

    await tester.attack(world)

    sent = str(fake.turn_requests[0])
    assert world.run_id in sent
    assert world.world_id in sent


async def test_adversary_agent_spec_sends_no_temperature() -> None:
    """The configured reasoning model rejects ``temperature``; we must not send it."""
    engine = DemoProductionEngine()
    tester, _ = build_tester(FakeTrueForge([]), engine)

    assert "params" not in tester.agent_spec("run_1", "world_alpha")["model"]


async def test_adversary_paused_for_approval_fails_closed() -> None:
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    fake = FakeTrueForge(
        [
            FakeTurn(
                output="",
                required_actions=[
                    {
                        "type": "tool.approval_required",
                        "thread_id": "main",
                        "tool_calls": [{"id": "c1", "source_event_id": "e1"}],
                    }
                ],
            )
        ]
    )
    tester, _ = build_tester(fake, engine)

    with pytest.raises(TrueForgeError, match="adversaries may not mutate"):
        await tester.attack(world)


async def test_adversary_creates_a_per_world_session_binding() -> None:
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    fake = FakeTrueForge(
        [FakeTurn(output=json.dumps(COMPATIBILITY_ATTACK), events=adversarial_events())]
    )
    tester, bindings = build_tester(fake, engine)

    await tester.attack(world)

    binding = await bindings.get("run_1", SessionPurpose.ADVERSARY, world_id="world_alpha")
    assert binding is not None
    assert binding.trueforge_session_id == "sess_1"
    assert binding.world_id == "world_alpha"


async def test_replay_runs_against_the_world_snapshot_never_reality() -> None:
    engine = DemoProductionEngine()
    reality_before = await engine.reality()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    fake = FakeTrueForge(
        [FakeTurn(output=json.dumps(COMPATIBILITY_ATTACK), events=adversarial_events())]
    )
    tester, _ = build_tester(fake, engine)

    await tester.attack(world)

    assert await engine.reality() == reality_before
