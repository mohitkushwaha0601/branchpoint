"""Human rejection: the operator declines a world BRANCHPOINT found survivable.

This is a *governance* outcome and the tests are written to keep it from being
confused with a safety one. A veto says the action is unsafe and is proved by
machine-verifiable evidence. A rejection says a person chose not to proceed, and
proves nothing about the world at all — its verdict, evidence, and
counterexamples come out the other side untouched.

The invariant that matters most is negative: after a rejection, no sequence of
requests can commit. That is checked against the real capability store and the
real demo engine rather than against the endpoint's own claim.
"""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import (
    get_demo_orchestrator,
    get_event_sink,
    get_run_repository,
)
from app.domain.events import RunEventType
from app.main import app

INCIDENT_BODY = {
    "incident": {
        "title": "Checkout Regression",
        "goal": "Return checkout error rate below 1%",
        "severity": "CRITICAL",
        "affected_services": ["checkout", "pricing-service"],
    }
}
ACTOR = "release-engineer"
REASON = "Rollback risk is unacceptable."


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """A client on the process-wide stores, deliberately not overridden.

    ``build_approval_coordinator`` resolves the run store and event sink itself
    rather than through FastAPI's dependency graph, so an override here would
    give the routes one store and the coordinator another — and a decision would
    be recorded somewhere nothing else could read. Using the real singletons
    keeps every request in this file looking at one run.

    Each test creates its own run, so they do not collide. Demo reality is reset
    on the way out because one test here really does approve and commit.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
        await http.post("/api/v1/demo/reset")


async def run_awaiting_approval(http: AsyncClient) -> str:
    """Drive the deterministic demo pipeline to the human gate."""
    run_id = (await http.post("/api/v1/runs", json=INCIDENT_BODY)).json()["run_id"]
    await http.post(f"/api/v1/runs/{run_id}/execute-demo-worlds")
    run = (await http.get(f"/api/v1/runs/{run_id}")).json()
    assert run["status"] == "AWAITING_APPROVAL", run["status"]
    return run_id


# ----- 1-2. a valid rejection, and what it records ----------------------------


async def test_a_human_can_reject_a_run_awaiting_approval(client: AsyncClient) -> None:
    run_id = await run_awaiting_approval(client)

    response = await client.post(
        f"/api/v1/runs/{run_id}/rejection", json={"actor": ACTOR, "reason": REASON}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["approval_status"] == "REJECTED"
    assert body["run_status"] == "REJECTED"
    assert body["commit_possible"] is False


async def test_the_decision_is_audited_on_the_run(client: AsyncClient) -> None:
    """Who, why, and when — read back from the run, not from the response."""
    run_id = await run_awaiting_approval(client)
    await client.post(f"/api/v1/runs/{run_id}/rejection", json={"actor": ACTOR, "reason": REASON})

    approval = (await client.get(f"/api/v1/runs/{run_id}")).json()["approval"]

    assert approval["status"] == "REJECTED"
    assert approval["actor"] == ACTOR
    assert approval["reason"] == REASON
    assert approval["decided_at"] is not None
    # The binding it was decided against is still stated.
    assert approval["selected_world_id"]
    assert approval["action_fingerprint"]


async def test_a_reason_is_optional(client: AsyncClient) -> None:
    """The domain does not require one, so neither does the endpoint."""
    run_id = await run_awaiting_approval(client)

    response = await client.post(f"/api/v1/runs/{run_id}/rejection", json={"actor": ACTOR})

    assert response.status_code == 200
    assert response.json()["reason"] == ""


# ----- 3-4. no commit, by any route -------------------------------------------


async def test_a_rejected_run_cannot_obtain_a_commit_capability(client: AsyncClient) -> None:
    run_id = await run_awaiting_approval(client)
    await client.post(f"/api/v1/runs/{run_id}/rejection", json={"actor": ACTOR})

    response = await client.post(f"/api/v1/runs/{run_id}/commit-capability")

    assert response.status_code == 409
    assert "REJECTED" in response.json()["detail"]


async def test_approving_after_a_rejection_is_refused(client: AsyncClient) -> None:
    """The commit path is closed at its own gate, not only at the new one."""
    run_id = await run_awaiting_approval(client)
    await client.post(f"/api/v1/runs/{run_id}/rejection", json={"actor": ACTOR})

    response = await client.post(f"/api/v1/runs/{run_id}/approval", json={"actor": ACTOR})

    assert response.status_code == 409
    run = (await client.get(f"/api/v1/runs/{run_id}")).json()
    assert run["status"] == "REJECTED"
    assert run["commit_id"] is None
    assert run["commit_status"] is None
    assert run["verification_status"] is None


# ----- 5. reality is untouched -------------------------------------------------


async def test_rejection_mutates_no_reality(client: AsyncClient) -> None:
    """A refusal is a record, not an action."""
    run_id = await run_awaiting_approval(client)
    before = (await client.get("/api/v1/demo/state")).json()

    await client.post(f"/api/v1/runs/{run_id}/rejection", json={"actor": ACTOR, "reason": REASON})

    after = (await client.get("/api/v1/demo/state")).json()
    assert after["deployment"] == before["deployment"]
    assert after["feature_flag"] == before["feature_flag"]
    assert after["capacity"] == before["capacity"]
    assert after["orders"] == before["orders"]


async def test_rejection_changes_no_world_verdict_or_evidence(client: AsyncClient) -> None:
    """Governance does not rewrite what BRANCHPOINT measured."""
    run_id = await run_awaiting_approval(client)
    before = (await client.get(f"/api/v1/runs/{run_id}/worlds")).json()["worlds"]

    await client.post(f"/api/v1/runs/{run_id}/rejection", json={"actor": ACTOR})

    after = (await client.get(f"/api/v1/runs/{run_id}/worlds")).json()["worlds"]
    assert after == before, "a human decision must not touch world verdicts or evidence"
    # Specifically: a rejected run is not a vetoed world.
    assert [world["veto"] for world in after] == [world["veto"] for world in before]


# ----- 6-8. lifecycle -----------------------------------------------------------


async def test_a_run_that_has_not_reached_the_gate_cannot_be_rejected(
    client: AsyncClient,
) -> None:
    run_id = (await client.post("/api/v1/runs", json=INCIDENT_BODY)).json()["run_id"]

    response = await client.post(f"/api/v1/runs/{run_id}/rejection", json={"actor": ACTOR})

    assert response.status_code == 409
    assert "only a run awaiting approval may be rejected" in response.json()["detail"]


async def test_an_unknown_run_is_not_found(client: AsyncClient) -> None:
    response = await client.post("/api/v1/runs/run_missing/rejection", json={"actor": ACTOR})

    assert response.status_code == 404


async def test_a_granted_approval_cannot_be_rejected_afterwards(
    client: AsyncClient,
) -> None:
    """A decision is made once. Rejection must not overwrite an approval.

    The approval is granted through the domain rather than through
    ``POST /approval``, which would drive the real TrueForge commit operator and
    open a socket. What is under test is the second decision, not the commit.
    """
    run_id = await run_awaiting_approval(client)
    orchestrator = get_demo_orchestrator(get_run_repository(), get_event_sink())
    await orchestrator.decide_approval(run_id, approved=True, actor=ACTOR)

    response = await client.post(f"/api/v1/runs/{run_id}/rejection", json={"actor": "someone"})

    assert response.status_code == 409
    approval = (await client.get(f"/api/v1/runs/{run_id}")).json()["approval"]
    assert approval["status"] == "APPROVED", "the granted decision stands"
    assert approval["actor"] == ACTOR


async def test_repeating_a_rejection_is_idempotent(client: AsyncClient) -> None:
    """Matches approval's own repeat semantics: return the decision, do not redo it."""
    run_id = await run_awaiting_approval(client)
    first = await client.post(
        f"/api/v1/runs/{run_id}/rejection", json={"actor": ACTOR, "reason": REASON}
    )
    second = await client.post(
        f"/api/v1/runs/{run_id}/rejection", json={"actor": "someone-else", "reason": "other"}
    )

    assert first.status_code == second.status_code == 200
    # The first decision is the decision; a repeat does not re-author it.
    assert second.json()["actor"] == ACTOR
    assert second.json()["reason"] == REASON
    assert second.json()["decided_at"] == first.json()["decided_at"]


# ----- 9. events ----------------------------------------------------------------


async def test_rejection_emits_the_human_decision_events(client: AsyncClient) -> None:
    run_id = await run_awaiting_approval(client)
    await client.post(f"/api/v1/runs/{run_id}/rejection", json={"actor": ACTOR, "reason": REASON})

    events = (await client.get(f"/api/v1/runs/{run_id}/events")).json()["events"]
    types = [event["event_type"] for event in events]

    assert types.count(str(RunEventType.APPROVAL_REJECTED)) == 1
    assert types.count(str(RunEventType.RUN_REJECTED)) == 1
    # Never confused with an adversarial veto or a commit.
    assert str(RunEventType.WORLD_VETOED) not in types[types.index("APPROVAL_REQUESTED") :]
    assert str(RunEventType.COMMIT_STARTED) not in types
    assert str(RunEventType.COMMIT_COMPLETED) not in types

    rejection = next(
        event for event in events if event["event_type"] == str(RunEventType.APPROVAL_REJECTED)
    )
    assert ACTOR in rejection["summary"]


async def test_a_repeated_rejection_does_not_emit_a_second_event(
    client: AsyncClient,
) -> None:
    run_id = await run_awaiting_approval(client)
    await client.post(f"/api/v1/runs/{run_id}/rejection", json={"actor": ACTOR})
    await client.post(f"/api/v1/runs/{run_id}/rejection", json={"actor": ACTOR})

    events = (await client.get(f"/api/v1/runs/{run_id}/events")).json()["events"]
    types = [event["event_type"] for event in events]

    assert types.count(str(RunEventType.RUN_REJECTED)) == 1
    assert types.count(str(RunEventType.APPROVAL_REJECTED)) == 1
