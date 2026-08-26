# BRANCHPOINT — judging guide

Every claim here is verifiable from the code or the running UI. Where something
is not implemented, it says so.

---

## Impact

**Problem.** Agents can cause irreversible production changes from plausible but
incorrect reasoning. The failure mode that matters is not an obviously bad
action — it is a *convincing* one that fixes the headline metric and breaks
something nobody is watching.

**Proof.** In the hero scenario the rollback (world α) genuinely recovers
checkout error rate and latency. It is still blocked, because BRANCHPOINT
reproduced a `schema_compatibility` and `payment_retry` failure against that
world's own snapshot.

**Where to see it.** Open world α in Mission Control. The proof chain ends in
`VETOED`, and the RESULT section shows the metrics really did improve.

---

## Creativity

Three ideas composed rather than one:

1. **Counterfactual execution** — every candidate action is rehearsed against
   its own isolated copy of production before anything is permitted.
2. **Adversarial DOPPELGÄNGER** — a creative agent whose entire job is to
   invalidate the proposal, with a sandbox and a subagent to do it with.
3. **Deterministic replay as the arbiter** — the adversary's creativity is
   uncapped precisely because its authority is zero.

The result is a system where the agent is *encouraged* to be imaginative,
because imagination cannot become permission.

---

## Technical excellence

| Claim | Where |
|---|---|
| Deterministic domain invariants | `backend/app/domain/` — frozen models, asserted transitions |
| **556 backend tests** | `cd backend && uv run pytest` |
| **163 frontend tests** | `cd frontend && npm run test -- --run` |
| Exact action fingerprinting | `CandidateAction.fingerprint()` — SHA-256 of canonical content |
| One-use commit capability | `app/infrastructure/demo/capability.py`, consumed atomically |
| Typed APIs end to end | Pydantic response models; strict TS with `noUncheckedIndexedAccess` |
| CI | `.github/workflows/{backend,frontend}.yml` on PRs and `main` |
| Lint | Ruff check + format clean, 137 files |

No test makes a model, network, TrueForge, or Daytona call — the entire suite
runs offline and free.

Worth a look specifically:

- `tests/trueforge/test_sandbox_boundary.py` — 39 tests pinning that sandbox
  output cannot veto
- `tests/api/test_world_evidence_api.py` — a claimed reproduction with no
  qualifying evidence serializes as non-authoritative
- `tests/trueforge/test_approval_commit_path.py` — an allow-list of every
  mutating HTTP route; a new one must be added deliberately

---

## TrueForge

| Feature | Where to click | What you should see |
|---|---|---|
| **MCP** | Drawer → **Harness** | `MCP · branchpoint_get_metrics`, `branchpoint_get_schema`, … with `branchpoint` as the server |
| **Daytona sandbox** | Drawer → **Harness** | `Daytona sandbox created` with a real `v1:daytona:…` id |
| **Sandbox execution** | Drawer → **Harness** | `Sandbox exec completed · exitCode 0` |
| **Dynamic subagent** | Drawer → **Harness** | `Subagent · Compatibility Skeptic` — a real `create_sub_agent` call and nested thread |
| **Human approval** | Drawer → **Harness**, after approving | `Human approval required` → `Approved call executed · branchpoint_commit_recommended_world` |
| **Persistent sessions** | Drawer → **Harness**, then reload the page | The same `PLANNER` / `ADVERSARY` session ids, and `SESSION CONTINUITY · RESTORED` |
| **Harness Trace** | Drawer → **Harness** | The whole timeline, from TrueForge's own event log |
| **Skill** | — | **Not enabled by default.** The playbook is committed at `trueforge/skills/incident-counterfactual-review/SKILL.md`; registration needs a reachable TrueForge and is documented in `trueforge/README.md` |

Two things worth knowing about the Harness tab:

- Rows come from TrueForge's event log, normalized and redacted server-side.
  **Model prose claiming a sandbox was used produces no row.** If TrueForge
  emitted no `sandbox.created`, none appears.
- If TrueForge is unreachable, the tab says `TRUEFORGE UNREACHABLE` and still
  shows BRANCHPOINT's own session bindings rather than an empty panel.

---

## Safety and control

The chain a judge can read in the Inspector, driven entirely by structured
fields — never by parsing a summary string:

```
DOPPELGÄNGER        EXPLORATORY     machine_verifiable = false
        ↓
BRANCHPOINT REPLAY  VERIFIED        machine_verifiable = true
        ↓
COUNTEREXAMPLE      REPRODUCED      backend status + qualifying evidence
        ↓
VERDICT             VETOED          world.veto
```

Three properties to check:

1. **Authority comes from one bit.** `machine_verifiable`, not the source name.
   A sandbox record saying *"the invariant broke"* is still exploratory.
2. **Reproduced ≠ authoritative.** A counterexample can claim reproduction and
   carry `authoritative: false` if nothing qualifying backs it. It vetoes
   nothing.
3. **Nothing is fabricated.** The deterministic `/demo/hero` fixture has no
   DOPPELGÄNGER stage, and the chain renders it as `NOT PRESENT` rather than
   inventing one.

**Human authority is separate from technical safety.** A world can be `VETOED`
by BRANCHPOINT (machine-verifiable), and a *surviving, recommended* world can
still be `REJECTED` by a person (governance). The two have different words,
icons, and colours, and rejecting changes no verdict and commits nothing.

---

## Presentation

- A real **git-style counterfactual branch graph** — CSS Grid with measured SVG
  connectors, no graph library. One fork, three branches, the recommended one
  merging back to the trunk toward approval.
- GitHub Actions / GitLab pipeline visual language: a nine-stage rail, job rows
  with status glyphs, a bottom drawer.
- Status is never colour alone — every badge pairs a glyph with a word, and
  screen readers get the same information.
- The whole UI is dark, monospace where it matters (ids, metrics, fingerprints),
  and has no gradients, no giant cards, and **no AI confidence score anywhere**.

---

## What is deliberately not claimed

- Runs live in process memory; a backend restart ends them, and the UI says so.
- One backend worker is required.
- The optional TrueForge skill is not active by default.
- Reconnect demonstrates session continuity, not durable persistence.
