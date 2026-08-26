# BRANCHPOINT — submission checklist

## Repository

- [ ] Final PRs merged to `main`
- [ ] Qodo review comments resolved
- [ ] Backend CI green (`.github/workflows/backend.yml`)
- [ ] Frontend CI green (`.github/workflows/frontend.yml`)
- [ ] No secrets in tracked files — `git ls-files | xargs grep -niE 'API_KEY|SECRET|TOKEN|Bearer '`
- [ ] `.env` untracked; `.env.example` carries names only
- [ ] README current, test counts match reality

Local gate before pushing:

```bash
cd backend  && uv run pytest && uv run ruff check . && uv run ruff format --check .
cd frontend && npm run typecheck && npm run test -- --run && npm run build
```

Expected: **556 backend**, **156 frontend**, lint and build clean.

## Demo — one live run, end to end

Start clean (`POST /api/v1/demo/reset`), then walk the run once:

- [ ] Fresh hero run starts in one click, run id returned immediately
- [ ] Planner session bound (Harness → `PLANNER · sess_…`)
- [ ] MCP event visible (`MCP · branchpoint_*`)
- [ ] `sandbox.created` with a real `v1:daytona:…` id
- [ ] Sandbox exec with `exitCode 0`
- [ ] `Subagent · Compatibility Skeptic`
- [ ] Alpha shows the real exploratory hypothesis
- [ ] Alpha shows the verified failing evidence (`schema_compatibility`, `payment_retry`)
- [ ] Alpha counterexample `REPRODUCED`
- [ ] Alpha `VETOED`
- [ ] Beta `SURVIVED` and `RECOMMENDED` by the comparator
- [ ] Human checkpoint shows bound world, action id, fingerprint
- [ ] Approve → `COMMITTING`
- [ ] → `VERIFYING`
- [ ] → `SUCCEEDED`
- [ ] Reality changed: `PRICING_V2 OFF`, header reads `CURRENT REALITY — VERIFIED CHANGE`
- [ ] Browser refresh mid-run: same TrueForge session ids, `SESSION CONTINUITY · RESTORED`, no duplicate drive

Optional second pass, if time allows:

- [ ] Rejection ending: `HUMAN DECISION · REJECTED`, reality unchanged, world still `SURVIVED`

## Capture

- [ ] Branch graph — fork, three lanes, α vetoed, β recommended merging to trunk
- [ ] Harness tab — MCP + sandbox + subagent + approval rows visible together
- [ ] Proof chain — α's four stages in the Inspector
- [ ] Human checkpoint — bound action and fingerprint, both buttons
- [ ] Final verified state — header showing `VERIFIED CHANGE` and `PRICING_V2 OFF`

Capture at **1440×900**, drawer expanded for the Harness shot.

## Submission

- [ ] GitHub URL: `___`
- [ ] Deployed URL: `___` *(owned by the deployment teammate)*
- [ ] Demo video: `___`
- [ ] Team names: `___`
- [ ] TrueForge usage statement — see the table in [`../README.md`](../README.md)
      and [`JUDGING.md`](JUDGING.md); **do not claim the optional skill is active**
- [ ] Code-quality statement — Qodo on PRs, GitHub Actions CI, Ruff, strict
      TypeScript, pytest, Vitest

## Honesty check

Before submitting, confirm nothing claims:

- [ ] durable persistence (runs are in process memory)
- [ ] multi-worker support (one worker required)
- [ ] the TrueForge skill is enabled (it is opt-in)
- [ ] a DOPPELGÄNGER stage on the `/demo/hero` fixture (there isn't one)
