# BRANCHPOINT Backend

BRANCHPOINT is a counterfactual execution and adversarial verification layer for autonomous agents. Candidate actions are tested in isolated worlds, attacked by DOPPELGÄNGER agents, compared using executable evidence, and only then eligible for human-approved execution against reality.

> **No consequential action reaches reality until it survives an adversarial counterfactual and receives explicit approval.**

Agents get branches before they get permissions.

## Core lifecycle

```text
Observe → Plan → Fork → Execute → Attack → Compare → Approve → Commit → Verify
```

| Step | What happens |
| --- | --- |
| Observe | Structured observations of reality are read into the run — metrics, deployments, feature flags, service health, invariants. |
| Plan | Candidate actions are proposed. A candidate is inert: it describes what *would* be done and never executes anything. |
| Fork | One counterfactual world is created per candidate action. |
| Execute | Each world runs its candidate action counterfactually and measures the result. |
| Attack | A DOPPELGÄNGER attacks each world and tries to produce a reproducible counterexample. |
| Compare | Surviving worlds are ranked by explicit deterministic rules — never by a model score. |
| Approve | A human explicitly approves exactly one surviving world. |
| Commit | Exactly one action is applied to reality, against an immutable receipt. |
| Verify | Reality is independently re-checked. A successful commit is not success. |

## MANYWORLDS

Rather than reasoning about one action and taking it, BRANCHPOINT forks a world per candidate action and executes all of them counterfactually. Each world belongs to exactly one run and tests exactly one candidate action, so worlds can be compared on what actually happened in them rather than on what a model predicted would happen.

## DOPPELGÄNGER

A DOPPELGÄNGER is an adversarial agent whose job is to invalidate a candidate. It does not review the candidate; it attacks it and tries to produce a counterexample that reproduces.

## Evidence > confidence

A DOPPELGÄNGER cannot veto a world by saying it looks unsafe. A veto requires a counterexample that is **reproduced** *and* references **machine-verifiable failing evidence** — a failing test, a violated invariant, a reproducible counterexample, a deterministic policy violation, or a measured regression.

Two consequences are enforced in the domain:

- An unsupported claim of reproduction is recorded and ignored, never raised as an error. An untrusted adversary cannot halt a run by asserting things.
- A world with no machine-verifiable evidence at all is `INCONCLUSIVE`, not `SURVIVED`. Absence of evidence never becomes evidence of safety.

There is no aggregate "safety score" anywhere in the system.

## Architecture

```text
app/
  api/             HTTP boundary only — request/response schemas, routing, DI wiring
  application/     deterministic use cases, ports, orchestration, world comparison
  domain/          pure business concepts and invariants — no framework imports
  infrastructure/  adapters for external systems (in-memory only in Phase 1)
```

The domain layer imports no framework, transport, database, sandbox, or model SDK. Domain objects are frozen Pydantic models: every state change returns a revalidated copy rather than mutating in place.

Everything the system does not own arrives through a port in `app/application/ports.py`:

| Port | Backed later by |
| --- | --- |
| `RealityReader`, `RealityMutator`, `RealityVerifier` | MCP tools |
| `CandidatePlanner`, `AdversarialTester` | TrueForge |
| `WorldExecutor` | sandbox providers |
| `RunRepository`, `EventSink` | a real datastore |

Phase 1 ships no adapter for any of these beyond in-memory storage, and an orchestrator built without a port fails loudly rather than pretending the step ran.

### Run lifecycle

```text
CREATED → OBSERVING → PLANNING → FORKING → EXECUTING_WORLDS → ADVERSARIAL_TESTING
        → COMPARING → AWAITING_APPROVAL → APPROVED → COMMITTING → VERIFYING → SUCCEEDED
```

`REJECTED` and `FAILED` are terminal. Transitions are explicit and validated: `CREATED → COMMITTING`, `AWAITING_APPROVAL → SUCCEEDED`, and `REJECTED → COMMITTING` all raise.

### World lifecycle

```text
CREATED → PREPARING → EXECUTING → ATTACKING → EVALUATING → SURVIVED | VETOED | FAILED
```

### Approval safety

- Only a world whose verdict is `SURVIVED` and which comparison found eligible may be selected.
- Approval can only be requested after deterministic comparison, and only once per run.
- Commit requires a granted approval; a pending or rejected one is not enough.
- Approval binds the exact world *and* a content fingerprint of the exact action. If the action changes after approval, the fingerprint no longer matches and the commit is refused.

## Local development

Requires Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```bash
cd backend

uv sync

uv run uvicorn app.main:app --reload
```

The health endpoint is available at:

```text
http://localhost:8000/health
```

Run the automated checks with:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Service liveness. |
| `POST` | `/api/v1/runs` | Open a run for an incident. |
| `GET` | `/api/v1/runs` | List runs, newest first. |
| `GET` | `/api/v1/runs/{run_id}` | Inspect one run, its worlds, comparison, and approval. |
| `GET` | `/api/v1/runs/{run_id}/events` | The run's timeline. |

OpenAPI is served at `/openapi.json`.

Endpoints that would drive a run past creation are deliberately absent: without planner, executor, and adversarial adapters they could only fake the work.

## Phase 1 scope

Implemented: the deterministic domain and application core — run and world state machines, evidence, counterexamples, verdicts, the comparator, approval and commit invariants, verification, run events, in-memory storage, and run inspection over HTTP. It runs with zero external network dependencies.

Deferred by design: LLM calls, TrueForge, MCP, sandbox providers, real persistence, WebSockets, and the frontend.
