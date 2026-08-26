"""Evidence-rich world APIs: can a client reconstruct the veto chain?

The Inspector has to be able to answer "what vetoed this world, and what right
did it have to?" from structured fields alone. So these tests are written from
the client's side: they never read ``verdict_reason``, and they check the two
ways the answer can go wrong —

*Under-claiming.* A world really was vetoed and the linkage is missing.
*Over-claiming.* Something non-authoritative serializes as if it could veto.

The second is the dangerous one, and it is where most of this file goes.
"""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import get_event_sink, get_run_repository
from app.domain.evidence.models import EvidenceKind, EvidenceSeverity
from app.domain.runs.lifecycle import RunStatus
from app.domain.runs.models import BranchpointRun
from app.domain.worlds.models import CounterexampleStatus, World
from app.infrastructure.persistence.memory import InMemoryEventSink, InMemoryRunRepository
from app.main import app
from tests.factories import (
    FIXED_TIME,
    completed_world,
    make_action,
    make_counterexample,
    make_evidence,
    make_incident,
)

RUN_ID = "run_evidence"


@pytest.fixture
async def client() -> AsyncIterator[tuple[AsyncClient, InMemoryRunRepository]]:
    repository = InMemoryRunRepository()
    app.dependency_overrides[get_run_repository] = lambda: repository
    app.dependency_overrides[get_event_sink] = lambda: InMemoryEventSink()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http, repository
    app.dependency_overrides.clear()


async def store_world(
    repository: InMemoryRunRepository,
    *,
    world_id: str = "world_1",
    evidence=(),
    counterexamples=(),
) -> None:
    """Persist one run holding one world driven through its real lifecycle.

    The verdict is **derived** by ``completed_world`` from the same domain rule
    the API reports on, never asserted by the test. That is deliberate: a test
    that set the verdict by hand could pass while the linkage disagreed with it.
    """
    world = completed_world(
        world_id=world_id,
        run_id=RUN_ID,
        attack_evidence=tuple(evidence),
        counterexamples=tuple(counterexamples),
    )
    run = BranchpointRun.create(run_id=RUN_ID, incident=make_incident(), at=FIXED_TIME)
    run = run.transition_to(RunStatus.OBSERVING).with_worlds((world,))
    await repository.save(run)


def failing_replay_evidence(evidence_id: str = "evidence_replay"):
    """What BRANCHPOINT's own replay produces when it reproduces a failure."""
    return make_evidence(
        evidence_id,
        kind=EvidenceKind.DATA_INTEGRITY,
        passed=False,
        machine_verifiable=True,
        severity=EvidenceSeverity.CRITICAL,
        world_id="world_1",
        claim="schema_compatibility: all orders deserialize",
    )


def sandbox_evidence(evidence_id: str = "evidence_sandbox"):
    """What a DOPPELGÄNGER sandbox probe produces. Never authoritative."""
    return make_evidence(
        evidence_id,
        kind=EvidenceKind.COUNTEREXAMPLE,
        passed=None,
        machine_verifiable=False,
        severity=EvidenceSeverity.INFO,
        world_id="world_1",
        claim="adversarial exploration performed in a TrueForge sandbox",
    )


# ----- 1. veto structure ------------------------------------------------------


async def test_a_vetoed_world_links_to_the_counterexample_that_vetoed_it(client) -> None:
    """No string parsing: the veto names its counterexample and its evidence."""
    http, repository = client
    replay = failing_replay_evidence()
    await store_world(
        repository,
        evidence=(sandbox_evidence(), replay),
        counterexamples=(
            make_counterexample(
                "attack_1",
                "world_1",
                status=CounterexampleStatus.REPRODUCED,
                evidence_ids=("evidence_sandbox", "evidence_replay"),
            ),
        ),
    )

    world = (await http.get(f"/api/v1/runs/{RUN_ID}/worlds")).json()["worlds"][0]

    assert world["verdict"] == "VETOED"
    assert world["veto"] == {
        "basis": "REPRODUCED_COUNTEREXAMPLE",
        "counterexample_id": "attack_1",
        "evidence_ids": ["evidence_replay"],
        "authoritative": True,
        "summary": "Migration replay regression",
    }
    # The sandbox evidence the attack also cited is not part of the justification.
    assert "evidence_sandbox" not in world["veto"]["evidence_ids"]


async def test_a_veto_from_standalone_failing_evidence_says_so(client) -> None:
    """The other authoritative path: no counterexample, just a failed check."""
    http, repository = client
    await store_world(
        repository,
        evidence=(failing_replay_evidence(),),
        counterexamples=(),
    )

    world = (await http.get(f"/api/v1/runs/{RUN_ID}/worlds")).json()["worlds"][0]

    assert world["veto"]["basis"] == "MACHINE_VERIFIABLE_FAILURE"
    assert world["veto"]["counterexample_id"] is None
    assert world["veto"]["evidence_ids"] == ["evidence_replay"]
    assert world["veto"]["authoritative"] is True


# ----- 2. reproduction is distinguishable from proposal -----------------------


@pytest.mark.parametrize(
    ("status", "reproduced"),
    [
        (CounterexampleStatus.PROPOSED, False),
        (CounterexampleStatus.NOT_REPRODUCED, False),
        (CounterexampleStatus.ERROR, False),
        (CounterexampleStatus.REPRODUCED, True),
    ],
)
async def test_reproduction_state_is_exposed_verbatim(client, status, reproduced) -> None:
    http, repository = client
    await store_world(
        repository,
        evidence=(failing_replay_evidence(),),
        counterexamples=(
            make_counterexample(
                "attack_1", "world_1", status=status, evidence_ids=("evidence_replay",)
            ),
        ),
    )

    body = (await http.get(f"/api/v1/runs/{RUN_ID}/worlds/world_1")).json()

    counterexample = body["counterexamples"][0]
    assert counterexample["status"] == str(status)
    assert counterexample["reproduced"] is reproduced


# ----- 3. authority ----------------------------------------------------------


async def test_a_claimed_reproduction_without_evidence_is_not_authoritative(client) -> None:
    """The load-bearing case: an adversary cannot veto by asserting a reproduction.

    The attack says REPRODUCED and cites only its own sandbox output. It
    serializes as reproduced — that is what it claimed — and as *not*
    authoritative, and the world carries no veto.
    """
    http, repository = client
    await store_world(
        repository,
        evidence=(sandbox_evidence(),),
        counterexamples=(
            make_counterexample(
                "attack_1",
                "world_1",
                status=CounterexampleStatus.REPRODUCED,
                evidence_ids=("evidence_sandbox",),
            ),
        ),
    )

    body = (await http.get(f"/api/v1/runs/{RUN_ID}/worlds/world_1")).json()

    counterexample = body["counterexamples"][0]
    assert counterexample["reproduced"] is True
    assert counterexample["authoritative"] is False
    assert counterexample["supporting_evidence_ids"] == []
    assert body["world"]["veto"] is None
    assert body["world"]["reproduced_counterexamples"] == 1
    assert body["world"]["authoritative_counterexamples"] == 0


async def test_a_reproduction_backed_by_replay_is_authoritative(client) -> None:
    http, repository = client
    await store_world(
        repository,
        evidence=(failing_replay_evidence(),),
        counterexamples=(
            make_counterexample(
                "attack_1",
                "world_1",
                status=CounterexampleStatus.REPRODUCED,
                evidence_ids=("evidence_replay",),
            ),
        ),
    )

    body = (await http.get(f"/api/v1/runs/{RUN_ID}/worlds/world_1")).json()

    counterexample = body["counterexamples"][0]
    assert counterexample["authoritative"] is True
    assert counterexample["supporting_evidence_ids"] == ["evidence_replay"]
    assert body["world"]["authoritative_counterexamples"] == 1


async def test_passing_machine_verifiable_evidence_disqualifies_nothing(client) -> None:
    """Authority is not "machine-verifiable"; it is machine-verifiable *and failing*."""
    http, repository = client
    passing = make_evidence(
        "evidence_pass", passed=True, machine_verifiable=True, world_id="world_1"
    )
    await store_world(
        repository,
        evidence=(passing,),
        counterexamples=(
            make_counterexample(
                "attack_1",
                "world_1",
                status=CounterexampleStatus.REPRODUCED,
                evidence_ids=("evidence_pass",),
            ),
        ),
    )

    body = (await http.get(f"/api/v1/runs/{RUN_ID}/worlds/world_1")).json()

    recorded = next(item for item in body["evidence"] if item["evidence_id"] == "evidence_pass")
    assert recorded["machine_verifiable"] is True
    assert recorded["disqualifying"] is False
    assert body["counterexamples"][0]["authoritative"] is False
    assert body["world"]["veto"] is None


# ----- 4. the TrueForge / sandbox boundary ------------------------------------


async def test_sandbox_evidence_never_serializes_as_authoritative(client) -> None:
    """A harness or sandbox record is provenance, and the payload says so."""
    http, repository = client
    await store_world(
        repository,
        evidence=(sandbox_evidence(),),
        counterexamples=(),
    )

    body = (await http.get(f"/api/v1/runs/{RUN_ID}/worlds/world_1")).json()
    evidence = next(item for item in body["evidence"] if item["evidence_id"] == "evidence_sandbox")

    assert evidence["machine_verifiable"] is False
    assert evidence["disqualifying"] is False
    assert evidence["passed"] is None


async def test_authority_is_readable_without_looking_at_the_source(client) -> None:
    """A client that trusted `source` would get this backwards, so it must not need to.

    Both records here are failing. Only one is machine-verifiable, and that — not
    the name of whatever produced it — is what the payload keys authority on.
    """
    http, repository = client
    loud_sandbox = make_evidence(
        "evidence_sandbox",
        passed=False,
        machine_verifiable=False,
        severity=EvidenceSeverity.CRITICAL,
        world_id="world_1",
        claim="sandbox script observed the invariant break",
    )
    await store_world(
        repository,
        evidence=(loud_sandbox, failing_replay_evidence()),
        counterexamples=(),
    )

    body = (await http.get(f"/api/v1/runs/{RUN_ID}/worlds/world_1")).json()

    by_id = {item["evidence_id"]: item for item in body["evidence"]}
    assert by_id["evidence_sandbox"]["passed"] is False
    assert by_id["evidence_sandbox"]["disqualifying"] is False
    assert by_id["evidence_replay"]["disqualifying"] is True
    # Only the replay record is cited by the veto.
    assert body["world"]["veto"]["evidence_ids"] == ["evidence_replay"]


# ----- 5. a surviving world claims no veto ------------------------------------


async def test_a_surviving_world_exposes_no_veto(client) -> None:
    http, repository = client
    await store_world(
        repository,
        evidence=(make_evidence("evidence_ok", passed=True, world_id="world_1"),),
        counterexamples=(
            make_counterexample("attack_1", "world_1", status=CounterexampleStatus.NOT_REPRODUCED),
        ),
    )

    body = (await http.get(f"/api/v1/runs/{RUN_ID}/worlds/world_1")).json()

    assert body["world"]["verdict"] == "SURVIVED"
    assert body["world"]["veto"] is None
    assert body["world"]["authoritative_counterexamples"] == 0
    assert body["counterexamples"][0]["authoritative"] is False


# ----- 6. unknown resources ---------------------------------------------------


async def test_an_unknown_run_is_not_found(client) -> None:
    http, _ = client

    response = await http.get("/api/v1/runs/run_missing/worlds/world_1")

    assert response.status_code == 404
    assert response.json()["detail"] == "run run_missing not found"


async def test_an_unknown_world_in_a_real_run_is_not_found(client) -> None:
    http, repository = client
    await store_world(
        repository,
        evidence=(),
        counterexamples=(),
    )

    response = await http.get(f"/api/v1/runs/{RUN_ID}/worlds/world_missing")

    assert response.status_code == 404
    assert "world_missing" in response.json()["detail"]


# ----- 7. determinism ---------------------------------------------------------


async def test_repeated_reads_serialize_identically(client) -> None:
    http, repository = client
    await store_world(
        repository,
        evidence=(
            sandbox_evidence(),
            failing_replay_evidence(),
            make_evidence("evidence_third", passed=True, world_id="world_1"),
        ),
        counterexamples=(
            make_counterexample(
                "attack_1",
                "world_1",
                status=CounterexampleStatus.REPRODUCED,
                evidence_ids=("evidence_replay",),
            ),
        ),
    )

    first = (await http.get(f"/api/v1/runs/{RUN_ID}/worlds/world_1")).text
    second = (await http.get(f"/api/v1/runs/{RUN_ID}/worlds/world_1")).text

    assert first == second
    # Evidence keeps the domain's arrival order rather than being re-sorted.
    ids = [
        item["evidence_id"]
        for item in (await http.get(f"/api/v1/runs/{RUN_ID}/worlds/world_1")).json()["evidence"]
    ]
    # Execution evidence first, then attack evidence in the order it arrived.
    assert ids[-3:] == ["evidence_sandbox", "evidence_replay", "evidence_third"]


# ----- 8. the existing contract still holds ------------------------------------


async def test_the_world_list_keeps_the_fields_it_already_had(client) -> None:
    """New fields are additive: nothing a current client reads has moved."""
    http, repository = client
    await store_world(
        repository,
        evidence=(failing_replay_evidence(),),
        counterexamples=(
            make_counterexample(
                "attack_1",
                "world_1",
                status=CounterexampleStatus.REPRODUCED,
                evidence_ids=("evidence_replay",),
            ),
        ),
    )

    world = (await http.get(f"/api/v1/runs/{RUN_ID}/worlds")).json()["worlds"][0]

    for field in (
        "world_id",
        "status",
        "verdict",
        "verdict_reason",
        "action_id",
        "action_name",
        "action_type",
        "goal_achieved",
        "goal_attainment",
        "regressions_detected",
        "blast_radius",
        "cost_delta",
        "evidence_count",
        "counterexample_count",
        "reproduced_counterexamples",
    ):
        assert field in world, field
    assert world["verdict_reason"], "the human-readable summary is still there"


# ----- action and outcome detail ----------------------------------------------
#
# The list endpoint only ever carried an action's id, name, and type, so a client
# could not say what the action would actually change. These pin the stored
# values through, and pin the absent ones absent.


async def test_the_action_is_serialized_from_stored_domain_values(client) -> None:
    http, repository = client
    await store_world(repository, evidence=(failing_replay_evidence(),))

    action = (await http.get(f"/api/v1/runs/{RUN_ID}/worlds/world_1")).json()["action"]

    assert action["action_id"] == "action_1"
    assert action["name"] == "Disable pricing v2 flag"
    assert action["action_type"] == "FEATURE_FLAG_DISABLE"
    assert action["target_service"] == "pricing-service"
    assert action["target_environment"] == "production"
    assert action["reversible"] is True
    assert action["risk_class"] == "LOW"
    assert action["source_kind"] == "PLANNER"
    # A content hash of the action, the same one an approval binds to.
    assert len(action["action_fingerprint"]) == 64


async def test_action_parameters_are_passed_through_verbatim(client) -> None:
    """The one field that says what would change. Never reconstructed."""
    http, repository = client
    world = completed_world(
        world_id="world_1",
        run_id=RUN_ID,
        action=make_action("action_1", parameters={"version": "v2.40"}),
        attack_evidence=(failing_replay_evidence(),),
    )
    run = BranchpointRun.create(run_id=RUN_ID, incident=make_incident(), at=FIXED_TIME)
    await repository.save(run.transition_to(RunStatus.OBSERVING).with_worlds((world,)))

    action = (await http.get(f"/api/v1/runs/{RUN_ID}/worlds/world_1")).json()["action"]

    assert action["parameters"] == {"version": "v2.40"}


async def test_the_outcome_is_serialized_from_stored_measurements(client) -> None:
    http, repository = client
    await store_world(repository, evidence=(failing_replay_evidence(),))

    outcome = (await http.get(f"/api/v1/runs/{RUN_ID}/worlds/world_1")).json()["outcome"]

    assert outcome["succeeded"] is True
    assert outcome["goal_achieved"] is True
    assert outcome["goal_attainment"] == 1.0
    assert outcome["invariants_preserved"] is True
    assert outcome["blast_radius"] == 1
    assert outcome["cost_delta"] == 0.0
    assert outcome["summary"] == "counterfactual execution completed"


async def test_a_world_that_has_not_executed_has_no_outcome(client) -> None:
    """Null, not a zeroed stand-in that would read as "measured, all zero"."""
    http, repository = client
    world = World.create(
        world_id="world_1", run_id=RUN_ID, candidate_action=make_action(), at=FIXED_TIME
    )
    run = BranchpointRun.create(run_id=RUN_ID, incident=make_incident(), at=FIXED_TIME)
    await repository.save(run.transition_to(RunStatus.OBSERVING).with_worlds((world,)))

    body = (await http.get(f"/api/v1/runs/{RUN_ID}/worlds/world_1")).json()

    assert body["outcome"] is None
    assert body["action"]["action_id"] == "action_1"


async def test_no_capability_or_credential_material_is_serialized(client) -> None:
    http, repository = client
    await store_world(
        repository,
        evidence=(sandbox_evidence(), failing_replay_evidence()),
        counterexamples=(
            make_counterexample(
                "attack_1",
                "world_1",
                status=CounterexampleStatus.REPRODUCED,
                evidence_ids=("evidence_replay",),
            ),
        ),
    )

    raw = (await http.get(f"/api/v1/runs/{RUN_ID}/worlds/world_1")).text.lower()

    for forbidden in ("capability", "cap_", "token", "secret", "api_key", "authorization"):
        assert forbidden not in raw, forbidden


# ----- the narrower sub-resources ---------------------------------------------


async def test_the_evidence_route_returns_the_same_records(client) -> None:
    http, repository = client
    await store_world(repository, evidence=(sandbox_evidence(), failing_replay_evidence()))

    full = (await http.get(f"/api/v1/runs/{RUN_ID}/worlds/world_1")).json()
    only = (await http.get(f"/api/v1/runs/{RUN_ID}/worlds/world_1/evidence")).json()

    assert only["world_id"] == "world_1"
    assert only["evidence"] == full["evidence"], "the narrower route must not disagree"


async def test_the_counterexample_route_agrees_about_authority(client) -> None:
    """A narrower fetch must not reach a different conclusion about an attack."""
    http, repository = client
    await store_world(
        repository,
        evidence=(sandbox_evidence(),),
        counterexamples=(
            make_counterexample(
                "attack_1",
                "world_1",
                status=CounterexampleStatus.REPRODUCED,
                evidence_ids=("evidence_sandbox",),
            ),
        ),
    )

    full = (await http.get(f"/api/v1/runs/{RUN_ID}/worlds/world_1")).json()
    only = (await http.get(f"/api/v1/runs/{RUN_ID}/worlds/world_1/counterexamples")).json()

    assert only["counterexamples"] == full["counterexamples"]
    # Claimed reproduced, unsupported, therefore not authoritative — on both routes.
    assert only["counterexamples"][0]["reproduced"] is True
    assert only["counterexamples"][0]["authoritative"] is False


@pytest.mark.parametrize("suffix", ["", "/evidence", "/counterexamples"])
async def test_every_world_route_404s_the_same_way(client, suffix: str) -> None:
    http, repository = client
    await store_world(repository)

    unknown_run = await http.get(f"/api/v1/runs/run_missing/worlds/world_1{suffix}")
    unknown_world = await http.get(f"/api/v1/runs/{RUN_ID}/worlds/world_missing{suffix}")

    assert unknown_run.status_code == 404
    assert unknown_run.json()["detail"] == "run run_missing not found"
    assert unknown_world.status_code == 404
    assert "world_missing" in unknown_world.json()["detail"]
