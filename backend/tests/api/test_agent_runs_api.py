"""HTTP contract for starting an agent run asynchronously.

Exercises the real route through ASGI. The TrueForge-backed orchestrator is
swapped for the deterministic Phase 2 adapters, so nothing here calls a model or
opens a socket — but the endpoint, the background runner, and the run store are
all the production ones.
"""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import dependencies
from app.api.dependencies import (
    get_background_runner,
    get_event_sink,
    get_run_repository,
)
from app.api.routes import agent_runs as agent_runs_route
from app.application.orchestration.orchestrator import BranchpointOrchestrator
from app.application.orchestration.task_runner import BackgroundTaskRunner
from app.core.config import Settings
from app.infrastructure.demo.adapters import DemoRealityReader, DemoWorldExecutor
from app.infrastructure.demo.engine import DemoProductionEngine
from app.infrastructure.demo.hero import HeroAdversarialTester, HeroCandidatePlanner
from app.infrastructure.persistence.memory import InMemoryEventSink, InMemoryRunRepository
from app.main import app

START_BODY = {
    "objective": "Return checkout error rate below the declared recovery SLO.",
    "title": "Checkout Regression",
    "severity": "CRITICAL",
    "affected_services": ["checkout", "pricing-service"],
}


class Harness:
    """The isolated stores and runner one test's requests share."""

    def __init__(
        self,
        http: AsyncClient,
        repository: InMemoryRunRepository,
        events: InMemoryEventSink,
        runner: BackgroundTaskRunner,
        engine: DemoProductionEngine,
    ) -> None:
        self.http = http
        self.repository = repository
        self.events = events
        self.runner = runner
        self.engine = engine


@pytest.fixture
async def harness(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Harness]:
    repository = InMemoryRunRepository()
    events = InMemoryEventSink()
    runner = BackgroundTaskRunner()
    engine = DemoProductionEngine()

    # A model must resolve for the endpoint to accept the run; the name is never
    # used because the orchestrator below has no TrueForge adapter in it.
    settings = Settings(_env_file=None, model="fake/model")
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    monkeypatch.setattr(agent_runs_route, "get_settings", lambda: settings)
    monkeypatch.setattr(
        agent_runs_route,
        "build_agent_orchestrator",
        lambda: BranchpointOrchestrator(
            repository=repository,
            events=events,
            reality_reader=DemoRealityReader(engine),
            planner=HeroCandidatePlanner(),
            world_executor=DemoWorldExecutor(engine),
            adversarial_tester=HeroAdversarialTester(engine),
        ),
    )

    app.dependency_overrides[get_run_repository] = lambda: repository
    app.dependency_overrides[get_event_sink] = lambda: events
    app.dependency_overrides[get_background_runner] = lambda: runner
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield Harness(http, repository, events, runner, engine)
    await runner.cancel_all()
    app.dependency_overrides.clear()


async def test_start_returns_202_with_the_run_id_immediately(harness: Harness) -> None:
    response = await harness.http.post("/api/v1/agent-runs", json=START_BODY)

    assert response.status_code == 202
    body = response.json()
    assert body["run_id"].startswith("run_")
    assert body["status"] == "CREATED"
    assert body["detail"] == "run accepted"


async def test_the_returned_run_is_immediately_readable(harness: Harness) -> None:
    run_id = (await harness.http.post("/api/v1/agent-runs", json=START_BODY)).json()["run_id"]

    fetched = await harness.http.get(f"/api/v1/runs/{run_id}")

    assert fetched.status_code == 200
    assert fetched.json()["run_id"] == run_id
    assert fetched.json()["incident"]["title"] == "Checkout Regression"


async def test_the_background_drive_advances_that_same_run(harness: Harness) -> None:
    run_id = (await harness.http.post("/api/v1/agent-runs", json=START_BODY)).json()["run_id"]

    await harness.runner.wait(run_id)

    run = (await harness.http.get(f"/api/v1/runs/{run_id}")).json()
    assert run["run_id"] == run_id
    assert run["status"] == "AWAITING_APPROVAL"
    assert len(run["worlds"]) > 0
    assert run["comparison"]["recommended_world_id"] is not None
    assert run["approval"]["status"] == "PENDING"

    listed = (await harness.http.get("/api/v1/runs")).json()["runs"]
    assert [item["run_id"] for item in listed] == [run_id], "one POST must create one run"


async def test_the_event_timeline_is_readable_over_http(harness: Harness) -> None:
    run_id = (await harness.http.post("/api/v1/agent-runs", json=START_BODY)).json()["run_id"]
    await harness.runner.wait(run_id)

    events = (await harness.http.get(f"/api/v1/runs/{run_id}/events")).json()["events"]

    assert [event["event_type"] for event in events][0] == "RUN_CREATED"
    assert {event["run_id"] for event in events} == {run_id}
    assert any(event["event_type"] == "APPROVAL_REQUESTED" for event in events)


async def test_starting_a_run_commits_nothing_to_reality(harness: Harness) -> None:
    before = (await harness.http.get("/api/v1/demo/state")).json()

    run_id = (await harness.http.post("/api/v1/agent-runs", json=START_BODY)).json()["run_id"]
    await harness.runner.wait(run_id)

    run = (await harness.http.get(f"/api/v1/runs/{run_id}")).json()
    assert run["commit_id"] is None
    assert run["commit_status"] is None
    assert run["verification_status"] is None

    after = (await harness.http.get("/api/v1/demo/state")).json()
    assert after["feature_flag"] == before["feature_flag"]
    assert after["deployment"]["version"] == before["deployment"]["version"]


async def test_each_post_creates_its_own_run_and_its_own_drive(harness: Harness) -> None:
    first = (await harness.http.post("/api/v1/agent-runs", json=START_BODY)).json()["run_id"]
    second = (await harness.http.post("/api/v1/agent-runs", json=START_BODY)).json()["run_id"]

    assert first != second
    assert harness.runner.task_count(first) == 1
    assert harness.runner.task_count(second) == 1

    await harness.runner.drain()
    listed = {item["run_id"] for item in (await harness.http.get("/api/v1/runs")).json()["runs"]}
    assert listed == {first, second}


async def test_an_unconfigured_model_is_refused_before_a_run_is_created(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A half-configured run would exist only to fail on its first agent call."""
    unconfigured = Settings(_env_file=None, model="", trueforge_model="")
    monkeypatch.setattr(agent_runs_route, "get_settings", lambda: unconfigured)

    response = await harness.http.post("/api/v1/agent-runs", json=START_BODY)

    assert response.status_code == 503
    assert "no model configured" in response.json()["detail"]
    assert (await harness.http.get("/api/v1/runs")).json()["runs"] == []


async def test_a_failing_drive_surfaces_as_a_failed_run_over_http(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The client must be able to read the failure, not watch a frozen run."""

    class ExplodingPlanner:
        async def plan(self, incident, observed_state, *, run_id: str):
            raise RuntimeError("TrueForge unreachable")

    monkeypatch.setattr(
        agent_runs_route,
        "build_agent_orchestrator",
        lambda: BranchpointOrchestrator(
            repository=harness.repository,
            events=harness.events,
            reality_reader=DemoRealityReader(harness.engine),
            planner=ExplodingPlanner(),
            world_executor=DemoWorldExecutor(harness.engine),
            adversarial_tester=HeroAdversarialTester(harness.engine),
        ),
    )

    response = await harness.http.post("/api/v1/agent-runs", json=START_BODY)
    assert response.status_code == 202, "acceptance does not depend on the drive succeeding"
    run_id = response.json()["run_id"]
    await harness.runner.wait(run_id)

    run = (await harness.http.get(f"/api/v1/runs/{run_id}")).json()
    assert run["status"] == "FAILED"
    assert "TrueForge unreachable" in run["failure_reason"]

    events = (await harness.http.get(f"/api/v1/runs/{run_id}/events")).json()["events"]
    assert [event["event_type"] for event in events].count("RUN_FAILED") == 1


def test_the_module_still_wires_one_process_wide_runner() -> None:
    """The runner is a singleton for the same reason the run store is."""
    assert dependencies.get_background_runner() is dependencies.get_background_runner()
