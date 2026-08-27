# Landing + How It Works — interaction blueprint

The design source of truth for everything below the frozen hero, and for the
whole `/how-it-works` route. Phase 2A output: **design only, no implementation.**

One rule governs this document: **the repository is authoritative.** Every value
here was derived from the live demo engine and the domain layer, not from a
prompt, a mock, or the offline frontend fixture. Where an earlier brief and the
code disagreed, the code won and the design was rewritten around it.

| | |
|---|---|
| Frozen hero | `e0e9213` — *feat: ship responsive Branchpoint landing hero* |
| Branch | `feature/branchpoint-landing` |
| Landing sections | 9, below the hero |
| Protocol stages | 9 (not 10 — see §9) |
| Build gates | 9 (2B → 3D) |
| Verified against | `backend/app/infrastructure/demo`, `backend/app/domain` on 2026-08-27 |

---

## 1. Canonical source paths

Facts on the marketing site must be traceable. This is the hierarchy, highest
authority first.

| Rank | Source | Path | Status |
|---|---|---|---|
| 1 | **Live demo engine** — every metric is a pure function of state | `backend/app/infrastructure/demo/metrics.py`<br>`backend/app/infrastructure/demo/workload.py` | AUTHORITATIVE |
| 2 | **Scenario snapshot** — the starting reality | `backend/app/infrastructure/demo/scenarios/checkout_regression.json` | AUTHORITATIVE |
| 3 | **Domain rules** — what the states *mean* | `backend/app/domain/worlds/verdicts.py`<br>`backend/app/domain/evidence/models.py`<br>`backend/app/domain/comparison/models.py`<br>`backend/app/domain/actions/models.py`<br>`backend/app/domain/events.py` | AUTHORITATIVE |
| 4 | **Frontend fixture** — offline `/demo/hero` only | `frontend/src/data/heroRun.ts` | ILLUSTRATIVE — do not quote |

### Why the frontend fixture is not the source

`heroRun.ts` opens by declaring itself:

> *"**Not part of the live path.** Since Phase 4.2 the app renders runs adapted
> from the real backend; this module exists so tests and the offline demo route
> have a complete, stable scenario to render. It is reachable only through
> `/demo/hero`, and `Run.source` marks anything built from it as `"fixture"` so
> a live run can never quietly inherit a value from here."*

Its α and γ numbers are hand-written and disagree with what the engine computes.
A marketing site describing the real product must quote the engine.

### Per-fact source index

| Fact | Constant / function | File |
|---|---|---|
| Baseline error rate 41.3% | `REGRESSION_BASE_ERROR_RATE = 0.413` | `demo/metrics.py` |
| Baseline p95 4800 ms | `REGRESSION_BASE_P95_MS = 4800.0` | `demo/metrics.py` |
| Affected users 8000 | `round(DAILY_CHECKOUT_ATTEMPTS × rate)`, `DAILY_CHECKOUT_ATTEMPTS = 19_370` | `demo/metrics.py` |
| Daily cost $450 | `replicas × cost_per_replica_per_day` = `4 × 112.5` | `demo/metrics.py`, `scenarios/checkout_regression.json` |
| α error 1.8% | `BYPASSED_ERROR_RATE_BY_VERSION["v2.40"] = 0.018` | `demo/metrics.py` |
| α p95 190 ms | `BYPASSED_P95_MS_BY_VERSION["v2.40"] = 190.0` | `demo/metrics.py` |
| β error 1.4% | `BYPASSED_ERROR_RATE_LEGACY_FLAG_OFF = 0.014` | `demo/metrics.py` |
| β p95 320 ms | `BYPASSED_P95_MS_LEGACY_FLAG_OFF = 320.0` | `demo/metrics.py` |
| γ error floor 7.0% | `ERROR_RATE_FLOOR = 0.07` | `demo/metrics.py` |
| γ latency floor 960 ms | `LATENCY_FLOOR_MS = 960.0` | `demo/metrics.py` |
| γ cost delta +$900/day | `daily_cost_delta_usd(before, after)` | `demo/metrics.py` |
| Regression activation rule | `is_regression_active()` — flag enabled **and** version `v2.41` | `demo/metrics.py` |
| The witness order | `_select_payment_revision_order()` → lowest-id v2.41 order with a revision | `demo/workload.py` |
| Schema failure | `order_deserialization_or_compatibility()` | `demo/workload.py` |
| Payment failure | `payment_retry()` | `demo/workload.py` |
| SLO thresholds | `RECOVERY_SLO_ERROR_RATE_THRESHOLD = 0.02`, `RECOVERY_SLO_P95_MS_THRESHOLD = 500.0` | `demo/metrics.py` |
| Veto decision order | `derive_verdict()` | `domain/worlds/verdicts.py` |
| Disqualifying kinds | `DISQUALIFYING_EVIDENCE_KINDS = {INVARIANT, DATA_INTEGRITY}` | `domain/worlds/verdicts.py` |
| Authority bit | `Evidence.machine_verifiable`, `Evidence.disqualifies` | `domain/evidence/models.py` |
| Comparator axes | `WorldRanking` fields | `domain/comparison/models.py` |
| Rejection reasons | `RejectionReason` enum | `domain/comparison/models.py` |
| Fingerprint | `sha256(canonical JSON).hexdigest()` | `domain/actions/models.py:77-85` |
| Run lifecycle | `RunStatus` state machine | `domain/runs/lifecycle.py`, `docs/ARCHITECTURE.md` §1 |
| Event vocabulary | `RunEventType` | `domain/events.py` |

---

## 2. Discrepancy table

Corrections discovered in Phase 2A. **These must not regress.**

| Item | Earlier prompt §7 | Frontend fixture | Live engine — **USE THIS** | Derivation |
|---|---|---|---|---|
| α checkout error | — | 2.1% | **1.8%** | `BYPASSED_ERROR_RATE_BY_VERSION["v2.40"] = 0.018` |
| α p95 | — | 610 ms | **190 ms** | `BYPASSED_P95_MS_BY_VERSION["v2.40"] = 190.0` |
| β checkout error | ~1.4% | 1.4% | **1.4%** | agree — `…LEGACY_FLAG_OFF = 0.014` |
| β p95 | ~320 ms | 320 ms | **320 ms** | agree — `…LEGACY_FLAG_OFF = 320.0` |
| γ checkout error | "partial improvement" | 16.2% | **7.0%** | `max(0.07, 0.413 − 0.043×8)` → **floor binds** |
| γ p95 | — | 1.9 s | **960 ms** | `max(960, 4800 − 480×8)` → **floor binds** |
| γ cost delta | "higher cost" | 1840 | **+$900/day** | `(12 − 4) × $112.50` |
| Affected users | 8000 | 12.4k | **8000** | `round(19_370 × 0.413)` — **prompt was right** |
| Daily infra cost | $450 | — | **$450/day** | `4 × $112.50` — **prompt was right** |
| Protocol stages | 10 (incl. REPLAY) | 9 | **9** | REPLAY is a step inside ATTACK, not a run state |
| Action fingerprint | `"sha256 8a91…c410"` | 16 hex chars | **SHA-256, 64 hex** | `actions/models.py:84` |
| α veto cause | "schema/payment compatibility failure" | same | **confirmed** | two `CRITICAL` checks on `order_1003` |
| γ verdict | SURVIVED, NOT SELECTED | same | **confirmed** | `MEDIUM` severity is not disqualifying |

### The two corrections that changed the design

**γ does not "partially improve" — it hits a floor.** `ERROR_RATE_FLOOR = 0.07`
exists because *the root cause is still deployed and still enabled.* Scaling
eases queueing pressure and can never remove the bug. This is a far stronger
section than "16.2%": **you cannot scale your way out of code that is still
running.**

**α is the fastest world in the run.** At 190 ms it beats the world that wins
(320 ms), and its 1.8% error rate is inside the 2% recovery SLO. Every headline
number says ship it. It is vetoed anyway. The landing page's opening argument is
now *literally true of the data*, not a rhetorical flourish.

---

## 3. The canonical incident

### Starting reality — `scenarios/checkout_regression.json`

| Fact | Value | Fact | Value |
|---|---|---|---|
| pricing-service | `v2.41` (prev `v2.40`) | Checkout error | 41.3% |
| PRICING_V2 | `true` | p95 latency | 4800 ms |
| Replicas | 4 @ $112.50/day | Pricing timeouts | 35% |
| Daily infra cost | $450 | Affected users | 8000 / 19 370 |
| Orders schema | 41 | Pricing CPU | 0.75 |
| DB latency | 12.0 ms | Checkout CPU | 0.42 |

The regression is v2.41's own code. It runs **only** when v2.41 is deployed
*and* the flag routes traffic through it — `is_regression_active()`.

### The five orders

| `order_id` | Created under | schema | `payment_revision` | Role |
|---|---|---|---|---|
| `order_1001` | v2.40 | 40 | `null` | safe under either version |
| `order_1002` | v2.40 | 40 | `null` | safe under either version |
| **`order_1003`** | v2.41 | 41 | **`pr_7f3a91`** | **THE WITNESS** — lowest id, selected by the check |
| `order_1004` | v2.41 | 41 | `pr_2b88c4` | same exposure |
| `order_1005` | v2.41 | 41 | `pr_9e10aa` | same exposure, still `PENDING` |

`_select_payment_revision_order()` deterministically picks the lowest-id v2.41
order carrying a revision — always **`order_1003`**. The entire veto rests on one
nameable record. Every section needing a concrete artifact should use
`order_1003` / `pr_7f3a91`: stable, real, repeatable.

### The three worlds, exactly

| | α — rollback | β — flag off | γ — scale |
|---|---|---|---|
| Action | `version v2.41 → v2.40` | `PRICING_V2 true → false` | `replicas 4 → 12` |
| Regression active? | no (version changed) | no (flag off) | **YES** — both still true |
| Checkout error | **1.8%** | **1.4%** | 7.0% *(floor)* |
| p95 | **190 ms** ← fastest | 320 ms | 960 ms *(floor)* |
| Affected users | 349 | 271 | 1356 |
| Cost delta | $0 | $0 | +$900/day |
| `healthy_checkout` | PASS | PASS | **FAIL** *(MEDIUM)* |
| `recovery_slo` | PASS | PASS | **FAIL** *(MEDIUM)* |
| `data_integrity` | PASS | PASS | PASS |
| `order_deserialization` | **FAIL — CRITICAL** | PASS | PASS |
| `payment_retry` | **FAIL — CRITICAL** | PASS | PASS |
| Verdict | **VETOED** | SURVIVED | SURVIVED |
| Selection | disqualified before ranking | **RECOMMENDED** | not selected |

### The two failing checks, verbatim from the engine

```
order_deserialization_or_compatibility        FAIL   CRITICAL   artifact order:order_1003
  expected   pricing-service v2.40 deserializes order order_1003 (schema 41)
  observed   pricing-service v2.40 supports orders schema up to 40; order requires schema 41
  detail     order.payment_revision is unrepresentable to a deployment older than v2.41

payment_retry                                 FAIL   CRITICAL   artifact order:order_1003
  expected   retry idempotency key == 'order_1003:pr_7f3a91'
  observed   retry idempotency key == 'order_1003:legacy'
  detail     retry recomputed a legacy dedupe key that does not match the original charge,
             so the retry would be charged as a new payment
```

**The rollback that fixes checkout double-charges a customer.** Not "may cause
data issues" — a specific order, a specific dedupe key, a second charge. That is
what a reproduced counterexample buys, and it is why headline metrics are not
allowed to decide.

---

## 4. The authority model

One spine runs through both pages. Every interaction must place itself on it,
and the site must never blur the lower bands into the top one.

| Band | Who | May do | May never do | Colour |
|---|---|---|---|---|
| **EXPLORATORY** | DOPPELGÄNGER, its subagent, Daytona sandbox, all model prose | Investigate, run code in isolation, form hypotheses, submit a typed `CounterexampleSpec` | Veto. Set a threshold. Mark anything `REPRODUCED`. Contribute authority. | `--dim #8B949E` |
| **DETERMINISTIC** | BRANCHPOINT replay, world executor, comparator | Produce `machine_verifiable=True` evidence, veto, rank, recommend | Grant permission. Change reality. | `--blue #58A6FF` |
| **PERMISSION** | The human | Approve exactly one bound action, or reject | Invent an action. Override a veto. Approve a changed action. | `--violet #BC8CFF` |

### The one bit that carries authority

```python
Evidence.machine_verifiable          # the ONLY authority bit; never inferred from `source`

@property
def disqualifies(self) -> bool:
    return self.machine_verifiable and self.is_failing

# and a veto needs BOTH halves:
counterexample.status is REPRODUCED   AND   any(evidence.disqualifies)
```

A validator refuses machine-verifiable evidence with no pass/fail outcome — *a
check that proves nothing cannot claim to.* An adversary asserting `REPRODUCED`
with only sandbox output behind it is **recorded and ignored**, never rejected —
so an untrusted adversary cannot halt a run by making claims either.

### Veto is safety. Losing is quality. Keep them apart.

γ fails two checks and still **SURVIVED**, because those failures are severity
`MEDIUM`, kind `TEST_RESULT` — not in `{INVARIANT, DATA_INTEGRITY}` and not
`CRITICAL`. α fails two checks and is **VETOED** because both are `CRITICAL`.

The site must show this: **a world can miss the goal entirely and still be
safe.** Relative quality is a comparator concern and is deliberately
unrepresentable in the invariant registry — nothing there can reference a second
world.

### Design consequence

**Green does not mean winner.** γ is green (`SURVIVED`) and still loses. Any
design that implies green = selected contradicts the comparison section.

---

## 5. Cofounder — interaction principles extracted

Measured live at 1440×900 and 390×844. Principles only; no artwork, copy, layout
or code is borrowed.

| Measurement | Finding | Principle for BRANCHPOINT |
|---|---|---|
| page height | 9287 px ≈ **10.3 viewports**, 10 top-level blocks | A long page is fine. Budget ~10–14 viewports, not 25. |
| `position:sticky` count | **1** — a 44 px utility pill, 27× travel | They barely use sticky. Reserve it for the 2 sections that *are* a sequence. |
| largest section | 2635 px, 419 words, **13 buttons** | Concentrate interaction. One dense operable section beats five shallow ones. |
| second interactive | 1222 px, **11 buttons** | Two selector-driven sections is the right count. |
| words / section | 12 → 419, median ≈ 75 | Most sections carry one thesis + a label set. Prose lives in few places. |
| video | **1**, hero only | Matches our frozen hero exactly. Nothing below the fold gets video. |
| canvas | **0** — SVG throughout (58 in one block) | SVG + CSS suffices. No canvas, no WebGL. |
| mobile height | 12 295 px ≈ **14.6 vh**, 0 horizontal scrollers | Mobile grows *taller*. Do not convert sections into swipe carousels. |

### Qualitative principles worth taking

- **Explanation left, live artifact right.** The right pane shows a real
  interface with real state labels — including *"Agent requires approval"*. They
  sell the product by showing the product's own states, not illustrations of
  them. This is exactly our advantage: our states are `VETOED` / `SURVIVED` /
  `AWAITING APPROVAL`.
- **A numbered spine.** Monospace markers (`1.1`, `2.0 — GROW`) run the page's
  length and make a long scroll feel like a structured document.
- **Indexed accordions as the workhorse.** Cheap, keyboard-native, no scroll
  maths — one section can hold four ideas without becoming four sections.
- **Two-tone headlines.** Full-strength text for the subject, muted for the
  qualifier. Free hierarchy with no extra type sizes.
- **Sticky is a utility, not a stage.** Their one sticky element is a persistent
  action, not a pinned scene.
- **Whitespace as pacing.** Large empty gaps between dense moments.

### Where we deliberately diverge

Cofounder is a bright, optimistic, warm-grey product. BRANCHPOINT is a dark
operations console at night. We take their *rhythm and restraint* and none of
their *tone*. Our sections darken toward the adversarial middle and resolve to
violet at the checkpoint — a tonal arc they do not have and do not need.

---

## 6. Inherited constraints

### Hard constraints

- `.bp-marketing` is the scroll container — `html`/`body` stay
  `overflow: hidden` for Mission Control. **Every scroll-linked effect must
  observe this element, not the window.**
- Type scale exists: `.bp-display`, `.bp-lead`, `.bp-eyebrow`, `.bp-cta`. Reuse;
  do not add a second scale.
- `--bp-gutter: clamp(20px, 5vw, 96px)`, `--bp-header-h: 64px`,
  `--bp-void: #05070a`.
- The hero owns `--bp-px` scene-space maths. Nothing below the hero should use
  it — that unit exists to weld overlays to footage.
- Mobile breakpoint is `max-width: 639px`, chosen from layout not device class.
  Match it.

### Palette — already frozen

| Token | Hex | Meaning |
|---|---|---|
| void | `#05070A` | landing ground |
| surface | `#0D1117` | panels |
| raised | `#161B22` | chips, headers |
| blue | `#58A6FF` | running / deterministic |
| green | `#3FB950` | survived |
| red | `#F85149` | vetoed |
| violet | `#BC8CFF` | human gate |
| text | `#F0F3F6` / `#C9D1D9` | primary / body |
| dim | `#8B949E` | secondary, exploratory |

Semantic, not decorative. **Colour never carries meaning alone** — every state
also has a word and a shape.

### Transition out of the frozen hero

The hero ends on **HUMAN CHECKPOINT · AWAITING APPROVAL** baked into the
monitor, over near-black deck at the bottom of the frame. Section 01 must open on
that same near-black with no seam and no divider rule — the page should read as
continuing down the deck, not starting a new document.

The current `LandingPage.tsx` placeholder (`<div className="h-[70vh]
bg-[#07090d]" aria-hidden="true" />`) is where 01 lands; it is **replaced**, not
appended to.

---

## 7. Landing page — narrative

The hero makes a promise: *agents get branches before they get permissions.* The
page below has one job — **make that promise survive contact with a sceptic.**

The argument runs in nine moves:

1. **The trap.** The obvious fix looks correct on every number you would normally check.
2. **Manyworlds.** So don't check numbers — rehearse the action somewhere reality isn't.
3. **Three worlds.** Here is what each one actually did.
4. **The attack.** An adversary guesses; only a replay can prove. Authority transfers on screen.
5. **Comparison.** β wins by arithmetic, and there is no confidence score anywhere.
6. **The checkpoint.** A recommendation is not permission. A human binds one exact action.
7. **Commit & verify.** Reality changes once, then is re-read independently.
8. **Architecture.** Who holds which authority, and who explicitly does not.
9. **Close.** Rehearse before reality.

### Copy discipline

Durable claims in headlines; exact numbers only inside evidence surfaces.

> *"Compatibility failure reproduced · VETOED"* is headline copy and stays true
> forever. *"retry idempotency key == 'order_1003:legacy'"* is evidence copy and
> lives in an inspector where precision earns its keep.

This keeps the page from going stale if a threshold moves.

---

## 8. Landing section blueprint

### 01 — THE TRAP

| | |
|---|---|
| **Thesis** | **"Every number said ship it."** Sub: the rollback recovered checkout to 1.8% and 190 ms — the fastest result in the run. BRANCHPOINT vetoed it anyway. |
| **Desktop** | Full-bleed dark. A row of four metric plates (error, p95, users, cost) reading as a healthy dashboard. One control: `HEADLINE VIEW` ⇄ `EVIDENCE VIEW`. Toggling flips the same four plates to the two CRITICAL checks — same geometry, opposite conclusion. |
| **Scroll** | No sticky. |
| **Motion** | Plates cross-fade + 6 px rise, 240 ms ease-out, 40 ms stagger. Auto-advances once on first view (IntersectionObserver), then user-driven. |
| **Data** | `1.8% · 190ms · 349 users · $0` → `order_1003 schema 41 vs 40` → `key 'order_1003:legacy'` |
| **Authority** | DETERMINISTIC |
| **Tech** | React state + CSS. No SVG. |
| **Mobile** | Plates stack 2×2. Toggle becomes a full-width segmented control, 44 px tall. |
| **Reduced motion** | No auto-advance, no stagger — **starts on EVIDENCE VIEW**, the conclusion. |
| **A11y** | Segmented control is a real `radiogroup`; arrow keys switch. |

### 02 — MANYWORLDS

| | |
|---|---|
| **Thesis** | **"Fork reality. Not production."** One line per beat, nothing more. |
| **Desktop** | Sticky scene, 4 beats. Centre: an SVG topology. Beat 1 — one node, *production twin*. Beat 2 — splits into α/β/γ along drawn branches. Beat 3 — three isolated frames, each running its own action. Beat 4 — outcomes settle onto each node. Left rail: beat label + count. |
| **Scroll** | **Sticky, ~300 vh.** IntersectionObserver on 4 sentinel divs → discrete beat index. *No scroll-jacking, no rAF, no scrubbing.* |
| **Motion** | Branch paths draw via `stroke-dashoffset` transition, 420 ms. |
| **Data** | 3 worlds, isolated snapshots; action per world; verdict chip on settle. |
| **Authority** | DETERMINISTIC |
| **Tech** | Inline SVG + CSS transitions + IO. ~140 lines. |
| **Mobile** | **Sticky dropped.** Becomes 4 stacked static frames, each with its own caption. Same SVG, no pinning. |
| **Reduced motion** | Branches render already-drawn. |
| **A11y** | Decorative SVG `aria-hidden`; captions are the real content in an `<ol>`. |

### 03 — WORLD EXPLORER

| | |
|---|---|
| **Thesis** | **"Three candidates. One survives selection."** |
| **Desktop** | Real tablist (α / β / γ) over a two-pane body: left = action + outcome plates; right = the world's *actual* evidence list, deliberately different lengths per world (α 3 · β 6 · γ 4). Verdict chip pinned top-right of the pane. |
| **Scroll** | No sticky. |
| **Motion** | Pane cross-fades 180 ms. Tab indicator slides via `transform`. |
| **Data** | Full per-world truth from §3; evidence rows: claim · outcome · observed · expected. |
| **Authority** | DETERMINISTIC, with EXPLORATORY rows explicitly marked. |
| **Tech** | React tabs, roving tabindex. Data from one typed module. |
| **Mobile** | Tabs become a horizontally scrollable tablist (3 items fit at 390 px with 44 px targets). One pane at a time. Evidence list collapses to claim + outcome; row tap expands. |
| **Reduced motion** | Instant pane swap. |
| **A11y** | `role="tablist"`, roving tabindex, `aria-selected`, arrow-key cycling. |

> **Do not make the three worlds symmetrical.** They have 3, 6 and 4 evidence
> rows. Forcing a uniform grid destroys the most honest thing on the page.

### 04 — THE ATTACK

| | |
|---|---|
| **Thesis** | **"The candidate survived. Now try to break it."** Then: **"A guess is not a finding."** |
| **Desktop** | Darkest section on the page (`#05070A` → pure black vignette). Sticky, 3 beats. **Beat 1**: DOPPELGÄNGER hypothesis card, stamped `EXPLORATORY · NO AUTHORITY`, sandbox exec counter ticking. **Beat 2**: the typed `CounterexampleSpec` hands off to BRANCHPOINT — the card physically crosses a labelled rule down the middle of the section. **Beat 3**: replay output lands in blue, `REPRODUCED`, then `VETOED`. |
| **Scroll** | **Sticky, ~220 vh.** Same IO-sentinel pattern. |
| **Motion** | The crossing is a `transform: translateY` on one card, 500 ms ease-in-out. The card's border animates dim → blue as it crosses. |
| **Data** | Real hypothesis text; `3 exec calls, 1 hypothesis`; then both CRITICAL checks verbatim. |
| **Authority** | EXPLORATORY → DETERMINISTIC. **The transfer *is* the section.** |
| **Tech** | SVG rule + CSS transforms + IO. |
| **Mobile** | **Sticky dropped.** Three stacked cards; the middle carries the authority rule as a horizontal divider with its label centred on it. |
| **Reduced motion** | Card appears already across the line, blue. |
| **A11y** | Each beat is an `<li>`. The authority label is **real text**, not an SVG path. Must be legible without colour. |

### 05 — DETERMINISTIC COMPARISON

| | |
|---|---|
| **Thesis** | **"No score. Arithmetic."** Sub: α was removed before ranking began. |
| **Desktop** | A real comparison matrix, worlds as columns, the comparator's *actual* axes as rows: `goal_achieved`, `goal_attainment`, `invariants_preserved`, `regressions_detected`, `blast_radius`, `reversible`, `cost_delta`. α's column struck through with `ADVERSARIAL_VETO`. Row hover/focus reveals a one-line explanation of the axis. |
| **Scroll** | No sticky. |
| **Motion** | Rows reveal on entry, 30 ms stagger. α's strike-through draws left→right, 300 ms. |
| **Data** | Real `RejectionReason` enum; real `WorldRanking` fields. |
| **Authority** | DETERMINISTIC |
| **Tech** | Semantic `<table>`. CSS only. |
| **Mobile** | Matrix **transposes**: pick a world with a segmented control, axes list vertically. Never a 3-column table at 390 px. |
| **Reduced motion** | No draw animation; strike-through static. |
| **A11y** | Stays a `<table>` with `<caption>` and `scope` attributes in **both** orientations. Row explanations reachable by focus, never hover-only. |

> `ComparisonResult` can also be **tied** — `recommended_world_id` is `None` when
> the best worlds are deterministically tied. *"BRANCHPOINT never invents a
> winner and never breaks a tie at random."* Worth one line of copy.

### 06 — HUMAN CHECKPOINT

| | |
|---|---|
| **Thesis** | **"A recommendation is not permission."** |
| **Desktop** | Centred approval card on violet-tinged ground: world β, the exact action, the truncated SHA-256, and the five real binding checks. Two buttons — `REJECT` / `APPROVE EXACT ACTION`. Below, one control: *"Change the action"*. Pressing it mutates `PRICING_V2` → `CHECKOUT_V2`; the fingerprint visibly recomputes and the card stamps `APPROVAL INVALIDATED`, both buttons disabling. |
| **Scroll** | No sticky. |
| **Motion** | Fingerprint characters re-roll per-glyph, 24 ms stagger — the one flourish on the page. |
| **Data** | `action_b8e2 · SET_FEATURE_FLAG`, `PRICING_V2 true → false`, sha256 truncated 12+4. |
| **Authority** | PERMISSION |
| **Tech** | Local `useState` only. **Never calls the API.** Two precomputed hashes shipped as constants. |
| **Mobile** | Card full-width, buttons stack at 48 px tall. Fingerprint wraps to two mono lines. |
| **Reduced motion** | Hash swaps with no per-glyph roll. |
| **A11y** | Real `<button>`s. Invalidated state uses `aria-disabled` + visible text, not colour alone. |

> **Security note for implementation:** this is a local visual fixture. It must
> not import the approval client, must not construct a request, and a test should
> assert no `fetch` is issued from this section.

### 07 — COMMIT & VERIFY

| | |
|---|---|
| **Thesis** | **"Approval changes permission. Verification proves reality."** |
| **Desktop** | Two stacked bands. Upper: reality mutating — `PRICING_V2 true → false` on a single line, with the one-time capability shown being issued and consumed. Lower: an *independent* re-read, three expected/actual pairs resolving to ✓ one at a time. |
| **Scroll** | No sticky. |
| **Motion** | A 3-step timed sequence (900 ms apart) started by IntersectionObserver, run once. |
| **Data** | `error 1.4% == 1.4% ✓`, `p95 320ms == 320ms ✓`, `schema 41 unchanged ✓`. |
| **Authority** | DETERMINISTIC |
| **Tech** | `setTimeout` chain in one effect, cleaned up on unmount. |
| **Mobile** | Bands stack. Expected/actual pairs become two-line rows. |
| **Reduced motion** | Sequence resolved instantly, all ✓. |
| **A11y** | Result region is **not** `aria-live` — static content that animates. |

### 08 — AUTHORITY ARCHITECTURE

| | |
|---|---|
| **Thesis** | **"Who is allowed to be sure."** |
| **Desktop** | A five-node SVG topology (TrueForge · BRANCHPOINT · Daytona · Human · Reality). Hover *or* focus any node → a panel states three things: what it does, what authority it holds, **what authority it does not hold**. The negative line is the point of the section. |
| **Scroll** | No sticky. |
| **Motion** | Node highlight 160 ms. Panel content swaps with no layout shift (fixed `min-height`). |
| **Data** | 17 MCP tools · 13 read-only · 4 destructive; sandbox: DOPPELGÄNGER only; 4 independent commit gates. |
| **Authority** | all three bands, labelled. |
| **Tech** | Inline SVG, `<button>` hotspots. Keyboard-first. |
| **Mobile** | Topology becomes a vertical tap-through list of the 5 layers; tapping expands its three lines in place. |
| **Reduced motion** | No transitions. |
| **A11y** | **Hover is never the only path** — every node is a focusable `<button>` with the same panel. |

Conceptual topology:

```
                TRUEFORGE
        planning · agents · MCP · sessions
                    │
                    ▼
               BRANCHPOINT
        plan → fork → replay → compare
             EVIDENCE AUTHORITY
                    │
            ┌───────┴───────┐
            ▼               ▼
      DAYTONA SANDBOX    HUMAN
     exploratory only   APPROVAL
            │               │
            └───────┬───────┘
                    ▼
                 COMMIT
                    ▼
                 VERIFY
```

### 09 — CLOSE

| | |
|---|---|
| **Thesis** | **"Rehearse before reality."** |
| **Desktop** | Quiet. Returns to the hero's near-black, no artwork, no repeat of the hero headline. A single hairline branch mark echoing the fork from 02, at 20% opacity. Primary `SEE LIVE DEMO` → `/runs`. Secondary `HOW IT WORKS` → `/how-it-works`. |
| **Scroll / motion** | None beyond a fade-in. |
| **Mobile** | Stacks. CTAs full-width. |

---

## 9. Scroll map

Derived from the interactions above, not chosen first. **Two sticky regions
total** — everything else is ordinary flow, following Cofounder's restraint.

```
DESKTOP 1440×900                                              cumulative
┌──────────────────────────────────────────────────────────┐
│ HERO            100 dvh   FROZEN — do not touch          │    1.0
├──────────────────────────────────────────────────────────┤
│ 01 THE TRAP      ~90 vh   flow · toggle                  │    1.9
│ 02 MANYWORLDS   ~300 vh   ██ STICKY ██ 4 beats × 75 vh   │    4.9
│ 03 EXPLORER     ~110 vh   flow · tabs                    │    6.0
│ 04 THE ATTACK   ~220 vh   ██ STICKY ██ 3 beats × 73 vh   │    8.2
│ 05 COMPARISON   ~110 vh   flow · matrix                  │    9.3
│ 06 CHECKPOINT   ~100 vh   flow · fingerprint demo        │   10.3
│ 07 COMMIT+VER   ~120 vh   flow · timed sequence          │   11.5
│ 08 ARCHITECTURE ~110 vh   flow · hover/focus             │   12.6
│ 09 CLOSE         ~80 vh   flow · static                  │   13.4
└──────────────────────────────────────────────────────────┘
                                        TOTAL ≈ 13.4 viewports

sticky enter/exit
  02  begins when its top hits header-h; releases after beat 4 sentinel
  04  same pattern; released before COMPARISON so two pins never meet

MOBILE 390×844 — both sticky regions become static stacks
  total ≈ 15–16 viewports (matches Cofounder's 14.6 vh mobile growth)
```

**Rhythm check.** The two long sticky sections sit at positions 2 and 4 — never
adjacent, each followed by a short flow section that lets the reader breathe.
Interaction type never repeats twice in a row:

> toggle → sticky scene → tabs → sticky reveal → matrix → button demo → timed
> sequence → hover map → static

---

## 10. Desktop wireframes

### 01 · THE TRAP — 1440×900, EVIDENCE VIEW active

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                                                                                │
│   EVERY NUMBER SAID SHIP IT.                                                   │
│   The rollback recovered checkout to 1.8% and 190 ms — the fastest result      │
│   in the run. Branchpoint vetoed it anyway.                                    │
│                                                                                │
│        ┌─ HEADLINE VIEW ─┬─ ▓ EVIDENCE VIEW ▓ ─┐                              │
│        └─────────────────┴─────────────────────┘                              │
│                                                                                │
│   ┌─────────────────────────┐  ┌─────────────────────────┐                    │
│   │ ■ order_deserialization │  │ ■ payment_retry         │                    │
│   │   CRITICAL       FAIL   │  │   CRITICAL       FAIL   │                    │
│   │ ───────────────────────  │  │ ───────────────────────  │                   │
│   │ expected  v2.40 reads    │  │ expected  key ==         │                   │
│   │   order_1003 schema 41   │  │   'order_1003:pr_7f3a91' │                   │
│   │ observed  supports ≤ 40  │  │ observed  key ==         │                   │
│   │                          │  │   'order_1003:legacy'    │                   │
│   └─────────────────────────┘  └─────────────────────────┘                    │
│                                                                                │
│   The retry would be charged as a new payment.                                 │
└────────────────────────────────────────────────────────────────────────────────┘
```

### 02 · MANYWORLDS — sticky, beat 3 of 4

```
┌────────────────────────────────────────────────────────────────────────────────┐
│  FORK REALITY.                                                                 │
│  NOT PRODUCTION.                                                               │
│                                                                                │
│  ┌ BEAT ─────────┐        ┌───────────── isolated ─────────────┐              │
│  │ 01 twin       │        │  ╭─────────╮  α  SET_DEPLOYMENT    │              │
│  │ 02 fork       │        │  │ α  ▓▓▓  │     v2.41 → v2.40     │              │
│  │ ▶ 03 execute  │   ╱────┼─▶╰─────────╯     running…          │              │
│  │ 04 outcomes   │  ╱     │                                    │              │
│  └───────────────┘ ╱      │  ╭─────────╮  β  SET_FEATURE_FLAG  │              │
│                   ╱       │  │ β  ▓▓▓  │     PRICING_V2 → false│              │
│   ╭──────────╮   ╱────────┼─▶╰─────────╯     running…          │              │
│   │PRODUCTION│ ╱          │                                    │              │
│   │   TWIN   │╱           │  ╭─────────╮  γ  SCALE_SERVICE     │              │
│   │  v2.41   │╲           │  │ γ  ▓▓▓  │     replicas 4 → 12   │              │
│   ╰──────────╯ ╲──────────┼─▶╰─────────╯     running…          │              │
│                           └────────────────────────────────────┘              │
│   nothing here can reach reality                                               │
└────────────────────────────────────────────────────────────────────────────────┘
```

### 04 · THE ATTACK — sticky, beat 2 of 3, the crossing

```
┌────────────────────────────────────────────────────────────────────────────────┐
│  THE CANDIDATE SURVIVED. NOW TRY TO BREAK IT.                                  │
│                                                                                │
│   ┌──────────────────────────────────────────┐                                │
│   │ DOPPELGÄNGER · sandbox sbx_4a19c72e      │   exec calls  3               │
│   │ "Orders created under schema 41 may not  │                                │
│   │  deserialize under v2.40."               │                                │
│   │                        ░ EXPLORATORY ░   │  ← border dim, card descending │
│   └──────────────────────────────────────────┘                                │
│ ═══════════════ CounterexampleSpec · typed · validated ══════════════════════  │
│         nothing above this line may conclude anything                          │
│                                                                                │
│   ┌ ── ── ── ── ── ── ── ── ── ── ── ── ── ─┐                                 │
│   │ BRANCHPOINT REPLAY  ·  world snapshot   │   (empty until beat 3)          │
│   └ ── ── ── ── ── ── ── ── ── ── ── ── ── ─┘                                 │
└────────────────────────────────────────────────────────────────────────────────┘
```

### 05 · COMPARISON — α struck out before ranking

```
┌────────────────────────────────────────────────────────────────────────────────┐
│  NO SCORE. ARITHMETIC.                                                         │
│                                                                                │
│                        ╱α ROLLBACK╱      β FLAG OFF       γ SCALE             │
│                        ╱ADVERSARIAL╱                                          │
│                        ╱  _VETO   ╱                                           │
│  goal_achieved         ╱  true    ╱      true             false               │
│  goal_attainment       ╱  0.94    ╱      0.97             0.58                │
│  invariants_preserved  ╱  false   ╱      true             true                │
│  regressions           ╱   2      ╱       0                0                  │
│  blast_radius          ╱   3      ╱       1                2                  │
│  reversible            ╱  true    ╱      true             true                │
│  cost_delta            ╱   $0     ╱       $0            +$900/day             │
│  ────────────────────────────────────────────────────────────────────         │
│  rank                    removed          1                2                  │
│                                      RECOMMENDED       not selected           │
│                                                                                │
│  A vetoed world is disqualified before ranking begins.                         │
└────────────────────────────────────────────────────────────────────────────────┘
```

### 06 · CHECKPOINT — after "Change the action" is pressed

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                    A RECOMMENDATION IS NOT PERMISSION.                         │
│                                                                                │
│         ┌──────────────────────────────────────────────────┐                  │
│         │  WORLD β          SET_FEATURE_FLAG               │                  │
│         │  ▲ CHECKOUT_V2      true → false                 │  ← mutated       │
│         │                                                  │                  │
│         │  ACTION FINGERPRINT                              │                  │
│         │  sha256  4f2c8ba90e17…d6b3     ← recomputed      │                  │
│         │                                                  │                  │
│         │  ✓ goal achieved                                 │                  │
│         │  ✓ all declared invariants passed                │                  │
│         │  ✓ no reproduced counterexamples                 │                  │
│         │  ✓ deterministic comparator recommendation       │                  │
│         │  ✗ action fingerprint bound                      │                  │
│         │                                                  │                  │
│         │        ▓▓▓  APPROVAL INVALIDATED  ▓▓▓            │                  │
│         │  [ REJECT ]          [ APPROVE ] ← disabled      │                  │
│         └──────────────────────────────────────────────────┘                  │
│                    ⟲ reset to the reviewed action                              │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## 11. Mobile wireframes — 390×844

### 03 · EXPLORER, α selected

```
┌──────────────────────────┐
│ ◀ ▓ α ▓ │  β  │  γ  ▶    │
│──────────────────────────│
│ ROLLBACK    ▓ VETOED ▓   │
│ v2.41 → v2.40            │
│                          │
│ error   1.8%   ▲ fastest │
│ p95     190ms            │
│ cost    $0               │
│                          │
│ EVIDENCE           3     │
│ ┌──────────────────────┐ │
│ │░ sandbox probe  INFO │ │
│ │  EXPLORATORY       ▾ │ │
│ ├──────────────────────┤ │
│ │■ schema_compat  FAIL │ │
│ │  VERIFIED          ▾ │ │
│ ├──────────────────────┤ │
│ │■ payment_retry  FAIL │ │
│ │  VERIFIED          ▾ │ │
│ └──────────────────────┘ │
│ tap a row for observed / │
│ expected                 │
└──────────────────────────┘
```

### 04 · ATTACK, sticky dropped

```
┌──────────────────────────┐
│ THE CANDIDATE SURVIVED.  │
│ NOW TRY TO BREAK IT.     │
│                          │
│ ┌──────────────────────┐ │
│ │ DOPPELGÄNGER         │ │
│ │ "schema 41 may not   │ │
│ │  deserialize under   │ │
│ │  v2.40"              │ │
│ │  ░ EXPLORATORY ░     │ │
│ └──────────────────────┘ │
│                          │
│ ══ typed spec ══════════ │
│  nothing above may       │
│  conclude anything       │
│                          │
│ ┌──────────────────────┐ │
│ │ BRANCHPOINT REPLAY   │ │
│ │ schema_compat  FAIL  │ │
│ │ payment_retry  FAIL  │ │
│ │  ▓ REPRODUCED ▓      │ │
│ └──────────────────────┘ │
│      ▓ WORLD α VETOED ▓  │
└──────────────────────────┘
```

### HOW IT WORKS · mobile stage view

```
┌──────────────────────────────────────┐
│ ▓ 05 / 09   ATTACK                   │  ← sticky, 56 px, always visible
│   EXPLORATORY → DETERMINISTIC        │
├──────────────────────────────────────┤
│ run_dbfa98c87f06 · world α           │
│                                      │
│  ┌────────────────────────────────┐  │
│  │      [ stage visualisation ]   │  │
│  │   sandbox → hypothesis → spec  │  │
│  └────────────────────────────────┘  │
│                                      │
│ EVIDENCE                             │
│ ┌────────────────────────────────┐   │
│ │ ░ sandbox probe        INFO    │   │
│ │   machine_verifiable = false   │   │
│ └────────────────────────────────┘   │
│                                      │
│ AUTHORITY                            │
│ ┌────────────────────────────────┐   │
│ │ can  investigate, hypothesise  │   │
│ │ cannot  veto, set thresholds   │   │
│ └────────────────────────────────┘   │
│                                      │
│           ▼ REPLAY                   │
└──────────────────────────────────────┘
```

---

## 12. How It Works — narrative

**Landing sells the idea. How It Works proves the system.**

One run — `run_dbfa98c87f06` — advances through all nine stages and **never
resets**. The visitor should be able to trace causality from the first metric to
the final verification without the example changing under them.

### Correction: nine stages, not ten

An earlier brief listed REPLAY as a peer stage. The repository has no such run
state — `RunStatus` goes
`… EXECUTING_WORLDS → ADVERSARIAL_TESTING → COMPARING …`, and the canonical
stage list holds nine entries. Replay is a step *inside* each world's pipeline
(`execute → doppelgänger → replay`).

**Keep it that way — it is better storytelling.** REPLAY is where authority
transfers. Promoting it to a peer stage would flatten the exact distinction the
page exists to teach. Instead **ATTACK is the one stage with two acts**, and the
page slows down there.

### Desktop architecture

Three columns: sticky stage rail (left), scroll-advanced viewport (centre),
sticky evidence + authority inspector (right).

```
┌───────────────┬────────────────────────────────────────┬───────────────────────┐
│ ▪ 01 OBSERVE  │  run_dbfa98c87f06   ATTACK   world α   │ EVIDENCE              │
│ ▪ 02 PLAN     │                                        │ ┌───────────────────┐ │
│ ▪ 03 FORK     │   ┌──────────────────────────────────┐ │ │░ sandbox    INFO  │ │
│ ▪ 04 EXECUTE  │   │  DOPPELGÄNGER    sbx_4a19c72e    │ │ │  EXPLORATORY      │ │
│ ▶ 05 ATTACK   │   │  hypothesis submitted            │ │ ├───────────────────┤ │
│    ├ act 1    │   └──────────────┬───────────────────┘ │ │■ schema_compat    │ │
│    └ ▶ act 2  │   ════ typed spec ═══════════════════  │ │  FAIL  CRITICAL   │ │
│   06 COMPARE  │                  ▼                     │ │  VERIFIED         │ │
│   07 APPROVE  │   ┌──────────────────────────────────┐ │ ├───────────────────┤ │
│   08 COMMIT   │   │  BRANCHPOINT REPLAY              │ │ │■ payment_retry    │ │
│   09 VERIFY   │   │  against world α's own snapshot  │ │ │  FAIL  CRITICAL   │ │
│               │   │  order_1003  schema 41 vs 40     │ │ │  VERIFIED         │ │
│ ────────────  │   │  key 'order_1003:legacy'         │ │ └───────────────────┘ │
│ AUTHORITY     │   │        ▓ REPRODUCED ▓            │ │ AUTHORITY THIS STAGE  │
│ ░ exploratory │   └──────────────────────────────────┘ │ ░→■ transfers here    │
│ ■ determinist │                                        │ can veto: YES         │
│ ▲ permission  │            ▓ WORLD α VETOED ▓          │ (replay only)         │
└───────────────┴────────────────────────────────────────┴───────────────────────┘
  sticky rail          scroll-advanced viewport            sticky inspector
```

---

## 13. The nine canonical stages

| Stage | Viewport state | Evidence state | Authority | Transition out |
|---|---|---|---|---|
| **01 OBSERVE** | Reality plate: v2.41, flag on, 4 replicas, schema 41. Metrics burning red — 41.3%, 4.8 s, 8000 users. | Empty. *"No evidence yet."* | DETERMINISTIC snapshot | Objective appears: *error below 2% without losing order data.* |
| **02 PLAN** | Three candidate actions fan out from the objective. Planner badge: read-only, **sandbox off**, no subagents. | Still empty — a plan is not evidence. | EXPLORATORY — model proposes | *"Three candidates. No permission granted."* |
| **03 FORK** | One twin splits into three isolated snapshots. Isolation ring drawn around each. | Empty per world. | DETERMINISTIC | Worlds enter `PREPARING`. |
| **04 EXECUTE** | Each world applies its action and measures. Three outcome plates fill: 1.8/190 · 1.4/320 · 7.0/960. | Execution suite lands: `healthy_checkout`, `recovery_slo`, `data_integrity`. γ's two go amber. | DETERMINISTIC | γ already missed the goal — *and is not vetoed.* |
| **05 ATTACK** *(two acts)* | **Act 1** sandbox + hypothesis, dim. **Act 2** spec crosses the rule, replay runs, both CRITICAL checks fail. | Act 1 adds one `INFO` row, `machine_verifiable=false`. Act 2 adds two `VERIFIED FAIL` rows. | EXPLORATORY → DETERMINISTIC | `REPRODUCED` + disqualifying evidence → **VETOED** |
| **06 COMPARE** | α's column struck out with `ADVERSARIAL_VETO`. β and γ ranked on the real axes. | Comparison evidence ids attach. | DETERMINISTIC | β rank 1. *"A deterministic recommendation. Not permission."* |
| **07 APPROVE** | Binding card: run + world + action id + fingerprint. Five checks. The mutation demo lives here too. | Frozen — approval does not add evidence. | PERMISSION | Approved → one-time capability issued. |
| **08 COMMIT** | Four independent gates shown passing in order, then `PRICING_V2 true → false`. Capability consumed, greying out. | Commit result row. | PERMISSION → DETERMINISTIC | *"The mutation was issued. That is all a commit proves."* |
| **09 VERIFY** | Independent re-read. Expected vs actual, three ✓. Only now **SUCCEEDED**. | Verification evidence appended. | DETERMINISTIC | *"Approval changed permission. Verification proved reality."* |

### Stage continuity rule

The example never resets. Evidence **accumulates** across stages and is never
cleared — by stage 09 the inspector holds the full chain from the sandbox probe
to the verification result. A test in phase 3B should assert this.

### Mobile How It Works

The three-column instrument cannot survive 390 px. Instead: a **56 px sticky
header** carrying `05 / 09 · ATTACK` and the current authority band — so the
reader always knows stage, authority and run state — then visualisation, then
evidence, then authority, then a `▼ NEXT STAGE` affordance. One stage per
screenful, ordinary vertical scroll, **no pinning and no horizontal snap**.

---

## 14. Component architecture

### Landing

```
components/marketing/sections/
  TrapToggle.tsx
  ManyworldsStory.tsx      + ForkDiagram.tsx
  WorldExplorer.tsx        + EvidenceList.tsx
  AttackReplay.tsx         + AuthorityRule.tsx
  ComparisonMatrix.tsx
  ApprovalFingerprint.tsx
  CommitVerify.tsx
  AuthorityArchitecture.tsx
  ClosingCta.tsx
```

### Shared

```
components/marketing/
  StickyBeats.tsx      the ONE IntersectionObserver sentinel primitive
                       both sticky sections use. Written once, reviewed once.
  AuthorityChip.tsx    the three bands, one component
  VerdictChip.tsx
  MetricPlate.tsx
  SectionHeader.tsx
```

### How It Works

```
components/protocol/
  ProtocolShell.tsx
  ProtocolStageRail.tsx
  ProtocolViewport.tsx
  EvidencePanel.tsx
  AuthorityPanel.tsx
  stages/*.tsx
```

### Data — the one architectural rule

```
data/canonicalIncident.ts
```

**Not optional.** Nine sections and nine stages quote the same incident; if the
numbers live inline in components they will drift within a week.

Every field carries a comment naming its backend origin:

```ts
/** metrics.py BYPASSED_P95_MS_BY_VERSION["v2.40"] */
p95Ms: 190,
```

so a future reader can re-verify without re-deriving. This file is also the seam
where a later phase could swap fixture values for a real API read.

---

## 15. Implementation technologies

### Stack decisions

- **No animation library.** CSS transitions + a shared IntersectionObserver hook
  cover every effect specified.
- **No canvas, no WebGL.** Cofounder ships 58 SVGs and zero canvases in its
  densest block; our diagrams are simpler than that.
- **No new video.** The hero already carries ~11 MB. Below the fold is
  HTML/SVG/CSS only.
- **No scroll library.** Sticky positioning + sentinels. No GSAP ScrollTrigger,
  no Lenis, no scroll-jacking.
- **No `requestAnimationFrame`.** Nothing here needs per-frame state; the frozen
  hero already set this precedent.
- Icons: `lucide-react`, already a dependency.

### Performance budget

| Budget | Limit | Current |
|---|---|---|
| Added JS | ≤ 25 KB gzipped across all nine sections | bundle 100.8 KB gz |
| Added CSS | ≤ 10 KB gzipped | 7.8 KB gz |
| Added network requests below the fold | 0 | — |
| Animated properties | `transform` and `opacity` only | — |
| Animated elements per viewport | ≤ 2 | — |

Sticky sections must not trigger layout on scroll: fixed-height viewports,
content swapped by opacity.

### Accessibility contract

| Requirement | How it is met |
|---|---|
| Keyboard reachable | Every control is a real `<button>`, `<a>`, or ARIA tablist with roving tabindex. **No drag-only or hover-only controls anywhere in the design** — the architecture map and comparison rows are focusable buttons, not hover targets. |
| Visible focus | 2 px `--blue` ring at 2 px offset on every focusable. Never `outline:none` without replacement. |
| Reduced motion | Each section's fallback is specified in §8. Rule: **reduced motion always lands on the section's conclusion**, never its opening frame — a reader who cannot see the animation gets the answer, not an empty stage. |
| No scroll-jacking | Sticky + sentinels only. Native scroll speed is never intercepted. |
| Colour never alone | Every verdict pairs colour with a word (`VETOED`) and a shape (■ / ░ / ▲). Passes for deuteranopia and in greyscale. |
| Live regions | **None.** These animate on scroll; announcing them would interrupt a screen reader repeatedly. Follows the hero's established pattern — decorative motion is `aria-hidden`, and each section carries static semantic text stating its claim. |
| Touch targets | ≥ 44×44 px, 48 px for the approval buttons. |
| Contrast | `#C9D1D9` on `#0D1117` = 11.9:1. `#8B949E` on `#05070A` ≈ 6.4:1. Chip text on tinted grounds verified ≥ 4.5:1. |
| Structure | One `<h1>` (the hero). Sections are `<section>` with `aria-labelledby` → their `<h2>`. The protocol rail is a real `<ol>`. |

---

## 16. Implementation phases

| Phase | Scope | Model / effort | Files | Visual gate | Tests | Stop condition |
|---|---|---|---|---|---|---|
| **2B**<br>foundation | `canonicalIncident.ts` + `StickyBeats` + `AuthorityChip` + section 01 THE TRAP | Opus · high | `data/canonicalIncident.ts`, `marketing/*`, `sections/TrapToggle.tsx`, `LandingPage.tsx`, `marketing.css` | 1440×900, 390×844 — seam from hero invisible | data module matches backend constants; toggle a11y; reduced-motion lands on EVIDENCE | Section 01 reads correctly and the hero transition is seamless. **Do not start 02.** |
| **2C**<br>the set piece | 02 MANYWORLDS sticky scene | Opus · xhigh | `sections/ManyworldsStory.tsx`, `ForkDiagram.tsx`, css | 1440×900, 1280×800, 1024×768, 390×844 + scroll-through recording | beat index from sentinels; mobile renders 4 static frames; **no `window` scroll listener** | Four beats advance cleanly in both directions; no jank; sticky releases correctly. |
| **2D** | 03 WORLD EXPLORER | Sonnet · high | `sections/WorldExplorer.tsx`, `EvidenceList.tsx` | 1440×900, 390×844 | tablist keyboard cycling, `aria-selected`, per-world evidence counts 3/6/4 | All three worlds show their real, asymmetric evidence. |
| **2E**<br>the argument | 04 THE ATTACK | Opus · xhigh | `sections/AttackReplay.tsx`, `AuthorityRule.tsx` | 1440×900, 390×844 + greyscale check | authority label present in DOM as text; exploratory row is `machine_verifiable=false` | The transfer across the rule is legible **without colour**. |
| **2F** | 05 COMPARISON + 06 CHECKPOINT | Opus · high | `ComparisonMatrix.tsx`, `ApprovalFingerprint.tsx` | 1440×900, 390×844 | **assert no fetch is ever issued**; fingerprint invalidation flips checks and disables approve | Mutation demo works and provably touches no endpoint. |
| **2G** | 07 COMMIT+VERIFY, 08 ARCHITECTURE, 09 CLOSE | Sonnet · high | three `sections/*` | 1440×900, 390×844 | timers cleaned up on unmount; every arch node keyboard-reachable | Landing complete end to end. |
| **3A** | Protocol shell — rail, viewport, inspector, stage state machine, all 9 stages stubbed | Opus · xhigh | `protocol/*`, `HowItWorksPage.tsx` | 1440×900, 1280×800, 390×844 | stage advance; sticky header shows n/9 + authority; `<ol>` semantics | Shell navigates all nine stages with placeholder viewports. |
| **3B** | Stages 01–05 (OBSERVE → ATTACK, both acts) | Opus · xhigh | `protocol/stages/*` | 1440×900, 390×844 | evidence accumulates and never resets between stages | Run state is continuous from OBSERVE to VETOED. |
| **3C** | Stages 06–09 (COMPARE → VERIFY) | Sonnet · high | `protocol/stages/*` | 1440×900, 390×844 | four commit gates in order; verify is independent of commit | Full protocol readable start to finish. |
| **3D** | Responsive, a11y, performance QA across both pages | Opus · high | css + targeted fixes | 1440×900, 1366×768, 1280×800, 1024×768, 900×900, 768×900, 430×932, 393×852, 390×844 | full suite; axe pass; bundle within budget; reduced-motion & keyboard sweep | Both pages ship-ready. |

### Recommended first phase

**Start with 2B, and specifically with `canonicalIncident.ts` before any pixels.**

Three reasons: it is the single dependency of all eighteen remaining surfaces;
writing it forces the α/γ corrections to be locked into code where they cannot
regress; and it is the cheapest possible place to discover that a number is
wrong. Section 01 then proves the hero seam — the riskiest visual unknown — while
the work is still small enough to throw away.

---

## 17. Risks and visual traps

### Visual traps to avoid

- **Three symmetrical world cards.** The worlds are not symmetrical — 3, 6 and 4
  evidence rows. Forcing a grid destroys the most honest thing on the page.
- **Sticky everywhere.** Two sticky sections is the budget. A third makes the
  page feel like a template.
- **Repeating the hero's headline** in the closing section. Different words, same
  idea.
- **Green-means-good.** γ is green (`SURVIVED`) and still loses. If the design
  implies green = winner, the comparison section contradicts itself.
- **Explaining the authority boundary twice.** It belongs to section 04 as
  narrative and section 08 as architecture. A third telling is padding.
- **A confidence score creeping in.** Any progress ring or 0–100 gauge silently
  contradicts the product's central claim. There is no confidence score anywhere
  in the system.
- **Cargo-culted numbered eyebrows.** Ours are legitimate — both pages are
  genuine sequences — but they must number the *argument*, not decorate the
  sections.

### Technically hardest, in order

1. **02 MANYWORLDS sticky scene** — sticky inside `.bp-marketing`'s own scroll
   container, not the window. Every sentinel must observe with
   `root: .bp-marketing`. The single most likely thing to be got wrong, and it
   fails silently.
2. **Protocol shell (3A)** — three independently sticky columns whose heights
   differ, with one shared stage state.
3. **04 THE ATTACK** — the crossing must be legible without colour, at 390 px,
   and under reduced motion.
4. **05 COMPARISON on mobile** — transposing a 3-column matrix without losing
   table semantics.

### The constraint most likely to be forgotten

`html` and `body` are `overflow: hidden` — Mission Control owns them. Scroll
happens inside `.bp-marketing`.

Any `IntersectionObserver` created with the default root, or any
`window.addEventListener('scroll')`, **will silently never fire.** Both sticky
sections and all reveal animations depend on getting this right. A test asserting
no `window` scroll listener is worth writing in phase 2B.

### Known duplicate demo data

The canonical incident appears in ~33 files across `docs/`, `backend/tests/` and
`frontend/src/__tests__/`. Some carry stale values (notably `12.4k` affected
users in `heroRun.ts` and `apiFixtures.ts`).

**Phase 2A did not fix these** — it is out of scope and touching test fixtures
risks unrelated breakage. The mitigation for the marketing site is
`canonicalIncident.ts`: one typed module, sourced from the engine, that the
marketing surfaces read instead of copying values around.

---

## 18. Judge-impact assessment

Ranked by expected impact, highest first.

1. **04 THE ATTACK** — the authority transfer is the whole thesis made visible,
   and nothing else in the category does it. Highest ceiling.
2. **06 CHECKPOINT** — mutating the action and watching approval invalidate is a
   *demonstration of a security property*, not a claim about one. Judges can
   operate it themselves.
3. **01 THE TRAP** — now literally true: α is the fastest world and still vetoed.
   Sets up everything.
4. **05 COMPARISON** — the absence of a score is the point, and the real axes
   prove it isn't marketing.
5. **02 MANYWORLDS** — the most cinematic, but the least differentiated. Plenty
   of sites can animate a fork.

---

## 19. Status

Phase 2A is **design only**. No components exist, no routes changed, no backend
touched, and the frozen hero (`e0e9213`) is untouched.

The next action is Phase 2B, beginning with `frontend/src/data/canonicalIncident.ts`.
