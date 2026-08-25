"""HTTP contract for the demo production endpoints."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import get_event_sink, get_run_repository
from app.core.config import Settings, get_settings
from app.infrastructure.demo.capability import CapabilityStore
from app.infrastructure.demo.dependencies import get_capability_store, get_demo_engine
from app.infrastructure.demo.engine import DemoProductionEngine
from app.infrastructure.persistence.memory import InMemoryEventSink, InMemoryRunRepository
from app.main import app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Yield a client backed by a fresh in-memory store and demo engine per test."""
    repository = InMemoryRunRepository()
    events = InMemoryEventSink()
    engine = DemoProductionEngine()
    capability_store = CapabilityStore()
    app.dependency_overrides[get_run_repository] = lambda: repository
    app.dependency_overrides[get_event_sink] = lambda: events
    app.dependency_overrides[get_demo_engine] = lambda: engine
    app.dependency_overrides[get_capability_store] = lambda: capability_store
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


async def test_get_demo_state_returns_the_initial_incident(client: AsyncClient) -> None:
    response = await client.get("/api/v1/demo/state")

    assert response.status_code == 200
    body = response.json()
    assert body["deployment"]["version"] == "v2.41"
    assert body["metrics"]["checkout_error_rate"] == pytest.approx(0.413)
    assert "token" not in str(body).lower()


async def test_post_demo_reset_works_in_development(client: AsyncClient) -> None:
    create = await client.post(
        "/api/v1/runs", json={"incident": {"title": "t", "goal": "g", "severity": "CRITICAL"}}
    )
    run_id = create.json()["run_id"]
    await client.post(f"/api/v1/runs/{run_id}/execute-demo-worlds")

    changed = await client.get("/api/v1/demo/state")
    assert changed.status_code == 200

    reset = await client.post("/api/v1/demo/reset")

    assert reset.status_code == 200
    assert reset.json()["deployment"]["version"] == "v2.41"
    assert reset.json()["feature_flag"]["enabled"] is True


async def test_demo_reset_is_unavailable_in_production(client: AsyncClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(env="production")
    try:
        response = await client.post("/api/v1/demo/reset")
    finally:
        del app.dependency_overrides[get_settings]

    assert response.status_code == 404


async def test_execute_demo_worlds_drives_the_run_to_awaiting_approval(client: AsyncClient) -> None:
    create = await client.post(
        "/api/v1/runs", json={"incident": {"title": "t", "goal": "g", "severity": "CRITICAL"}}
    )
    run_id = create.json()["run_id"]

    response = await client.post(f"/api/v1/runs/{run_id}/execute-demo-worlds")

    assert response.status_code == 200
    assert response.json()["status"] == "AWAITING_APPROVAL"

    run = (await client.get(f"/api/v1/runs/{run_id}")).json()
    verdicts = {w["action_name"]: w["verdict"] for w in run["worlds"]}
    assert verdicts["Roll back pricing-service to v2.40"] == "VETOED"
    assert verdicts["Disable PRICING_V2 feature flag"] == "SURVIVED"


async def test_execute_demo_worlds_rejects_an_unknown_run(client: AsyncClient) -> None:
    response = await client.post("/api/v1/runs/run_missing/execute-demo-worlds")

    assert response.status_code == 404


async def test_commit_capability_requires_an_approved_run(client: AsyncClient) -> None:
    create = await client.post(
        "/api/v1/runs", json={"incident": {"title": "t", "goal": "g", "severity": "CRITICAL"}}
    )
    run_id = create.json()["run_id"]

    response = await client.post(f"/api/v1/runs/{run_id}/commit-capability")

    assert response.status_code == 409
