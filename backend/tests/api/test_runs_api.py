"""HTTP contract for run inspection."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import get_event_sink, get_run_repository
from app.infrastructure.persistence.memory import InMemoryEventSink, InMemoryRunRepository
from app.main import app

INCIDENT_BODY = {
    "incident": {
        "title": "Checkout error rate at 41%",
        "goal": "Return checkout error rate below 1%",
        "severity": "CRITICAL",
        "affected_services": ["checkout", "pricing-service"],
    }
}


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Yield a client backed by a fresh in-memory store per test."""
    repository = InMemoryRunRepository()
    events = InMemoryEventSink()
    app.dependency_overrides[get_run_repository] = lambda: repository
    app.dependency_overrides[get_event_sink] = lambda: events
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


async def test_create_run_returns_a_created_run(client: AsyncClient) -> None:
    response = await client.post("/api/v1/runs", json=INCIDENT_BODY)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "CREATED"
    assert body["run_id"].startswith("run_")
    assert body["incident"]["title"] == "Checkout error rate at 41%"
    assert body["worlds"] == []
    assert body["approval"] is None
    assert body["comparison"] is None


async def test_created_run_can_be_read_back(client: AsyncClient) -> None:
    run_id = (await client.post("/api/v1/runs", json=INCIDENT_BODY)).json()["run_id"]

    response = await client.get(f"/api/v1/runs/{run_id}")

    assert response.status_code == 200
    assert response.json()["run_id"] == run_id


async def test_runs_are_listed_newest_first(client: AsyncClient) -> None:
    first = (await client.post("/api/v1/runs", json=INCIDENT_BODY)).json()["run_id"]
    second = (await client.post("/api/v1/runs", json=INCIDENT_BODY)).json()["run_id"]

    response = await client.get("/api/v1/runs")

    assert response.status_code == 200
    listed = [run["run_id"] for run in response.json()["runs"]]
    assert set(listed) == {first, second}


async def test_run_timeline_starts_with_run_created(client: AsyncClient) -> None:
    run_id = (await client.post("/api/v1/runs", json=INCIDENT_BODY)).json()["run_id"]

    response = await client.get(f"/api/v1/runs/{run_id}/events")

    assert response.status_code == 200
    events = response.json()["events"]
    assert [event["event_type"] for event in events] == ["RUN_CREATED"]
    assert events[0]["run_id"] == run_id


async def test_unknown_run_returns_404(client: AsyncClient) -> None:
    response = await client.get("/api/v1/runs/run_missing")

    assert response.status_code == 404


async def test_unknown_run_timeline_returns_404(client: AsyncClient) -> None:
    response = await client.get("/api/v1/runs/run_missing/events")

    assert response.status_code == 404


async def test_invalid_incident_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/v1/runs", json={"incident": {"title": ""}})

    assert response.status_code == 422


async def test_openapi_documents_the_run_endpoints(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    assert {"/health", "/api/v1/runs", "/api/v1/runs/{run_id}"} <= set(response.json()["paths"])
