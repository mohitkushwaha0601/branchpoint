"""End-to-end regression cover for :class:`AgentRunService`.

The service is what a real ``POST /agent-runs`` drives, and it is the only
place where the planner session and the world adversary sessions have to agree
on a single run identity. Nothing here calls a model: the real TrueForge client
is served by the fake transport.
"""

import json

from app.application.orchestration.agent_run import AgentRunService
from app.application.orchestration.orchestrator import BranchpointOrchestrator
from app.domain.events import RunEventType
from app.domain.runs.lifecycle import RunStatus
from app.infrastructure.demo.adapters import DemoRealityReader, DemoWorldExecutor
from app.infrastructure.demo.engine import DemoProductionEngine
from app.infrastructure.persistence.memory import InMemoryEventSink, InMemoryRunRepository
from app.infrastructure.trueforge.adversary import TrueForgeAdversarialTester
from app.infrastructure.trueforge.planner import PLANNER_TOOLS, TrueForgeCandidatePlanner
from app.infrastructure.trueforge.sessions import InMemorySessionBindingStore, SessionPurpose
from tests.factories import make_incident
from tests.trueforge.fake_transport import FakeTrueForge, FakeTurn
from tests.trueforge.test_planner import VALID_PLAN

#: An adversary that honestly reports finding nothing replayable. Enough to
#: exercise session binding without dragging counterexample replay in.
NO_FINDING = json.dumps(
    {
        "hypothesis": "Probed compatibility and integrity; found nothing replayable.",
        "investigated": "Ran several sandbox probes.",
        "counterexample": None,
    }
)


def build_service(
    fake: FakeTrueForge,
) -> tuple[AgentRunService, InMemorySessionBindingStore, InMemoryEventSink]:
    """Wire the Phase 3 service exactly as ``build_agent_orchestrator`` does."""
    engine = DemoProductionEngine()
    bindings = InMemorySessionBindingStore()
    events = InMemoryEventSink()
    client = fake.client()

    orchestrator = BranchpointOrchestrator(
        repository=InMemoryRunRepository(),
        events=events,
        reality_reader=DemoRealityReader(engine),
        planner=TrueForgeCandidatePlanner(
            client,
            model="fake/model",
            bindings=bindings,
            read_only_tools=PLANNER_TOOLS,
        ),
        world_executor=DemoWorldExecutor(engine),
        adversarial_tester=TrueForgeAdversarialTester(
            client, engine, model="fake/model", bindings=bindings
        ),
    )
    service = AgentRunService(orchestrator=orchestrator, events=events, bindings=bindings)
    return service, bindings, events


def scripted_run() -> FakeTrueForge:
    """One planner turn followed by one adversarial turn per proposed world."""
    return FakeTrueForge(
        [FakeTurn(output=json.dumps(VALID_PLAN))]
        + [FakeTurn(output=NO_FINDING)] * len(VALID_PLAN["candidates"])
    )


async def test_planner_and_adversary_sessions_bind_to_the_same_run() -> None:
    """Regression: the planner binding must appear under the run the worlds use.

    The smoke test reads exactly this list. Before ``run_id`` came through the
    ``CandidatePlanner`` port, the planner bound to ``incident_id`` instead, so
    this list showed ``planner=0 adversary=3`` for a run that had plainly been
    planned.
    """
    service, bindings, _ = build_service(scripted_run())

    run = await service.drive_to_approval(make_incident())

    bound = await bindings.list_for_run(run.run_id)
    planner_bindings = [b for b in bound if b.purpose is SessionPurpose.PLANNER]
    adversary_bindings = [b for b in bound if b.purpose is SessionPurpose.ADVERSARY]

    assert len(planner_bindings) == 1
    assert len(adversary_bindings) == len(run.worlds) == 3
    assert planner_bindings[0].world_id is None
    assert {b.world_id for b in adversary_bindings} == {w.world_id for w in run.worlds}


async def test_no_binding_is_recorded_against_the_incident_id() -> None:
    """The incident id must never be used as a run id by any session."""
    service, bindings, _ = build_service(scripted_run())
    incident = make_incident()

    run = await service.drive_to_approval(incident)

    assert run.run_id != incident.incident_id
    assert await bindings.list_for_run(incident.incident_id) == []


async def test_service_reaches_the_approval_gate_with_reality_untouched() -> None:
    """The service stops at the human gate; nothing has mutated reality."""
    service, _, _ = build_service(scripted_run())

    run = await service.drive_to_approval(make_incident())

    assert run.status is RunStatus.AWAITING_APPROVAL
    assert run.commit_receipt is None


async def test_session_events_report_the_planner_session() -> None:
    """The run timeline names the planner session, not just the adversaries."""
    service, _, events = build_service(scripted_run())

    run = await service.drive_to_approval(make_incident())

    purposes = [
        event.payload["purpose"]
        for event in await events.events_for(run.run_id)
        if event.event_type is RunEventType.TRUEFORGE_SESSION_CREATED
    ]

    assert str(SessionPurpose.PLANNER) in purposes
    assert purposes.count(str(SessionPurpose.ADVERSARY)) == 3
