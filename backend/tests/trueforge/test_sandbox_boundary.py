"""The TrueForge sandbox authority boundary.

Phase 3.6 gives the DOPPELGÄNGER — and only the DOPPELGÄNGER — an isolated
TrueForge sandbox it may execute code in, gated on
``BRANCHPOINT_TRUEFORGE_SANDBOX_ENABLED``. These tests pin the boundary that
makes that safe:

*Exposure.* The sandbox is one role's exploratory capability. The planner reads
reality and the commit operator writes to it; neither ever gets code
execution, whatever the adversary is configured with. Turning the sandbox on
adds no tool to any session.

*Authority.* Anything originating in that session — sandbox ``exec``, sandbox
files, sandbox scripts, subagent prose, model prose — is recorded with
``machine_verifiable=False`` and can never mark a counterexample REPRODUCED or
veto a world. The only route to a veto stays: proposed spec → BRANCHPOINT's own
deterministic replay → machine-verifiable failing evidence → REPRODUCED → VETO.

*Fail closed.* A sandbox that reports a failure it cannot express as a
replayable spec, or a session that dies mid-attack, must never read as "this
world was safely attacked".

No model is called: every turn here is scripted through the fake transport.
"""

import inspect
import json
import sys

import httpx
import pytest

from app.api.dependencies import build_agent_orchestrator, build_commit_operator
from app.core.config import Settings
from app.domain.evidence.models import Evidence, EvidenceKind, EvidenceSeverity
from app.domain.primitives import new_id, utc_now
from app.domain.worlds.lifecycle import WorldStatus
from app.domain.worlds.models import (
    AdversarialReport,
    Counterexample,
    CounterexampleStatus,
    WorldVerdict,
)
from app.domain.worlds.verdicts import counterexample_vetoes, derive_verdict
from app.infrastructure.demo.engine import DemoProductionEngine
from app.infrastructure.trueforge.adversary import (
    DOPPELGANGER_TOOLS,
    SANDBOX_EVIDENCE_SOURCE,
    TrueForgeAdversarialTester,
)
from app.infrastructure.trueforge.commit_operator import (
    COMMIT_OPERATOR_TOOLS,
    TrueForgeCommitOperator,
)
from app.infrastructure.trueforge.errors import StructuredOutputError, TurnFailedError
from app.infrastructure.trueforge.models import TurnEvent
from app.infrastructure.trueforge.planner import PLANNER_TOOLS, TrueForgeCandidatePlanner
from app.infrastructure.trueforge.sessions import InMemorySessionBindingStore
from app.mcp.server import DESTRUCTIVE_TOOL_NAMES
from scripts import smoke_trueforge as smoke
from tests.trueforge.fake_transport import (
    FakeTrueForge,
    FakeTurn,
    model_message_event,
    sandbox_created_event,
    sandbox_exec_event,
    thread_created_event,
    tool_response_event,
)
from tests.trueforge.test_adversary import (
    ALPHA_ACTION,
    BETA_ACTION,
    COMPATIBILITY_ATTACK,
    build_tester,
    executed_world,
)

#: Source BRANCHPOINT's own replay engine stamps on the only evidence that may
#: disqualify a world.
REPLAY_EVIDENCE_SOURCE = "branchpoint-counterexample-replay"

#: A sandbox run that "proves" a failure. Deliberately loud: a zero exit code,
#: a confident stdout, and matching model prose. None of it is evidence.
SANDBOX_PROOF_STDOUT = json.dumps(
    {
        "exitCode": 0,
        "stdout": "FAIL: 3/3 legacy orders lost payment_revision. INVARIANT VIOLATED.",
        "stderr": "",
    }
)


def sandbox_events(*, exec_call_id: str = "call_exec_1") -> list[dict]:
    """A turn in which the subagent provisioned a sandbox and ran code in it."""
    return [
        thread_created_event("thread_doppel_1"),
        sandbox_created_event("sbx_alpha"),
        sandbox_exec_event(exec_call_id, command="python3 /tmp/probe.py"),
        tool_response_event(exec_call_id, SANDBOX_PROOF_STDOUT, thread_id="thread_doppel_1"),
        model_message_event("the sandbox proved it", thread_id="thread_doppel_1"),
    ]


#: What the model says when it believes its sandbox settled the question but has
#: no replayable spec to offer. Confidence, provenance, and an exit code — and
#: still nothing BRANCHPOINT can check.
SANDBOX_ASSERTED_FAILURE = {
    "hypothesis": "My sandbox script reproduced the failure: this world is definitively broken.",
    "investigated": "Wrote /tmp/probe.py, executed it in the sandbox, exit code 0, output FAIL.",
    "counterexample": None,
}


def adversary_spec(*, sandbox_enabled: bool) -> dict:
    """The agent spec a DOPPELGÄNGER wired with ``sandbox_enabled`` would send."""
    tester, _ = build_tester(
        FakeTrueForge([]), DemoProductionEngine(), sandbox_enabled=sandbox_enabled
    )
    return tester.agent_spec("run_1", "world_alpha")


def planner_spec() -> dict:
    """The agent spec a production-wired planner would send."""
    planner = TrueForgeCandidatePlanner(
        FakeTrueForge([]).client(),
        model="fake/model",
        bindings=InMemorySessionBindingStore(),
        read_only_tools=PLANNER_TOOLS,
    )
    return planner.agent_spec()


def commit_operator_spec() -> dict:
    """The agent spec the commit operator would send."""
    operator = TrueForgeCommitOperator(
        FakeTrueForge([]).client(),
        model="fake/model",
        bindings=InMemorySessionBindingStore(),
    )
    return operator.agent_spec()


# ----- 1-2. the flag is the whole switch --------------------------------------


def test_sandbox_execution_is_opt_in_at_every_default() -> None:
    """Unset means off — in the settings the docs describe, and in the adapter.

    ``Settings()`` would read this repo's own ``.env``, so the field default is
    asserted directly: the guarantee is about a deployment that configures
    nothing at all.
    """
    assert Settings.model_fields["trueforge_sandbox_enabled"].default is False
    assert (
        inspect.signature(TrueForgeAdversarialTester.__init__).parameters["sandbox_enabled"].default
        is False
    )


def test_an_unconfigured_deployment_gets_no_sandbox() -> None:
    """The end-to-end reading of the default: no env, no ``.env``, no sandbox."""
    settings = Settings(_env_file=None, model="fake/model")
    tester = TrueForgeAdversarialTester(
        FakeTrueForge([]).client(),
        DemoProductionEngine(),
        model=settings.resolve_model(),
        bindings=InMemorySessionBindingStore(),
        sandbox_enabled=settings.trueforge_sandbox_enabled,
    )

    assert tester.agent_spec("run_1", "world_alpha")["config"]["sandbox"] == {"enabled": False}


def test_doppelganger_has_no_sandbox_when_the_flag_is_off() -> None:
    assert adversary_spec(sandbox_enabled=False)["config"]["sandbox"]["enabled"] is False


def test_doppelganger_has_a_sandbox_when_the_flag_is_on() -> None:
    assert adversary_spec(sandbox_enabled=True)["config"]["sandbox"]["enabled"] is True


def test_the_brief_never_promises_a_sandbox_the_session_does_not_have() -> None:
    """A model told it has a sandbox it lacks burns iterations on calls that cannot work."""
    on = adversary_spec(sandbox_enabled=True)["instructions"]
    off = adversary_spec(sandbox_enabled=False)["instructions"]

    assert "isolated sandbox" in on
    assert "`exec`" in on
    assert "no sandbox in this run" in off
    assert "`exec`" not in off
    # The authority boundary is stated either way: an opinion never vetoes.
    for instructions in (on, off):
        assert "You do not get to veto with an opinion" in instructions


# ----- 3-4. no other role ever gets one ---------------------------------------


def test_planner_has_no_sandbox_and_no_setting_that_could_give_it_one() -> None:
    """The planner reads *reality*. It is never given code execution."""
    spec = planner_spec()

    assert spec["config"]["sandbox"]["enabled"] is False
    assert spec["config"]["dynamic_sub_agents"]["enabled"] is False


def test_commit_operator_has_no_sandbox_and_no_setting_that_could_give_it_one() -> None:
    """The one role that can mutate reality is the least capable agent in the system."""
    spec = commit_operator_spec()

    assert spec["config"]["sandbox"]["enabled"] is False
    assert spec["config"]["dynamic_sub_agents"]["enabled"] is False
    assert set(spec["mcp_servers"][0]["enable_tools"]) == set(COMMIT_OPERATOR_TOOLS)


@pytest.mark.parametrize("configured", [True, False])
def test_the_setting_reaches_the_adversary_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch, configured: bool
) -> None:
    """Production wiring, not hand-built adapters: where does the flag actually land?

    ``BRANCHPOINT_TRUEFORGE_SANDBOX_ENABLED`` is read once, in the composition
    root. This is the regression that matters — someone threading the same
    setting into ``TrueForgeCandidatePlanner`` or ``TrueForgeCommitOperator``
    would hand code execution to a role that reads or writes reality.
    """
    settings = Settings(model="fake/model", trueforge_sandbox_enabled=configured)
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)

    orchestrator = build_agent_orchestrator()
    operator = build_commit_operator()

    assert orchestrator._adversarial_tester.sandbox_enabled is configured
    assert orchestrator._adversarial_tester.agent_spec("run_1", "world_alpha")["config"][
        "sandbox"
    ] == {"enabled": configured}
    assert orchestrator._planner.agent_spec()["config"]["sandbox"] == {"enabled": False}
    assert operator.agent_spec()["config"]["sandbox"] == {"enabled": False}


def test_only_the_doppelganger_role_can_ever_carry_a_sandbox() -> None:
    """Exactly one of the three specs varies with the flag, and only in ``sandbox``."""
    enabled = [
        spec
        for spec in (
            adversary_spec(sandbox_enabled=True),
            planner_spec(),
            commit_operator_spec(),
        )
        if spec["config"]["sandbox"]["enabled"]
    ]
    assert len(enabled) == 1
    assert set(enabled[0]["mcp_servers"][0]["enable_tools"]) == set(DOPPELGANGER_TOOLS)


# ----- 5. enabling the sandbox widens nothing else -----------------------------


def test_enabling_the_sandbox_exposes_no_destructive_branchpoint_tool() -> None:
    mcp_server = adversary_spec(sandbox_enabled=True)["mcp_servers"][0]
    enabled = set(mcp_server["enable_tools"])

    assert enabled == set(DOPPELGANGER_TOOLS)
    assert not enabled & set(DESTRUCTIVE_TOOL_NAMES)
    assert mcp_server["require_approval_for_tools"] == ["@write", "@destructive"]


def test_the_sandbox_flag_changes_nothing_but_the_sandbox_flag() -> None:
    """Tool exposure, approval policy, and subagents are identical either way."""
    on = adversary_spec(sandbox_enabled=True)
    off = adversary_spec(sandbox_enabled=False)

    assert on["mcp_servers"] == off["mcp_servers"]
    assert on["config"]["dynamic_sub_agents"] == off["config"]["dynamic_sub_agents"]
    assert on["config"]["iteration_limit"] == off["config"]["iteration_limit"]
    assert on["config"]["sandbox"] != off["config"]["sandbox"]


# ----- 6. sandbox-derived evidence is never authoritative ----------------------


async def test_sandbox_derived_evidence_is_not_machine_verifiable() -> None:
    """Sandbox exec, sandbox files, subagent prose: all provenance, never proof."""
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    fake = FakeTrueForge(
        [FakeTurn(output=json.dumps(COMPATIBILITY_ATTACK), events=sandbox_events())]
    )
    tester, _ = build_tester(fake, engine, sandbox_enabled=True)

    report = await tester.attack(world)

    sandbox = [e for e in report.evidence if e.source == SANDBOX_EVIDENCE_SOURCE]
    assert sandbox, "sandbox provenance should still be recorded"
    for evidence in sandbox:
        assert evidence.machine_verifiable is False
        assert evidence.disqualifies is False
        assert evidence.severity is EvidenceSeverity.INFO


async def test_a_reproduced_counterexample_cites_replay_evidence_only() -> None:
    """The veto's evidence chain must not run through anything the session produced."""
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    fake = FakeTrueForge(
        [FakeTurn(output=json.dumps(COMPATIBILITY_ATTACK), events=sandbox_events())]
    )
    tester, _ = build_tester(fake, engine, sandbox_enabled=True)

    report = await tester.attack(world)
    counterexample = report.counterexamples[0]
    by_id = {item.evidence_id: item for item in report.evidence}
    cited = [by_id[eid] for eid in counterexample.evidence_ids]

    assert counterexample.status is CounterexampleStatus.REPRODUCED
    assert cited, "a reproduced counterexample must cite its replay evidence"
    assert all(item.source == REPLAY_EVIDENCE_SOURCE for item in cited)
    assert not any(item.source == SANDBOX_EVIDENCE_SOURCE for item in cited)


# ----- 7-8. sandbox output alone reproduces nothing and vetoes nothing ---------


async def test_a_sandbox_asserted_failure_cannot_mark_a_counterexample_reproduced() -> None:
    """Exit code 0 and "INVARIANT VIOLATED" on stdout are still just output."""
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    fake = FakeTrueForge(
        [FakeTurn(output=json.dumps(SANDBOX_ASSERTED_FAILURE), events=sandbox_events())]
    )
    tester, _ = build_tester(fake, engine, sandbox_enabled=True)

    report = await tester.attack(world)

    assert report.counterexamples[0].status is CounterexampleStatus.NOT_REPRODUCED
    assert not any(e.source == REPLAY_EVIDENCE_SOURCE for e in report.evidence)
    assert not any(e.machine_verifiable and e.is_failing for e in report.evidence)


async def test_a_sandbox_asserted_failure_cannot_veto_a_world() -> None:
    """The world that the sandbox "proved" broken still survives on the evidence."""
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    fake = FakeTrueForge(
        [FakeTurn(output=json.dumps(SANDBOX_ASSERTED_FAILURE), events=sandbox_events())]
    )
    tester, _ = build_tester(fake, engine, sandbox_enabled=True)

    report = await tester.attack(world)
    attacked = world.record_attacks(report).transition_to(WorldStatus.EVALUATING)
    verdict, reason = derive_verdict(attacked)

    assert verdict is WorldVerdict.SURVIVED
    assert "no reproduced counterexample" in reason


async def test_a_sandbox_backed_spec_that_does_not_replay_does_not_veto() -> None:
    """The sandbox may be certain; replay is what decides. Beta survives the same attack."""
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_beta", BETA_ACTION)
    insistent = json.loads(json.dumps(COMPATIBILITY_ATTACK))
    insistent["hypothesis"] = "Confirmed in my sandbox: this world is broken beyond doubt."
    fake = FakeTrueForge([FakeTurn(output=json.dumps(insistent), events=sandbox_events())])
    tester, _ = build_tester(fake, engine, sandbox_enabled=True)

    report = await tester.attack(world)
    attacked = world.record_attacks(report).transition_to(WorldStatus.EVALUATING)
    verdict, _ = derive_verdict(attacked)

    assert report.counterexamples[0].status is CounterexampleStatus.NOT_REPRODUCED
    assert verdict is WorldVerdict.SURVIVED


def test_even_a_forged_reproduced_status_cannot_veto_on_sandbox_evidence() -> None:
    """Defense in depth: the domain rule, not the adapter, is the last line.

    Constructed by hand rather than through the adapter — the adapter cannot
    produce this — so the guarantee holds even if some future caller marked a
    counterexample REPRODUCED off sandbox output.
    """
    sandbox_evidence = Evidence(
        evidence_id=new_id("evidence"),
        kind=EvidenceKind.COUNTEREXAMPLE,
        source=SANDBOX_EVIDENCE_SOURCE,
        claim="sandbox script observed the invariant break",
        world_id="world_alpha",
        observed=SANDBOX_PROOF_STDOUT,
        expected="invariant holds",
        passed=False,
        severity=EvidenceSeverity.CRITICAL,
        machine_verifiable=False,
        recorded_at=utc_now(),
    )
    forged = Counterexample(
        attack_id=new_id("attack"),
        world_id="world_alpha",
        title="sandbox says it breaks",
        hypothesis="the sandbox reproduced it",
        created_at=utc_now(),
        evidence_ids=(sandbox_evidence.evidence_id,),
        status=CounterexampleStatus.REPRODUCED,
    )

    assert not counterexample_vetoes(forged, {sandbox_evidence.evidence_id: sandbox_evidence})


async def test_a_world_attacked_only_from_the_sandbox_is_not_left_unverified() -> None:
    """Surviving still requires machine-verifiable evidence from somewhere real."""
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    fake = FakeTrueForge(
        [FakeTurn(output=json.dumps(SANDBOX_ASSERTED_FAILURE), events=sandbox_events())]
    )
    tester, _ = build_tester(fake, engine, sandbox_enabled=True)

    report = await tester.attack(world)
    sandbox_only = AdversarialReport(
        counterexamples=report.counterexamples,
        evidence=tuple(e for e in report.evidence if e.source == SANDBOX_EVIDENCE_SOURCE),
    )
    stripped = world.model_copy(update={"evidence": ()})
    attacked = stripped.record_attacks(sandbox_only).transition_to(WorldStatus.EVALUATING)
    verdict, reason = derive_verdict(attacked)

    assert verdict is WorldVerdict.INCONCLUSIVE
    assert reason == "no machine-verifiable evidence was produced"


# ----- 9-10. the authoritative path is untouched -------------------------------


async def test_backend_replay_still_produces_machine_verifiable_failing_evidence() -> None:
    """The one path that may create disqualifying evidence, with the sandbox on."""
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    fake = FakeTrueForge(
        [FakeTurn(output=json.dumps(COMPATIBILITY_ATTACK), events=sandbox_events())]
    )
    tester, _ = build_tester(fake, engine, sandbox_enabled=True)

    report = await tester.attack(world)

    replay = [e for e in report.evidence if e.source == REPLAY_EVIDENCE_SOURCE]
    assert replay
    assert any(e.machine_verifiable and e.is_failing and e.disqualifies for e in replay)
    assert report.counterexamples[0].status is CounterexampleStatus.REPRODUCED


@pytest.mark.parametrize("sandbox_enabled", [True, False])
async def test_reproduced_backend_evidence_still_vetoes_with_or_without_a_sandbox(
    sandbox_enabled: bool,
) -> None:
    """The veto is identical either way: the sandbox is not part of the chain."""
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    events = sandbox_events() if sandbox_enabled else [thread_created_event("thread_doppel_1")]
    fake = FakeTrueForge([FakeTurn(output=json.dumps(COMPATIBILITY_ATTACK), events=events)])
    tester, _ = build_tester(fake, engine, sandbox_enabled=sandbox_enabled)

    report = await tester.attack(world)
    attacked = world.record_attacks(report).transition_to(WorldStatus.EVALUATING)
    verdict, reason = derive_verdict(attacked)

    assert verdict is WorldVerdict.VETOED
    assert "reproduced counterexample" in reason


# ----- 11. malformed sandbox findings fail closed ------------------------------


async def test_a_malformed_sandbox_finding_is_rejected_not_promoted() -> None:
    """An unreplayable operation is an ERROR attack, and produces no evidence."""
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    malformed = json.loads(json.dumps(COMPATIBILITY_ATTACK))
    malformed["counterexample"]["operation"] = "RUN_SANDBOX_SCRIPT"
    fake = FakeTrueForge([FakeTurn(output=json.dumps(malformed), events=sandbox_events())])
    tester, _ = build_tester(fake, engine, sandbox_enabled=True)

    report = await tester.attack(world)
    attacked = world.record_attacks(report).transition_to(WorldStatus.EVALUATING)
    verdict, _ = derive_verdict(attacked)

    assert report.counterexamples[0].status is CounterexampleStatus.ERROR
    assert not any(e.source == REPLAY_EVIDENCE_SOURCE for e in report.evidence)
    assert verdict is not WorldVerdict.VETOED


async def test_a_sandbox_finding_that_is_not_json_fails_closed() -> None:
    """Sandbox stdout pasted back as prose is not a finding, and must not be salvaged."""
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    fake = FakeTrueForge(
        [FakeTurn(output="my sandbox printed FAIL, so veto it", events=sandbox_events())]
    )
    tester, _ = build_tester(fake, engine, sandbox_enabled=True)

    with pytest.raises(StructuredOutputError):
        await tester.attack(world)


async def test_a_dead_sandbox_session_never_reads_as_a_safe_attack() -> None:
    """Sandbox provisioning or exec failure raises, so the world goes INCONCLUSIVE."""
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    fake = FakeTrueForge(
        [FakeTurn(status="error", error="sandbox provisioning failed: daytona unreachable")]
    )
    tester, _ = build_tester(fake, engine, sandbox_enabled=True)

    with pytest.raises(TurnFailedError):
        await tester.attack(world)


# ----- live-smoke observability ------------------------------------------------
#
# The smoke script is how the one live sandbox-enabled E2E is proven. Its
# inspection helpers are pure and are tested here deterministically, so the live
# run is spent proving the *feature* rather than debugging the probe. Nothing
# below calls a model: the same fake transport serves TrueForge.


@pytest.fixture(autouse=True)
def isolated_smoke_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test its own stage ledger.

    ``record`` appends to a module-level list and the script's exit code is
    derived from it, so a shared ledger would let one test's failure decide
    another test's result.
    """
    monkeypatch.setattr(smoke, "_results", [])


def last_result() -> tuple[str, str, str]:
    """The most recent stage the smoke script recorded."""
    return smoke._results[-1]


def test_smoke_reads_a_sandbox_flag_out_of_a_nested_session_payload() -> None:
    payload = {
        "data": {"id": "sess_1", "agent": {"spec": {"config": {"sandbox": {"enabled": True}}}}}
    }
    assert smoke._find_sandbox_enabled(payload) is True


def test_smoke_reads_a_disabled_sandbox_flag_as_disabled() -> None:
    payload = {"agent": {"spec": {"config": {"sandbox": {"enabled": False}}}}}
    assert smoke._find_sandbox_enabled(payload) is False


def test_smoke_reports_unknown_when_trueforge_does_not_echo_the_spec() -> None:
    """A shape change upstream must degrade to "unknown", never to a wrong answer."""
    assert smoke._find_sandbox_enabled({"data": {"id": "sess_1", "title": None}}) is None


def test_smoke_counts_only_answered_sandbox_exec_calls() -> None:
    events = tuple(TurnEvent.model_validate(event) for event in sandbox_events())

    assert smoke._sandbox_exec_responses(events) == ["call_exec_1"]


def test_smoke_never_mistakes_a_branchpoint_mcp_call_for_sandbox_exec() -> None:
    """Read-only world tools are not code execution, whatever they are named."""
    mcp_call = {
        "type": "model.message",
        "id": "evt_mcp_1",
        "thread_id": "thread_doppel_1",
        "content": "",
        "tool_calls": [
            {
                "id": "call_mcp_1",
                "function": {
                    "name": "branchpoint_get_world_metrics",
                    "arguments": '{"run_id": "run_1", "world_id": "world_alpha"}',
                },
                "tool_info": {
                    "type": "mcp",
                    "name": "branchpoint_get_world_metrics",
                    "server_name": "branchpoint",
                },
            }
        ],
    }
    events = tuple(
        TurnEvent.model_validate(event)
        for event in [
            thread_created_event("thread_doppel_1"),
            mcp_call,
            tool_response_event("call_mcp_1", "{}", thread_id="thread_doppel_1"),
        ]
    )

    assert smoke._sandbox_exec_responses(events) == []


async def test_smoke_proves_sandbox_use_from_trueforge_events_alone() -> None:
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    fake = FakeTrueForge(
        [FakeTurn(output=json.dumps(COMPATIBILITY_ATTACK), events=sandbox_events())]
    )
    tester, _ = build_tester(fake, engine, sandbox_enabled=True)
    await tester.attack(world)

    client = fake.client()
    sessions = [
        {"purpose": "ADVERSARY", "trueforge_session_id": "sess_1", "last_turn_id": "turn_1"}
    ]
    passed = await smoke.stage_sandbox_observability(client, sessions, require_sandbox=True)
    await client.aclose()

    stage, status, detail = last_result()
    assert passed is True
    assert status == smoke.PASS
    assert "sandbox.created=1" in detail
    assert "exec tool.response=1" in detail


async def test_smoke_will_not_accept_model_prose_as_proof_of_sandbox_use() -> None:
    """A turn where the model only *says* it ran something proves nothing."""
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    prose_only = [
        thread_created_event("thread_doppel_1"),
        model_message_event(
            "I provisioned a Daytona sandbox and ran my probe there; exit code 0.",
            thread_id="thread_doppel_1",
        ),
    ]
    fake = FakeTrueForge([FakeTurn(output=json.dumps(SANDBOX_ASSERTED_FAILURE), events=prose_only)])
    tester, _ = build_tester(fake, engine, sandbox_enabled=True)
    await tester.attack(world)

    client = fake.client()
    sessions = [
        {"purpose": "ADVERSARY", "trueforge_session_id": "sess_1", "last_turn_id": "turn_1"}
    ]
    passed = await smoke.stage_sandbox_observability(client, sessions, require_sandbox=True)
    await client.aclose()

    _, status, _ = last_result()
    assert passed is False
    assert status == smoke.FAIL


async def test_smoke_stays_green_without_a_sandbox_when_it_is_not_required() -> None:
    """The sandbox is opt-in: a run without one must not fail the smoke test."""
    engine = DemoProductionEngine()
    world = await executed_world(engine, "world_alpha", ALPHA_ACTION)
    fake = FakeTrueForge(
        [
            FakeTurn(
                output=json.dumps(COMPATIBILITY_ATTACK),
                events=[thread_created_event("thread_doppel_1")],
            )
        ]
    )
    tester, _ = build_tester(fake, engine, sandbox_enabled=False)
    await tester.attack(world)

    client = fake.client()
    sessions = [
        {"purpose": "ADVERSARY", "trueforge_session_id": "sess_1", "last_turn_id": "turn_1"}
    ]
    passed = await smoke.stage_sandbox_observability(client, sessions, require_sandbox=False)
    await client.aclose()

    _, status, _ = last_result()
    assert passed is True
    assert status == smoke.SKIP


# ----- the sandbox assertion cannot be silently skipped ------------------------
#
# ``--require-sandbox`` is the flag that turns the live E2E into proof. A run
# carrying it must never exit 0 without stage 14 having actually asserted
# something — not when another flag suppresses the live flow, and not when the
# environment cannot produce one.


class NoNetworkHTTP:
    """Stands in for the smoke script's own HTTP client: every request refuses.

    These tests are about exit codes, so anything that escapes the stages under
    test must fail loudly rather than reach a real socket.
    """

    def __init__(self, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> "NoNetworkHTTP":
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False

    async def get(self, *args: object, **kwargs: object) -> object:
        raise httpx.ConnectError("no network in tests")

    async def post(self, *args: object, **kwargs: object) -> object:
        raise httpx.ConnectError("no network in tests")


async def _passing_stage(*args: object, **kwargs: object) -> bool:
    return True


async def run_smoke_cli(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    fake: FakeTrueForge,
    *,
    backend_reachable: bool = True,
) -> int:
    """Run the smoke script's whole CLI offline and return its exit code."""
    client = fake.client()
    monkeypatch.setattr(smoke.httpx, "AsyncClient", NoNetworkHTTP)
    monkeypatch.setattr(smoke, "TrueForgeClient", lambda **kwargs: client)
    monkeypatch.setattr(sys, "argv", ["smoke_trueforge.py", *argv])
    if backend_reachable:
        for stage in (
            "stage_backend_health",
            "stage_trueforge_health",
            "stage_mcp_visible",
            "stage_tool_annotations",
        ):
            monkeypatch.setattr(smoke, stage, _passing_stage)
    try:
        return await smoke.main()
    finally:
        await client.aclose()


async def test_require_sandbox_refuses_to_run_alongside_checks_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Honouring both would exit 0 having asserted nothing at all."""
    monkeypatch.setattr(sys, "argv", ["smoke_trueforge.py", "--checks-only", "--require-sandbox"])

    with pytest.raises(SystemExit) as exit_info:
        await smoke.main()

    assert exit_info.value.code == 2


async def test_require_sandbox_fails_when_no_model_provider_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a provider there is no live run, so there is nothing to prove."""
    exit_code = await run_smoke_cli(monkeypatch, ["--require-sandbox"], FakeTrueForge(models=[]))

    assert exit_code == 1
    assert any(status == smoke.FAIL for _, status, _ in smoke._results)


async def test_a_missing_model_provider_alone_is_still_only_a_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control case: nothing was demanded, so nothing failed."""
    exit_code = await run_smoke_cli(monkeypatch, [], FakeTrueForge(models=[]))

    assert exit_code == 0
    assert not any(status == smoke.FAIL for _, status, _ in smoke._results)


async def test_require_sandbox_fails_when_the_live_run_never_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider exists but the backend does not: stage 14 never runs, exit nonzero."""
    exit_code = await run_smoke_cli(
        monkeypatch, ["--require-sandbox"], FakeTrueForge(), backend_reachable=False
    )

    assert exit_code == 1


async def test_model_gate_fails_rather_than_skips_when_sandbox_proof_is_required() -> None:
    fake = FakeTrueForge(models=[])
    client = fake.client()

    available = await smoke.stage_model_available(client, require_sandbox=True)
    await client.aclose()

    _, status, detail = last_result()
    assert available is False
    assert status == smoke.FAIL
    assert "--require-sandbox" in detail


async def test_model_gate_still_skips_when_no_sandbox_proof_was_demanded() -> None:
    fake = FakeTrueForge(models=[])
    client = fake.client()

    available = await smoke.stage_model_available(client, require_sandbox=False)
    await client.aclose()

    _, status, _ = last_result()
    assert available is False
    assert status == smoke.SKIP
