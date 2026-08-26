"""The asynchronous agent-run contract Mission Control depends on.

``POST /api/v1/agent-runs`` must hand back a run id *before* the TrueForge
pipeline finishes, and the pipeline must then advance that same run — never a
copy — through the real lifecycle. Everything here is deterministic: the drives
are stubs, and no model is called.

The properties pinned down are the ones a live UI would silently lose:

*Identity.* One POST, one run, one drive task against that run's id.
*Observability.* A drive that raises leaves a ``FAILED`` run a client can read,
not an exception in a task log and a run frozen mid-pipeline.
*Safety.* Starting a run never commits anything to reality.
"""

import asyncio

import pytest

from app.application.orchestration.agent_run import AgentRunService
from app.application.orchestration.orchestrator import BranchpointOrchestrator
from app.application.orchestration.task_runner import BackgroundTaskRunner
from app.domain.events import RunEventType
from app.domain.runs.lifecycle import RunStatus
from app.infrastructure.demo.adapters import DemoRealityReader, DemoWorldExecutor
from app.infrastructure.demo.engine import DemoProductionEngine
from app.infrastructure.demo.hero import HeroAdversarialTester, HeroCandidatePlanner
from app.infrastructure.persistence.memory import InMemoryEventSink, InMemoryRunRepository
from app.infrastructure.trueforge.sessions import InMemorySessionBindingStore
from tests.factories import make_incident


def build_service(
    *, planner=None, engine: DemoProductionEngine | None = None
) -> tuple[AgentRunService, InMemoryRunRepository, InMemoryEventSink, DemoProductionEngine]:
    """Wire the service with deterministic Phase 2 adapters — no TrueForge, no model."""
    engine = engine or DemoProductionEngine()
    repository = InMemoryRunRepository()
    events = InMemoryEventSink()
    orchestrator = BranchpointOrchestrator(
        repository=repository,
        events=events,
        reality_reader=DemoRealityReader(engine),
        planner=planner if planner is not None else HeroCandidatePlanner(),
        world_executor=DemoWorldExecutor(engine),
        adversarial_tester=HeroAdversarialTester(engine),
    )
    service = AgentRunService(
        orchestrator=orchestrator, events=events, bindings=InMemorySessionBindingStore()
    )
    return service, repository, events, engine


class SlowPlanner:
    """A planner that blocks until released, standing in for a real agent call."""

    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.started = asyncio.Event()
        self._inner = HeroCandidatePlanner()

    async def plan(self, incident, observed_state, *, run_id: str):
        self.started.set()
        await self.release.wait()
        return await self._inner.plan(incident, observed_state, run_id=run_id)


class ExplodingPlanner:
    """A planner that fails the way an unreachable TrueForge would."""

    async def plan(self, incident, observed_state, *, run_id: str):
        raise RuntimeError("TrueForge unreachable")


# ----- 1-3. the id comes back before the pipeline does ------------------------


async def test_the_run_is_readable_before_its_drive_finishes() -> None:
    """The whole point of the async contract: id first, pipeline later."""
    planner = SlowPlanner()
    service, repository, _, _ = build_service(planner=planner)
    runner = BackgroundTaskRunner()

    run = await service.create_run(make_incident())
    runner.start(run.run_id, lambda: service.drive_safely(run.run_id))

    # The caller already has a usable id, and the run is already fetchable.
    assert run.run_id.startswith("run")
    assert run.status is RunStatus.CREATED
    await asyncio.wait_for(planner.started.wait(), timeout=2)
    assert runner.is_running(run.run_id), "the drive should still be in flight"

    stored = await repository.get(run.run_id)
    assert stored is not None
    assert stored.run_id == run.run_id
    assert not stored.is_terminal

    planner.release.set()
    await runner.wait(run.run_id)


# ----- 4. the background drive advances that same run -------------------------


async def test_the_background_drive_advances_the_same_run_through_its_lifecycle() -> None:
    service, repository, events, _ = build_service()
    runner = BackgroundTaskRunner()

    run = await service.create_run(make_incident())
    runner.start(run.run_id, lambda: service.drive_safely(run.run_id))
    await runner.wait(run.run_id)

    driven = await repository.get(run.run_id)
    assert driven is not None
    assert driven.run_id == run.run_id, "the drive must not create a second run"
    assert driven.status is RunStatus.AWAITING_APPROVAL
    assert len(driven.worlds) > 0
    assert driven.comparison is not None

    # Exactly one run exists, and every event belongs to it.
    assert [stored.run_id for stored in await repository.list_runs()] == [run.run_id]
    timeline = await events.events_for(run.run_id)
    assert {event.run_id for event in timeline} == {run.run_id}


async def test_the_timeline_keeps_its_order_through_the_background_drive() -> None:
    service, repository, events, _ = build_service()
    runner = BackgroundTaskRunner()

    run = await service.create_run(make_incident())
    runner.start(run.run_id, lambda: service.drive_safely(run.run_id))
    await runner.wait(run.run_id)

    types = [event.event_type for event in await events.events_for(run.run_id)]
    assert types[0] is RunEventType.RUN_CREATED
    assert types[1] is RunEventType.PLANNER_STARTED
    for earlier, later in (
        (RunEventType.OBSERVATION_COMPLETED, RunEventType.CANDIDATES_PLANNED),
        (RunEventType.CANDIDATES_PLANNED, RunEventType.COMPARISON_COMPLETED),
        (RunEventType.COMPARISON_COMPLETED, RunEventType.APPROVAL_REQUESTED),
    ):
        assert types.index(earlier) < types.index(later), f"{earlier} must precede {later}"


# ----- 5. a background failure is observable ----------------------------------


async def test_a_failing_drive_leaves_a_failed_run_not_a_lost_exception() -> None:
    """A pipeline error must be readable as run state, not buried in a task."""
    service, repository, events, _ = build_service(planner=ExplodingPlanner())
    runner = BackgroundTaskRunner()

    run = await service.create_run(make_incident())
    runner.start(run.run_id, lambda: service.drive_safely(run.run_id))
    await runner.wait(run.run_id)

    failed = await repository.get(run.run_id)
    assert failed is not None
    assert failed.status is RunStatus.FAILED
    assert "TrueForge unreachable" in failed.failure_reason

    types = [event.event_type for event in await events.events_for(run.run_id)]
    assert RunEventType.RUN_FAILED in types
    assert not runner.is_running(run.run_id)


async def test_a_failing_drive_records_exactly_one_failure() -> None:
    """The orchestrator already fails the run; the runner must not fail it twice.

    Failing a terminal run would raise ``IllegalTransitionError`` from inside the
    error handler — turning a recorded outcome into a lost one.
    """
    service, repository, events, _ = build_service(planner=ExplodingPlanner())
    runner = BackgroundTaskRunner()

    run = await service.create_run(make_incident())
    runner.start(run.run_id, lambda: service.drive_safely(run.run_id))
    await runner.wait(run.run_id)

    types = [event.event_type for event in await events.events_for(run.run_id)]
    assert types.count(RunEventType.RUN_FAILED) == 1
    stored = await repository.get(run.run_id)
    assert stored is not None and stored.status is RunStatus.FAILED


async def test_drive_safely_never_lets_an_exception_escape_the_task() -> None:
    service, _, _, _ = build_service(planner=ExplodingPlanner())
    run = await service.create_run(make_incident())

    # No raise: the failure became run state instead.
    await service.drive_safely(run.run_id)


# ----- 6. starting a run never touches reality --------------------------------


async def test_starting_and_driving_a_run_commits_nothing() -> None:
    engine = DemoProductionEngine()
    reality_before = await engine.reality()
    service, repository, _, _ = build_service(engine=engine)
    runner = BackgroundTaskRunner()

    run = await service.create_run(make_incident())
    runner.start(run.run_id, lambda: service.drive_safely(run.run_id))
    await runner.wait(run.run_id)

    driven = await repository.get(run.run_id)
    assert driven is not None
    assert driven.commit_receipt is None
    assert driven.verification is None
    assert driven.status is RunStatus.AWAITING_APPROVAL
    assert await engine.reality() == reality_before


# ----- 7. one drive per run ---------------------------------------------------


async def test_a_run_gets_at_most_one_drive_task() -> None:
    planner = SlowPlanner()
    service, _, _, _ = build_service(planner=planner)
    runner = BackgroundTaskRunner()

    run = await service.create_run(make_incident())
    assert runner.start(run.run_id, lambda: service.drive_safely(run.run_id)) is True
    await asyncio.wait_for(planner.started.wait(), timeout=2)

    # A second start for the same run is refused while the first is in flight.
    assert runner.start(run.run_id, lambda: service.drive_safely(run.run_id)) is False
    assert runner.task_count(run.run_id) == 1

    planner.release.set()
    await runner.wait(run.run_id)


async def test_the_runner_keeps_separate_runs_separate() -> None:
    service, repository, _, _ = build_service()
    runner = BackgroundTaskRunner()

    first = await service.create_run(make_incident("incident_1"))
    second = await service.create_run(make_incident("incident_2"))
    assert first.run_id != second.run_id

    runner.start(first.run_id, lambda: service.drive_safely(first.run_id))
    runner.start(second.run_id, lambda: service.drive_safely(second.run_id))
    await runner.drain()

    for run_id in (first.run_id, second.run_id):
        stored = await repository.get(run_id)
        assert stored is not None and stored.status is RunStatus.AWAITING_APPROVAL


# ----- the runner's own guarantees --------------------------------------------


async def test_the_runner_observes_an_exception_from_its_own_error_handling() -> None:
    """Last-resort net: a handler that itself raises is logged, never unobserved."""
    runner = BackgroundTaskRunner()

    async def broken() -> None:
        raise RuntimeError("handler blew up")

    runner.start("key", broken)
    await runner.wait("key")

    task = runner._tasks["key"]
    assert task.done()
    # Retrieved by the done-callback, so asyncio never reports it as pending.
    assert isinstance(task.exception(), RuntimeError)


async def test_the_runner_can_cancel_in_flight_work() -> None:
    runner = BackgroundTaskRunner()
    started = asyncio.Event()

    async def forever() -> None:
        started.set()
        await asyncio.Event().wait()

    runner.start("key", forever)
    await asyncio.wait_for(started.wait(), timeout=2)
    await runner.cancel_all()

    assert not runner.is_running("key")


async def test_a_finished_key_can_be_started_again() -> None:
    """`start` refuses a *live* duplicate, not a completed one."""
    runner = BackgroundTaskRunner()
    calls = 0

    async def work() -> None:
        nonlocal calls
        calls += 1

    assert runner.start("key", work) is True
    await runner.wait("key")
    assert runner.start("key", work) is True
    await runner.wait("key")
    assert calls == 2


@pytest.mark.parametrize("key", ["run_a", "run_b"])
async def test_waiting_on_an_unknown_key_is_a_no_op(key: str) -> None:
    await BackgroundTaskRunner().wait(key)
