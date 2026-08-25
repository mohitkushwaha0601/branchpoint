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
  infrastructure/  adapters for external systems
    demo/          the checkout Operational Digital Twin (Phase 2, isolated from core domain)
    persistence/   in-memory run/event storage
  mcp/             the MCP server exposing the demo surface over streamable HTTP (Phase 2)
```

The domain layer imports no framework, transport, database, sandbox, or model SDK. Domain objects are frozen Pydantic models: every state change returns a revalidated copy rather than mutating in place. `app/infrastructure/demo/` follows the same discipline for its own state (`DemoProductionState` and friends are frozen too) — it is demo-specific infrastructure, and nothing under `app/domain/` imports from it.

Everything the domain does not own arrives through a port in `app/application/ports.py`:

| Port | Phase 1 | Phase 2 (checkout demo) |
| --- | --- | --- |
| `RealityReader` | none (fails loudly) | `DemoRealityReader` — reads the digital twin |
| `RealityMutator` | none (fails loudly) | `DemoRealityMutator` — capability-gated reality mutation |
| `RealityVerifier` | none (fails loudly) | `DemoRealityVerifier` — independently re-checks reality |
| `WorldExecutor` | none (fails loudly) | `DemoWorldExecutor` — executes an action in an isolated snapshot |
| `CandidatePlanner` | none (fails loudly) | `HeroCandidatePlanner` — deterministic demo test adapter, **not AI** |
| `AdversarialTester` | none (fails loudly) | `HeroAdversarialTester` — deterministic demo test adapter, **not AI** |
| `RunRepository`, `EventSink` | in-memory | in-memory (same instance, shared with Phase 2) |

`HeroCandidatePlanner` and `HeroAdversarialTester` exist to prove the deterministic pipeline end to end before any agent exists. TrueForge replaces both in Phase 3; nothing about them represents final agent behavior.

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

## Demo Production: the checkout incident

Phase 2 adds a small, deterministic **Operational Digital Twin** of a commerce system — no real microservices, no Kubernetes, just typed in-memory state under `app/infrastructure/demo/`, seeded from the packaged fixture [`app/infrastructure/demo/scenarios/checkout_regression.json`](app/infrastructure/demo/scenarios/checkout_regression.json) (ships inside the wheel; override with `BRANCHPOINT_DEMO_SCENARIO_PATH`).

**Initial incident:** `pricing-service` is on `v2.41` (previous version `v2.40`) with the `PRICING_V2` flag enabled and 4 replicas. This combination activates a pricing regression: checkout error rate ≈ **41.3%**, p95 latency ≈ **4.8s**, ≈ **8,000** affected users/day. Five synthetic orders exist; three were created under `v2.41` and carry a `payment_revision` field — a schema-41 addition `v2.40` has no code path for.

Every metric is a **pure function of state** (`app/infrastructure/demo/metrics.py`) — same state always yields the same numbers, nothing is randomized or asked of a model. The regression is defined structurally: it is active exactly when the flag is enabled *and* the deployed version is `v2.41`; disabling the flag or rolling the version back both bypass it independently, and adding replicas eases queueing pressure (a floor of 7% error rate remains, because the buggy code is still running).

Three candidate actions are available, and none of their outcomes are scripted — each is *measured*:

| World | Action | Headline result | Hidden cost |
| --- | --- | --- | --- |
| **Alpha** | Roll back to `v2.40` | Error rate → **1.8%**, strong latency recovery | `v2.40` cannot deserialize a `v2.41` order's `payment_revision` — a payment retry recomputes a different idempotency key than the original charge used, so retrying is not idempotent. Reproduced as a `CRITICAL`, machine-verifiable counterexample. |
| **Beta** | Disable `PRICING_V2` | Error rate → **1.4%**, p95 ≈ 320ms | None measured — data integrity, payment retry, and every regression check pass; no cost increase. |
| **Gamma** | Scale to 12 replicas | Error rate → **7%**, cost **+$900/day** | Mitigates but does not solve: the regression is still active, so the recovery SLO is not met. |

**Why rollback fails, mechanically:** `app/infrastructure/demo/workload.py` models a deployment's schema support as data (`{"v2.40": 40, "v2.41": 41}`) and a field's introduction schema as data (`payment_revision` → schema 41). A retry's idempotency key is derived from the order's `payment_revision` only if the active deployment supports that schema; `v2.40` doesn't, so it falls back to a legacy key that doesn't match the original charge's key. This check runs identically against every world's resulting state — it has no idea which action produced that state, and it does not reproduce against beta or gamma, because their state genuinely doesn't break it.

This mechanism is exercised in two places, deliberately kept apart:

- `DemoWorldExecutor` (execution phase) runs only aggregate checks — headline metrics, general orders-table sanity. Alpha looks *excellent* here: this is what makes the later veto meaningful rather than foregone.
- `HeroAdversarialTester` (attack phase) runs the order-compatibility suite specifically, and is what actually produces the `REPRODUCED` counterexample that vetoes alpha — exactly the reproducible-evidence mechanism Phase 3's real DOPPELGÄNGER will exercise dynamically.

### World isolation

Every `DemoProductionState` snapshot is a frozen Pydantic model. Applying an action always returns a *new* snapshot; nothing is ever mutated in place. World isolation therefore isn't a deep-copy convention that could be silently violated later — there is no shared mutable object for one world's mutation to leak through to another, or to reality.

## MCP

BRANCHPOINT exposes the demo digital twin through a real MCP server (`app/mcp/server.py`), built on `mcp` (PyPI `mcp>=2.1,<3`, using its `mcp.server.mcpserver.MCPServer` — the successor to the older `FastMCP` name) over the streamable HTTP transport, mounted directly into the FastAPI app.

**Start it** — it's part of the same process as the REST API:

```bash
uv run uvicorn app.main:app --reload
```

**Endpoint:** `POST http://localhost:8000/mcp` (plus the existing `GET /health`). The MCP sub-app is mounted at the FastAPI root with its default path, so this resolves directly — no trailing-slash redirect for a client to (possibly incorrectly) follow.

DNS-rebinding Host/Origin validation is **on** by default, restricted to `localhost`/`127.0.0.1`/`[::1]` (with and without a port). This is the backstop for "only reachable from localhost" — it rejects requests whose Host/Origin doesn't claim to be local, independent of which interface the process is actually bound to. It is not the authorization boundary for mutations (the one-time commit capability is — see **Security model** below), but read tools have no capability gate, so this is what stands between them and the network. Set `BRANCHPOINT_MCP_INSECURE_LOCALHOST=true` to disable it (an explicit opt-in only; never do this on a non-loopback bind).

**Tools** (10 total, every one carries explicit `readOnlyHint`/`destructiveHint` annotations — `tests/mcp/test_mcp_server.py` asserts none ships without them):

| Read (`readOnlyHint=true`, `destructiveHint=false`) | Destructive (`readOnlyHint=false`, `destructiveHint=true`) |
| --- | --- |
| `branchpoint_get_incident` | `branchpoint_disable_feature_flag` |
| `branchpoint_get_metrics` | `branchpoint_set_deployment_version` |
| `branchpoint_get_deployment` | `branchpoint_scale_service` |
| `branchpoint_get_feature_flags` | |
| `branchpoint_get_schema` | |
| `branchpoint_get_orders_summary` (aggregate counts only — never raw order records) | |
| `branchpoint_get_reality_state` | |

Destructive tools take tightly typed parameters only (e.g. `version: Literal["v2.40", "v2.41"]`, `target_replicas: int` bounded `1–50`) — no arbitrary strings, object paths, or code. **Counterfactual worlds are never exposed for mutation over MCP**: no tool accepts a `world_id`, and no tool name contains "world". World execution belongs exclusively to `DemoWorldExecutor`, reached only through the BRANCHPOINT orchestrator.

## Demo reset

```text
GET  /api/v1/demo/state    read the current digital twin state and derived metrics
POST /api/v1/demo/reset    restore the exact initial incident, discard every world snapshot
```

`POST /api/v1/demo/reset` returns `404` when `BRANCHPOINT_ENV=production` (checked via `Settings.is_production`). Neither endpoint exposes capability tokens, hashes, or raw order records.

## Security model

Mutating reality requires **all** of the following, layered as defense in depth:

1. **BRANCHPOINT domain approval** — `app.domain.approvals.rules.assert_commit_allowed` (Phase 1, untouched): only a world whose verdict is `SURVIVED`, comparison found eligible, and a human explicitly approved may be committed.
2. **One-time commit capability** — `app/infrastructure/demo/capability.py`. A capability is issued only after step 1 passes, is bound to the exact `run_id`/`world_id`/`action_id`/*action content fingerprint*, is a cryptographically random opaque token (`secrets.token_urlsafe`, never a JWT), and is spent atomically exactly once. It rejects: missing, invalid, expired, replayed, or mismatched (wrong run/world/action, or an action whose parameters changed after approval — fingerprint mismatch) tokens. Only its SHA-256 hash is ever stored; the raw token is returned exactly once by `POST /api/v1/runs/{run_id}/commit-capability` and never logged (`CommitCapability.__repr__` redacts it; see `tests/demo/test_capability.py::test_capability_token_never_appears_in_logs`).
3. **Destructive MCP tool** — every mutation tool (`branchpoint_disable_feature_flag`, `branchpoint_set_deployment_version`, `branchpoint_scale_service`) resolves its capability, checks it authorizes exactly that tool's action type and parameters, and only then calls `DemoProductionEngine.apply_to_reality` — the *single* mutation path shared with BRANCHPOINT's own `RealityMutator`, so the capability check cannot be bypassed by calling a different entry point.
4. **TrueForge tool approval** — Phase 3. Not implemented here.

Step 2 is not decorative: calling a destructive MCP tool directly, bypassing the orchestrator entirely, still requires a valid capability and is rejected identically without one (`tests/mcp/test_mcp_server.py::test_destructive_call_without_capability_fails`).

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

## Docker deployment

Build the image from the `backend` directory:

```bash
docker build -t branchpoint-backend:latest .
```

Run the container:

```bash
docker run --rm -p 8000:8000 --name branchpoint-backend branchpoint-backend:latest
```

Health check endpoint:

```text
http://localhost:8000/health
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Service liveness. |
| `POST` | `/api/v1/runs` | Open a run for an incident. |
| `GET` | `/api/v1/runs` | List runs, newest first. |
| `GET` | `/api/v1/runs/{run_id}` | Inspect one run, its worlds, comparison, and approval. |
| `GET` | `/api/v1/runs/{run_id}/events` | The run's timeline. |
| `POST` | `/api/v1/runs/{run_id}/execute-demo-worlds` | Drive an existing run through observe → plan → fork → execute → attack → compare → request-approval using the deterministic Phase 2 demo adapters. Never commits. |
| `POST` | `/api/v1/runs/{run_id}/commit-capability` | Issue a one-time commit capability for an `APPROVED` run's selected world. Returns the raw token exactly once. |
| `GET` | `/api/v1/demo/state` | Read-only current digital twin state and derived metrics. |
| `POST` | `/api/v1/demo/reset` | Restore the exact initial incident. Unavailable in production. |
| `POST` | `/mcp` | The MCP server, streamable HTTP transport. See **MCP** above. |

OpenAPI is served at `/openapi.json`.

There is still no HTTP endpoint to decide an approval or drive a commit/verify: doing so from a plain REST call would bypass the point of an explicit human-approval gate. Exercise that part of the lifecycle through the orchestrator directly (see `tests/demo/test_hero_integration.py`) or, for a real mutation, through `POST .../commit-capability` plus a destructive MCP tool.

## Phase scope

**Phase 1** (deterministic domain core): run and world state machines, evidence, counterexamples, verdicts, the comparator, approval and commit invariants, verification, run events, in-memory storage, and run inspection over HTTP. Zero external network dependencies.

**Phase 2** (this phase): the checkout Operational Digital Twin, its metrics and workload/regression engines, Phase 1 port adapters backed by it, the one-time commit capability security layer, the deterministic hero demo test adapters, and the MCP server. Still zero external network dependencies — everything runs in-process with in-memory state.

**Deferred to Phase 3**: TrueForge agent orchestration (replacing `HeroCandidatePlanner`/`HeroAdversarialTester`), a real DOPPELGÄNGER, any LLM/model SDK, sandbox providers, real persistence, WebSockets, and the frontend.
