# BRANCHPOINT × TrueForge

TrueForge is the **agent harness**. BRANCHPOINT is the **safety, evidence, and execution core**. Nothing in this directory reimplements TrueForge: it is configuration for using TrueForge as an external runtime.

## Verified upstream version

Everything here was built against, and empirically verified on:

| | |
| --- | --- |
| Package | `@truefoundry/trueforge` |
| Version | **0.1.4** (published 2026-08-19) |
| Mode | `standalone` (local), SQLite persistence, auth disabled |
| API | REST + SSE, OpenAPI at `/api/v1/docs`, spec at `https://trueforge.dev/openapi.json` |
| Bind address | `http://localhost:8790` — **IPv6 loopback (`[::1]`) only**; a literal `127.0.0.1` does *not* reach it |
| Sandbox | local fallback available with no Daytona key (`darwin`/`bash`/`python`) |

If you upgrade TrueForge, re-run `backend/scripts/smoke_trueforge.py` first: stages 1–4 need no model provider and will catch an API or annotation-classification regression immediately.

## Startup order

```bash
# 1. BRANCHPOINT backend (serves the MCP server at /mcp)
cd backend && uv run uvicorn app.main:app --port 8000

# 2. TrueForge
npx @truefoundry/trueforge@0.1.4          # -> http://localhost:8790

# 3. Configure a model provider (the key lives in TrueForge, never in BRANCHPOINT)
curl -X PUT http://localhost:8790/api/v1/settings/model-providers \
  -H 'content-type: application/json' \
  -d '{"manifest":{"type":"anthropic","name":"anthropic",
       "auth":{"type":"api_key","api_key":"'"$ANTHROPIC_API_KEY"'"}}}'

# 4. Register BRANCHPOINT's MCP server (and print how TrueForge classifies each tool)
./trueforge/scripts/setup_trueforge.sh

# 5. Configure the sandbox (optional: the local fallback is used when none is set)
#    Daytona: PUT /api/v1/settings/sandbox-providers

# 6. Tell the backend which model to drive, then start an agent run
export BRANCHPOINT_TRUEFORGE_MODEL="anthropic/<model-id-from-/api/v1/models>"
curl -X POST http://127.0.0.1:8000/api/v1/agent-runs \
  -H 'content-type: application/json' \
  -d '{"objective":"Fix the checkout production incident."}'
```

## Who owns what

| TrueForge owns | BRANCHPOINT owns |
| --- | --- |
| Model execution, sessions, turns, streaming | Typed domain contracts and invariants |
| Subagents (`dynamic_sub_agents`) | The digital twin and world isolation |
| Sandbox provisioning and code execution | Deterministic metrics |
| Human tool approval checkpoints | Evidence validity and counterexample **reproduction** |
| Context handling and persistence (SQLite) | Verdicts, comparison, approval binding |
| | Capability authorization, reality mutation, verification |

No model is ever authoritative for evidence validity, a world verdict, comparison, approval, mutation authorization, or verification success.

## Agent specs

`agents/*.json` are real `AgentSpec` bodies for `POST /api/v1/sessions` (`{"agent": {"spec": ...}}`). The backend builds these programmatically in `app/infrastructure/trueforge/{planner,adversary}.py`; the JSON files document the same shape for manual use in the TrueForge UI. Replace `REPLACE_WITH_PROVIDER/MODEL` with a model FQN from `GET /api/v1/models`.

- **`planner.json`** — read-only reality tools, **no sandbox**, **no subagents**.
- **`doppelganger.json`** — read-only *world* tools, **subagents on**, and the only spec that may carry a **sandbox** (`config.sandbox.enabled`, driven by `BRANCHPOINT_TRUEFORGE_SANDBOX_ENABLED`).
- **`commit-operator.json`** — the only spec that can reach a destructive tool, and it pauses for approval.

## Code Mode / destructive-tool classification

The known upstream concern is that MCP annotation changes can cause destructive tools to be misclassified, which would let Code Mode call them without an approval pause.

**Verified on 0.1.4: this does not reproduce against BRANCHPOINT.** `GET /api/v1/mcp-servers/branchpoint/tools` returns all 17 tools with correct hints — 13 `readOnlyHint: true`, 4 `destructiveHint: true` — because every BRANCHPOINT tool ships explicit annotations (Phase 2). `smoke_trueforge.py` stage 4 asserts exactly this and needs no model to run.

We still apply defense in depth, in this order:

1. **Literal tool names.** Every agent spec lists `enable_tools` by name. The planner and DOPPELGÄNGER sessions cannot reach *any* mutation tool — not because it is classified safely, but because it is not enabled at all. Classification is irrelevant to a tool that isn't there.
2. **Literal names in `require_approval_for_tools`** alongside `@destructive` (see `commit-operator.json`), so approval binds even if a selector stopped resolving.
3. **BRANCHPOINT's own capability gate**, which is independent of TrueForge entirely — a destructive MCP tool invoked directly, bypassing TrueForge, is still rejected without a valid one-time capability.

Layer 3 is the one that actually enforces safety. Layers 1–2 mean the model never gets the chance.

## Human approval path

```
HUMAN clicks approve in TrueForge
   ↓  TrueForge emits tool.approval_required, then resumes on user.tool_approval
BRANCHPOINT exact-world/action approval  (assert_commit_allowed + fingerprint)
   ↓
one-time commit capability  (issued, then atomically consumed)
   ↓
destructive MCP tool  (branchpoint_commit_recommended_world)
   ↓
REALITY
   ↓
independent verification  (RealityVerifier re-reads reality)
```

A turn pauses with `tool.approval_required`; only a client-supplied `user.tool_approval` input item resumes it. The model cannot approve its own tool call, and assistant prose saying "approved" has no effect anywhere.

## Sandbox trust boundary

`BRANCHPOINT_TRUEFORGE_SANDBOX_ENABLED` turns the sandbox on for **DOPPELGÄNGER sessions only**. It is off unless set, so code execution is something a deployment opts into rather than something it inherits. The planner and the commit operator are hardwired to `sandbox.enabled: false` and never read the setting: nothing that reads reality or writes to it is given code execution. Enabling it grants TrueForge's built-in `exec` inside the sandbox and nothing else — the enabled MCP tool list is byte-for-byte identical either way, so no destructive tool becomes reachable.

The DOPPELGÄNGER may write and run whatever it likes in its sandbox. That output is **exploratory evidence only** — BRANCHPOINT records it with `machine_verifiable=False`, so it can never contribute to a veto. The same is true of a subagent's summary and the model's own prose: sandbox `exec`, sandbox files, sandbox scripts, subagent prose, and model prose are all one provenance class, and none of them can mark a counterexample `REPRODUCED`.

If the sandbox is unavailable, the adversary fails closed like any other TrueForge failure: an errored turn raises, the world goes `INCONCLUSIVE`, and a missing sandbox never reads as "this world was safely attacked".

The only authoritative path is a typed `CounterexampleSpec` replayed by BRANCHPOINT against the world's own isolated snapshot. Every operation in that spec maps to a named, allowlisted demo primitive; there is no way to submit code. Sandbox-generated code never runs in the FastAPI process, and the sandbox cannot reach reality.

## Skills (optional, opt-in)

`skills/incident-counterfactual-review/SKILL.md` is a reusable adversarial
incident-review playbook. TrueForge 0.1.4 mounts skills by name in the agent
spec (`skills: [{name}]`) after they are registered out of band with a git
manifest — verified in its client bundle as `{type, url, name, ref, path?}`:

```bash
curl -X PUT http://localhost:8790/api/v1/settings/skills \
  -H 'content-type: application/json' \
  -d '{"manifest":{"type":"git",
       "name":"incident-counterfactual-review",
       "url":"https://github.com/<owner>/branchpoint",
       "ref":"main",
       "path":"trueforge/skills/incident-counterfactual-review"}}'

# only once TrueForge confirms the skill:
export BRANCHPOINT_TRUEFORGE_SKILL_NAME=incident-counterfactual-review
```

A `description` may be included in the manifest; the server stores
`{type, name, url, path, ref, description}` and nothing is read from the file
itself at registration time.

It is **off by default and deliberately so**, for four reasons found by reading
the 0.1.4 server bundle rather than assumed:

1. **Registration is a network operation.** TrueForge clones the named repo with
   its own `git_downloader.py`, so the repo must be public and reachable at
   registration time. It cannot be performed or verified offline.
2. **A skill needs a sandbox.** `getSkillsDir()` is called from `createSandbox`
   and the skill is materialised in the sandbox working directory. So a mounted
   skill is only usable when `BRANCHPOINT_TRUEFORGE_SANDBOX_ENABLED=true` —
   enabling the skill with the sandbox off mounts something TrueForge cannot
   place.
3. **A missing skill stops the turn.** The server's own error text is explicit:
   a turn "cannot be processed" when "a referenced resource is missing (named
   agent, model, MCP server, skill, or sandbox provider)". Naming an
   unregistered skill breaks the run at the least affordable moment.
4. **Subagent inheritance is unverifiable here.** Whether a model-created
   subagent inherits its parent's skills is not answerable from this package:
   `create_sub_agent` appears in the client bundle but the server bundle
   contains no subagent implementation at all. Attaching the skill to the
   Compatibility Skeptic specifically would be guesswork.

With `BRANCHPOINT_TRUEFORGE_SKILL_NAME` unset the DOPPELGÄNGER spec carries no
`skills` key at all — exactly the hero path as shipped. The planner and the
commit operator never carry one under any setting: they run with the sandbox
off, and only the adversary's spec builder accepts a skill name.

Whether or not it is mounted, the skill is **exploratory**. It instructs an
agent on how to look for a counterexample; it cannot make one authoritative,
and only BRANCHPOINT's deterministic replay produces evidence that can veto.

## Sessions and resume

TrueForge persists sessions, turns, and events in SQLite. BRANCHPOINT stores only a `TrueForgeSessionBinding` (`run_id`, optional `world_id`, purpose, `trueforge_session_id`, status, `last_turn_id`, pending tool-call id) so a domain run can be reconnected to its sessions after a restart. Re-binding the same run/world/purpose updates in place, so an interrupted run cannot duplicate a world or a commit.
