"""HTTP contract for the harness trace, and the reconnect story it proves.

Reconnect is the claim that reloading a run page rejoins the *same* TrueForge
sessions rather than starting new work. That is checkable, so it is checked
here: same run id in, same session ids out, and no second drive scheduled.
"""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import (
    get_background_runner,
    get_event_sink,
    get_run_repository,
    get_session_binding_store,
    get_trueforge_client,
)
from app.api.routes import agent_runs as agent_runs_route
from app.api.routes import harness as harness_route
from app.application.orchestration.orchestrator import BranchpointOrchestrator
from app.application.orchestration.task_runner import BackgroundTaskRunner
from app.core.config import Settings
from app.infrastructure.demo.adapters import DemoRealityReader, DemoWorldExecutor
from app.infrastructure.demo.engine import DemoProductionEngine
from app.infrastructure.demo.hero import HeroAdversarialTester, HeroCandidatePlanner
from app.infrastructure.persistence.memory import InMemoryEventSink, InMemoryRunRepository
from app.infrastructure.trueforge.errors import TrueForgeUnavailableError
from app.infrastructure.trueforge.models import TurnEvent
from app.infrastructure.trueforge.sessions import (
    InMemorySessionBindingStore,
    SessionPurpose,
)
from app.main import app
from tests.trueforge.test_harness_trace import (
    SECRET,
    exec_call_event,
    exec_response_event,
    mcp_call_event,
    subagent_call_event,
)

START_BODY = {
    "objective": "Return checkout error rate below the declared recovery SLO.",
    "title": "Checkout Regression",
    "severity": "CRITICAL",
    "affected_services": ["checkout"],
}


class StubTrueForge:
    """Stands in for TrueForge over the wire. Records what was asked of it."""

    def __init__(self, events: dict[str, tuple[TurnEvent, ...]], *, down: bool = False):
        self.events = events
        self.down = down
        self.asked: list[str] = []

    async def list_session_events(self, session_id: str) -> tuple[TurnEvent, ...]:
        self.asked.append(session_id)
        if self.down:
            raise TrueForgeUnavailableError("could not reach TrueForge at localhost:8790")
        return self.events.get(session_id, ())


class Harness:
    def __init__(
        self,
        http: AsyncClient,
        repository: InMemoryRunRepository,
        bindings: InMemorySessionBindingStore,
        runner: BackgroundTaskRunner,
        trueforge: StubTrueForge,
    ) -> None:
        self.http = http
        self.repository = repository
        self.bindings = bindings
        self.runner = runner
        self.trueforge = trueforge


@pytest.fixture
async def harness(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Harness]:
    repository = InMemoryRunRepository()
    events = InMemoryEventSink()
    bindings = InMemorySessionBindingStore()
    runner = BackgroundTaskRunner()
    engine = DemoProductionEngine()
    trueforge = StubTrueForge(
        {
            "sess_alpha": (
                mcp_call_event(),
                subagent_call_event(),
                exec_call_event(),
                exec_response_event(),
            )
        }
    )

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
    monkeypatch.setattr(harness_route, "get_trueforge_client", lambda: trueforge)

    app.dependency_overrides[get_run_repository] = lambda: repository
    app.dependency_overrides[get_event_sink] = lambda: events
    app.dependency_overrides[get_session_binding_store] = lambda: bindings
    app.dependency_overrides[get_background_runner] = lambda: runner
    app.dependency_overrides[get_trueforge_client] = lambda: trueforge

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield Harness(http, repository, bindings, runner, trueforge)
    await runner.cancel_all()
    app.dependency_overrides.clear()


async def start_run(harness: Harness) -> str:
    run_id = (await harness.http.post("/api/v1/agent-runs", json=START_BODY)).json()["run_id"]
    await harness.runner.wait(run_id)
    await harness.bindings.upsert(
        run_id=run_id,
        purpose=SessionPurpose.PLANNER,
        trueforge_session_id="sess_planner",
        last_turn_id="turn_1",
    )
    await harness.bindings.upsert(
        run_id=run_id,
        world_id="world_alpha",
        purpose=SessionPurpose.ADVERSARY,
        trueforge_session_id="sess_alpha",
        last_turn_id="turn_2",
    )
    return run_id


# ----- the endpoint -----------------------------------------------------------


async def test_an_unknown_run_is_not_found(harness: Harness) -> None:
    response = await harness.http.get("/api/v1/runs/run_missing/harness-trace")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


async def test_the_trace_surfaces_real_harness_activity(harness: Harness) -> None:
    run_id = await start_run(harness)

    body = (await harness.http.get(f"/api/v1/runs/{run_id}/harness-trace")).json()

    assert body["trueforge_status"] == "available"
    categories = [entry["category"] for entry in body["entries"]]
    assert "MCP_TOOL" in categories
    assert "SUBAGENT_CREATED" in categories
    assert "SANDBOX_EXEC" in categories
    exec_rows = [e for e in body["entries"] if e["category"] == "SANDBOX_EXEC"]
    assert any(row["exit_code"] == 0 for row in exec_rows)


async def test_the_trace_reads_only_this_runs_bound_sessions(harness: Harness) -> None:
    run_id = await start_run(harness)

    await harness.http.get(f"/api/v1/runs/{run_id}/harness-trace")

    assert sorted(harness.trueforge.asked) == ["sess_alpha", "sess_planner"]


async def test_no_credential_or_payload_appears_in_the_response(harness: Harness) -> None:
    run_id = await start_run(harness)

    raw = (await harness.http.get(f"/api/v1/runs/{run_id}/harness-trace")).text

    assert SECRET not in raw
    assert "python3 -c" not in raw
    # TrueForge's own address is never handed to a browser.
    assert "8790" not in raw


async def test_trueforge_unavailable_still_returns_the_run_and_its_sessions(
    harness: Harness,
) -> None:
    run_id = await start_run(harness)
    harness.trueforge.down = True

    response = await harness.http.get(f"/api/v1/runs/{run_id}/harness-trace")

    assert response.status_code == 200, "a down harness must not break the run page"
    body = response.json()
    assert body["trueforge_status"] == "unavailable"
    assert body["entries"] == []
    assert {s["trueforge_session_id"] for s in body["sessions"]} == {
        "sess_planner",
        "sess_alpha",
    }


# ----- reconnect / session continuity -----------------------------------------


async def test_rereading_a_run_reports_the_same_session_ids(harness: Harness) -> None:
    """The reconnect claim, checked: same run in, same TrueForge sessions out."""
    run_id = await start_run(harness)

    first = (await harness.http.get(f"/api/v1/runs/{run_id}/harness-trace")).json()
    # A reload is just another GET — nothing client-side carries the ids.
    second = (await harness.http.get(f"/api/v1/runs/{run_id}/harness-trace")).json()

    ids = [s["trueforge_session_id"] for s in first["sessions"]]
    assert ids == [s["trueforge_session_id"] for s in second["sessions"]]
    assert ids == ["sess_planner", "sess_alpha"]
    assert [s["purpose"] for s in first["sessions"]] == ["PLANNER", "ADVERSARY"]
    assert [s["last_turn_id"] for s in first["sessions"]] == ["turn_1", "turn_2"]


async def test_rereading_a_run_schedules_no_second_drive(harness: Harness) -> None:
    """Reading is reading: no GET may start agent work."""
    run_id = await start_run(harness)
    assert harness.runner.task_count(run_id) == 1

    for _ in range(3):
        await harness.http.get(f"/api/v1/runs/{run_id}")
        await harness.http.get(f"/api/v1/runs/{run_id}/events")
        await harness.http.get(f"/api/v1/runs/{run_id}/harness-trace")

    assert harness.runner.task_count(run_id) == 1
    assert not harness.runner.is_running(run_id)
    listed = (await harness.http.get("/api/v1/runs")).json()["runs"]
    assert [item["run_id"] for item in listed] == [run_id]


async def test_a_reread_run_keeps_its_state_and_worlds(harness: Harness) -> None:
    run_id = await start_run(harness)

    first = (await harness.http.get(f"/api/v1/runs/{run_id}")).json()
    second = (await harness.http.get(f"/api/v1/runs/{run_id}")).json()

    assert first["status"] == second["status"] == "AWAITING_APPROVAL"
    assert [w["world_id"] for w in first["worlds"]] == [w["world_id"] for w in second["worlds"]]
    assert first["approval"]["action_fingerprint"] == second["approval"]["action_fingerprint"]
