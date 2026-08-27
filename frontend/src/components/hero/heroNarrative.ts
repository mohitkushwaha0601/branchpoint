/**
 * The hero's narrative, as data.
 *
 * Every string here is traceable to something real. The verdicts are
 * `WorldVerdict` values; RECOMMENDED is the comparator's pick, which the domain
 * keeps deliberately distinct from a verdict. The metrics, versions, flag names
 * and world actions come from the canonical hero scenario in
 * `src/data/heroRun.ts` and `README.md`.
 *
 * Nothing on this page may state a fact the product cannot produce. If a line
 * here stops matching the domain, the line is wrong, not the domain.
 *
 * The monitor's own states — REHEARSAL ACTIVE, VETOED, RECOMMENDED, AWAITING
 * APPROVAL — are now baked into the video footage rather than drawn as HTML;
 * `useHeroVideoNarrative` reads the video's clock to keep the beats below in
 * step with it. "Human checkpoint" survives here as the human-readable label on
 * the status card, which is prose rather than a claim about the event stream.
 */

export type HeroTone = "ok" | "fail" | "run" | "gate" | "warn" | "muted";

/* ------------------------------------------------------------------ messages */

export interface MessageBeat {
  readonly id: string;
  readonly label: string;
  readonly body: string;
  /** Optional state chip, right-aligned on the label row. */
  readonly status?: string;
  readonly tone: HeroTone;
}

/**
 * The status stack, one card per beat.
 *
 * Four beats, not six: the baked monitor already establishes the incident and
 * the agent's proposal on screen, so the HTML stack states only what the
 * monitor cannot — the branchpoint structure — and shows at most three cards
 * at a time.
 */
export const MESSAGE_BEATS: readonly MessageBeat[] = [
  {
    id: "intercepted",
    label: "BRANCHPOINT",
    body: "Production intercepted",
    tone: "gate",
  },
  {
    id: "alpha",
    label: "WORLD α",
    body: "Compatibility failure reproduced",
    status: "VETOED",
    tone: "fail",
  },
  {
    id: "beta",
    label: "WORLD β",
    body: "SURVIVED · RECOMMENDED",
    tone: "ok",
  },
  {
    id: "checkpoint",
    label: "HUMAN CHECKPOINT",
    body: "Awaiting approval",
    tone: "gate",
  },
];

/**
 * The phone's cut of the same story.
 *
 * One card is on screen at a time, so the sequence has to carry itself without
 * a stack to lean on. INCIDENT and AGENT are dropped: they set up a situation,
 * and with no second card visible to hold that setup the reader would lose it
 * before the payoff. What remains is the argument itself — BRANCHPOINT
 * intercepts, one world fails, another is recommended, and a human still has to
 * say yes.
 */
export const MOBILE_BEATS: readonly MessageBeat[] = [
  {
    id: "intercepted",
    label: "BRANCHPOINT",
    body: "Production intercepted",
    tone: "gate",
  },
  {
    id: "alpha",
    label: "WORLD α",
    body: "Failure reproduced",
    status: "VETOED",
    tone: "fail",
  },
  {
    id: "beta",
    label: "WORLD β",
    body: "SURVIVED · RECOMMENDED",
    tone: "ok",
  },
  {
    id: "checkpoint",
    label: "HUMAN CHECKPOINT",
    body: "Awaiting approval",
    tone: "gate",
  },
];

/* ------------------------------------------------------------- accessibility */

/**
 * The one static description of the hero for assistive technology.
 *
 * The baked monitor and the status stack are decorative and `aria-hidden`: they
 * cycle, and announcing them would mean interrupting a screen reader every few
 * seconds forever. This sentence carries the same claim, once, and never
 * changes.
 */
export const HERO_DESCRIPTION =
  "BRANCHPOINT rehearses multiple candidate actions. A rollback is vetoed " +
  "after a reproduced compatibility failure, a safer alternative is " +
  "recommended, and execution waits for human approval.";

/**
 * The same run in full, still as plain static text.
 *
 * Kept alongside the summary because it is the only place the specific
 * evidence — which world was vetoed, on what grounds, and what is still
 * unchanged in production — is available to someone who cannot see the screen.
 * Static, non-live, and true with the video absent entirely.
 */
export const NARRATIVE_STEPS: readonly string[] = [
  "Checkout is failing in production: 41.3% error rate, 4.8 second p95 latency.",
  "An agent proposes rolling pricing-service back from v2.41 to v2.40.",
  "BRANCHPOINT intercepts the action. No commit capability is granted yet.",
  "The run forks into three counterfactual worlds: alpha rolls back, beta disables the PRICING_V2 flag, gamma scales the service.",
  "World alpha is VETOED. BRANCHPOINT's deterministic replay reproduced a schema compatibility failure against alpha's own snapshot.",
  "World beta SURVIVED, and the deterministic comparator recommends it.",
  "World gamma also SURVIVED but was not selected, because it only partly achieves the goal.",
  "Nothing has changed in production. The run is waiting for a human to approve exactly one bound action.",
];
