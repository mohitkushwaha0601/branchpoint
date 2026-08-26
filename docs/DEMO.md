# BRANCHPOINT — demo script

**Target: 2:40.** Everything below is real UI. Nothing is staged or narrated
ahead of what the screen shows.

## Before you start

```bash
# backend, sandbox on
cd backend && BRANCHPOINT_TRUEFORGE_SANDBOX_ENABLED=true \
  uv run uvicorn app.main:app --port 8000

# TrueForge + provider + MCP registration
npx @truefoundry/trueforge@0.1.4
./trueforge/scripts/setup_trueforge.sh
export BRANCHPOINT_MODEL="<provider>/<model-id>"

# frontend
cd frontend && npm run dev
```

Open `http://localhost:5173/runs` at **1440×900**. Drawer collapsed.
Have `POST /api/v1/demo/reset` ready if you need a clean incident.

---

## 0:00 – 0:20 · The problem

> "Production agents have a dangerous property: they only get one production
> environment, and one chance."

> "BRANCHPOINT gives agents branches before it gives them permissions."

---

## 0:20 – 0:35 · Broken reality

Point at the header.

> "Checkout is at 41.3% error, p95 4.8 seconds. Pricing-service is on v2.41."

Click **Run BRANCHPOINT**.

> "One click. The hero incident is preloaded — no typing."

The run id appears immediately and the stage rail starts moving.

---

## 0:35 – 0:55 · Three futures

> "The planner proposes three materially different remediations, and
> BRANCHPOINT forks a counterfactual world for each one."

Point at the branch graph as lanes appear.

> "These are rehearsals against isolated copies of production. Reality has not
> changed — the header still says CURRENT REALITY, UNCHANGED."

---

## 0:55 – 1:15 · This is a real harness

Open the drawer on **Harness**.

> "This isn't a decorative agent animation. These are actual TrueForge harness
> events, read from TrueForge's own event log."

Point at three rows in turn:

- `MCP · branchpoint_get_metrics`
- `Daytona sandbox created — v1:daytona:…`
- `Subagent · Compatibility Skeptic`

> "MCP tool calls. A real Daytona sandbox. And a real dynamic subagent — the
> DOPPELGÄNGER delegated a narrow compatibility question to a bounded skeptic."

> "If TrueForge hadn't emitted these, nothing would appear here. Model prose
> claiming it used a sandbox is not accepted as proof."

---

## 1:15 – 1:40 · Evidence beats confidence

Click **World α — Rollback Pricing Deployment**.

> "DOPPELGÄNGER suspects that rolling back breaks compatibility with orders
> written under the newer schema."

Point at stage 1.

> "EXPLORATORY. That allegation carries zero authority — it's a model's opinion
> and BRANCHPOINT treats it as one."

Point at stage 2.

> "BRANCHPOINT takes the typed counterexample and replays it itself, against
> this world's own snapshot. VERIFIED. schema_compatibility failed.
> payment_retry failed."

Point at stages 3 and 4.

> "REPRODUCED. VETOED."

> "And notice — the rollback *did* fix the error rate. It looked best on the
> dashboard. Evidence beats confidence."

---

## 1:40 – 1:58 · The comparator

Click **World β — Disable Pricing V2**.

> "Beta survived. The deterministic comparator ranks it first — goal achieved,
> no regressions, smallest blast radius."

> "There's no AI score anywhere in this system. That ranking is arithmetic over
> measured outcomes."

---

## 1:58 – 2:18 · Recommendation is not permission

Scroll to the **HUMAN CHECKPOINT**.

> "BRANCHPOINT will not act on its own recommendation."

Point at the bound action and fingerprint.

> "One world, one action, one fingerprint. The browser can't name anything else
> — it can only confirm what BRANCHPOINT already bound."

Click **Approve & Commit**.

---

## 2:18 – 2:35 · Commit and verify

Let the states arrive on their own.

> "APPROVED. COMMITTING — through the destructive MCP tool, behind TrueForge's
> approval gate and a one-time capability. VERIFYING — BRANCHPOINT independently
> re-reads reality. SUCCEEDED."

Point at the header.

> "PRICING_V2 is now OFF. Checkout error 1.4%. And only now does it say VERIFIED
> CHANGE — because verification passed, not because we asked for a commit."

---

## 2:35 – 2:45 · Close

> "AI agents shouldn't predict the future. They should rehearse it."

---

## Backup lines

Use these instead of waiting in silence. Never claim something that isn't on
screen.

**TrueForge is slow / planning takes a while**

> "While the planner works — every one of these steps is a real model call
> through TrueForge. We're watching the actual harness, not a replay."

Fill with the stage rail: *"Observe, plan, fork, execute, attack, compare — the
run only advances when the backend says it did."*

**Sandbox takes a while to provision**

> "Daytona is provisioning a sandbox for the adversary. It's optional by design —
> if it never comes up, the DOPPELGÄNGER investigates with read-only tools
> instead, and BRANCHPOINT replays whatever it proposes either way."

**A harness row arrives late**

> "The Harness tab reads TrueForge's event log directly, so rows appear when
> TrueForge actually emits them. That's the point — we're not animating."

Move on to the proof chain; come back to Harness at 2:35 if it lands.

**No subagent row appears**

> "Subagent delegation is model-directed — we instruct it, TrueForge exposes the
> tool, the model decides. When it fires you see it here."

Then show MCP and sandbox rows, which are reliable, and continue. **Do not claim
the subagent ran.**

**The backend restarted and the run is gone**

> "Runs live in process memory in this build — you can see it says so."

Point at *"Run no longer exists"*, then click **Run BRANCHPOINT** and rejoin at
0:35.

**Showing rejection instead of approval** *(alternate ending, ~15s)*

> "The other ending: a human declines."

Click **Reject**, type a reason, confirm.

> "HUMAN DECISION — REJECTED. Nothing committed. Reality unchanged. And note the
> world still says SURVIVED — this is a governance decision, not a safety one."
