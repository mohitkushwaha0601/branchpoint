/**
 * The Evidence Inspector's proof chain.
 *
 * The chain is the strongest claim Mission Control makes, so these tests attack
 * it from the direction that would embarrass us: can it be made to show a stage
 * that did not happen, or a veto that nothing justified?
 *
 * Every case drives the real component through the real API client against a
 * mocked socket. No model, TrueForge, or network call.
 */

import { screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { buildProofChain } from "../components/inspector/ProofChain";
import {
  RUN_ID,
  comparisonDto,
  demoStateDto,
  deterministicInspection,
  eventsDto,
  fullChainInspection,
  mockServer,
  nonDoppelgangerExploratoryInspection,
  partiallyLinkedInspection,
  runDto,
  survivingInspection,
  unsupportedClaimInspection,
  worldsDto,
} from "./apiFixtures";
import { inspector, lane, renderApp } from "./renderRun";

afterEach(() => vi.unstubAllGlobals());

function serveRun(inspection: Record<string, ReturnType<typeof fullChainInspection>>) {
  return mockServer({
    run: runDto(),
    worlds: worldsDto(),
    comparison: comparisonDto(),
    events: eventsDto(),
    demo: demoStateDto(),
    inspection,
  });
}

/** Mount the run and select α, whose inspection the tests care about. */
async function selectAlpha() {
  const view = renderApp(`/runs/${RUN_ID}`);
  await screen.findByRole("heading", { level: 1, name: "Checkout Regression" });
  await waitFor(() => expect(lane("WORLD α")).toBeInTheDocument());
  await view.user.click(
    within(lane("WORLD α")).getByRole("button", {
      name: /Rollback Pricing Deployment/,
    }),
  );
  return view;
}

async function chain(): Promise<HTMLElement> {
  return await within(inspector()).findByRole("region", { name: "Proof chain" });
}

// ----- 1. the complete authoritative chain -----------------------------------

describe("complete chain", () => {
  it("renders all four stages for a TrueForge-backed veto", async () => {
    serveRun({ world_alpha: fullChainInspection() });
    await selectAlpha();

    const panel = within(await chain());
    expect(panel.getByText("DOPPELGÄNGER")).toBeInTheDocument();
    expect(panel.getByText("EXPLORATORY")).toBeInTheDocument();
    expect(panel.getByText("BRANCHPOINT REPLAY")).toBeInTheDocument();
    expect(panel.getByText("VERIFIED")).toBeInTheDocument();
    expect(panel.getByText("COUNTEREXAMPLE")).toBeInTheDocument();
    expect(panel.getByText("REPRODUCED")).toBeInTheDocument();
    expect(panel.getByText("VERDICT")).toBeInTheDocument();
    expect(panel.getByText("VETOED")).toBeInTheDocument();
  });

  it("names the real hypothesis and the checks that actually failed", async () => {
    serveRun({ world_alpha: fullChainInspection() });
    await selectAlpha();

    const panel = within(await chain());
    expect(
      panel.getByText(/may not deserialize under v2.40/),
    ).toBeInTheDocument();
    expect(
      panel.getByText(/schema_compatibility, payment_retry failed/),
    ).toBeInTheDocument();
  });

  it("lists the supporting evidence split by authority", async () => {
    serveRun({ world_alpha: fullChainInspection() });
    await selectAlpha();

    const supporting = within(
      await within(inspector()).findByRole("region", { name: "Supporting evidence" }),
    );
    expect(supporting.getByText("MACHINE VERIFIED")).toBeInTheDocument();
    expect(
      supporting.getByText("schema_compatibility: all orders deserialize"),
    ).toBeInTheDocument();
    expect(supporting.getAllByText("FAIL")).toHaveLength(2);
    expect(
      supporting.getByText(/Only BRANCHPOINT.s own\s+replay can verify one/),
    ).toBeInTheDocument();
  });
});

// ----- 2. no fabricated DOPPELGÄNGER -----------------------------------------

describe("truthfulness", () => {
  it("does not claim DOPPELGÄNGER for a deterministic demo world", async () => {
    serveRun({ world_alpha: deterministicInspection() });
    await selectAlpha();

    const panel = within(await chain());
    // The stage is named but explicitly not reached — never shown as having run.
    expect(panel.getByText("NOT PRESENT")).toBeInTheDocument();
    expect(
      panel.getByText("No exploratory agent evidence for this world."),
    ).toBeInTheDocument();
    expect(panel.queryByText("EXPLORATORY")).not.toBeInTheDocument();

    // The rest of the chain is real and still concludes.
    expect(panel.getByText("VERIFIED")).toBeInTheDocument();
    expect(panel.getByText("REPRODUCED")).toBeInTheDocument();
    expect(panel.getByText("VETOED")).toBeInTheDocument();
  });

  it("does not conclude a veto from a claimed but unsupported reproduction", async () => {
    serveRun({ world_alpha: unsupportedClaimInspection() });
    await selectAlpha();

    const panel = within(await chain());
    expect(panel.getByText("CLAIMED, UNSUPPORTED")).toBeInTheDocument();
    expect(
      panel.getByText(/vetoes nothing/),
    ).toBeInTheDocument();
    expect(panel.queryByText("VETOED")).not.toBeInTheDocument();
    expect(panel.queryByText("REPRODUCED")).not.toBeInTheDocument();
  });

  it("shows a surviving world no veto conclusion", async () => {
    serveRun({ world_alpha: survivingInspection() });
    await selectAlpha();

    const panel = within(await chain());
    expect(panel.getByText("WORLD SURVIVED")).toBeInTheDocument();
    expect(
      panel.getByText("No authoritative counterexample. Nothing vetoed this world."),
    ).toBeInTheDocument();
    expect(panel.getByText("NONE REPRODUCED")).toBeInTheDocument();
    expect(panel.queryByText("VETOED")).not.toBeInTheDocument();
  });
});

// ----- 8. the structured contract is load-bearing -----------------------------

describe("structured contract", () => {
  it("builds the chain without reading verdict_reason", async () => {
    const inspection = fullChainInspection();
    // Deliberate nonsense. If the chain still reads correctly, nothing in it
    // depends on parsing this string.
    inspection.world = {
      ...inspection.world,
      verdict_reason: "lorem ipsum dolor sit amet ~~~ not a real reason ~~~",
    };
    serveRun({ world_alpha: inspection });
    await selectAlpha();

    const panel = within(await chain());
    expect(panel.getByText("VETOED")).toBeInTheDocument();
    expect(panel.getByText("REPRODUCED")).toBeInTheDocument();
    expect(panel.queryByText(/lorem ipsum/)).not.toBeInTheDocument();
  });

  it("drives the veto stage from world.veto alone", () => {
    const withVeto = fullChainInspection();
    const stages = buildProofChain(withVeto);
    expect(stages.at(-1)).toMatchObject({ key: "veto", verdict: "VETOED" });

    // Same evidence and same reproduced counterexample, but no structured veto:
    // the conclusion disappears with it.
    const withoutVeto = {
      ...withVeto,
      world: { ...withVeto.world, veto: null },
    };
    expect(buildProofChain(withoutVeto).at(-1)).toMatchObject({
      key: "veto",
      state: "ABSENT",
    });
  });

  it("keeps reproduced and authoritative distinct", () => {
    const stages = buildProofChain(unsupportedClaimInspection());
    const reproduced = stages.find((stage) => stage.key === "reproduced")!;

    expect(reproduced.state).toBe("UNSUPPORTED");
    expect(reproduced.verdict).toBe("CLAIMED, UNSUPPORTED");
  });
});

// ----- 5-7. fetch behaviour ---------------------------------------------------

describe("fetching", () => {
  it("requests inspection for the selected world only", async () => {
    const server = serveRun({ world_alpha: fullChainInspection() });
    await selectAlpha();
    await chain();

    // One request per selection, and only for worlds actually selected: the
    // recommended world on mount, then α when it is clicked. Never γ.
    const detailCalls = server.calls.filter((call) => /\/worlds\/world_/.test(call));
    expect(new Set(detailCalls)).toEqual(
      new Set([
        `GET /api/v1/runs/${RUN_ID}/worlds/world_beta`,
        `GET /api/v1/runs/${RUN_ID}/worlds/world_alpha`,
      ]),
    );
    expect(detailCalls.some((call) => call.endsWith("world_gamma"))).toBe(false);
  });

  it("fetches the newly selected world when the selection changes", async () => {
    const server = serveRun({
      world_alpha: fullChainInspection(),
      world_beta: survivingInspection(),
    });
    const { user } = await selectAlpha();
    await chain();

    await user.click(
      within(lane("WORLD β")).getByRole("button", { name: /Disable Pricing V2/ }),
    );

    await waitFor(() =>
      expect(
        server.calls.some((call) => call.endsWith("/worlds/world_beta")),
      ).toBe(true),
    );
    expect(
      within(await chain()).getByText("WORLD SURVIVED"),
    ).toBeInTheDocument();
  });

  it("never lets a late response for one world paint another", async () => {
    // α's inspection is a veto; β's is a survivor. If α's response were allowed
    // to land after β was selected, the panel would read VETOED under β's name.
    const server = serveRun({
      world_alpha: fullChainInspection(),
      world_beta: survivingInspection(),
    });
    const { user } = await selectAlpha();
    await chain();

    await user.click(
      within(lane("WORLD β")).getByRole("button", { name: /Disable Pricing V2/ }),
    );
    await waitFor(() =>
      expect(
        within(inspector()).getAllByText("Disable Pricing V2").length,
      ).toBeGreaterThan(0),
    );

    const panel = within(await chain());
    expect(panel.getByText("WORLD SURVIVED")).toBeInTheDocument();
    expect(panel.queryByText("VETOED")).not.toBeInTheDocument();
    expect(
      server.calls.filter((c) => c.endsWith("/worlds/world_alpha")),
    ).toHaveLength(1);
  });

  it("keeps the world summary usable when detail cannot be fetched", async () => {
    const server = serveRun({ world_alpha: fullChainInspection() });
    server.fail("/worlds/world_alpha", 500, "internal error");
    await selectAlpha();

    const panel = within(inspector());
    expect(await panel.findByText("Evidence detail unavailable.")).toBeInTheDocument();
    // The summary above it is untouched.
    expect(panel.getAllByText("Rollback Pricing Deployment").length).toBeGreaterThan(0);
    expect(panel.getByText("VETOED")).toBeInTheDocument();
    // ...and the rest of the run page still works.
    expect(
      screen.getByRole("heading", { name: "MANUAL APPROVAL REQUIRED" }),
    ).toBeInTheDocument();
  });

  it("does not fetch inspection for the offline fixture route", async () => {
    const server = mockServer({});
    renderApp("/demo/hero");

    await screen.findByRole("heading", { level: 1, name: "Checkout Regression" });

    expect(server.calls.some((call) => /\/worlds\//.test(call))).toBe(false);
  });
});

// ----- provenance and linkage -------------------------------------------------
//
// Two ways the chain could overstate itself: crediting an agent that never ran,
// and presenting unrelated evidence as the proof behind a veto.

describe("provenance", () => {
  it("does not brand non-DOPPELGÄNGER exploratory evidence as DOPPELGÄNGER", async () => {
    serveRun({ world_alpha: nonDoppelgangerExploratoryInspection() });
    await selectAlpha();

    const panel = within(await chain());
    // Still exploratory — it is genuinely non-machine-verifiable...
    expect(panel.getByText("EXPLORATORY EVIDENCE")).toBeInTheDocument();
    expect(panel.getByText("EXPLORATORY")).toBeInTheDocument();
    expect(
      panel.getByText("operator flagged this rollback as risky"),
    ).toBeInTheDocument();
    // ...but no adversarial agent ran, so none is credited.
    expect(panel.queryByText("DOPPELGÄNGER")).not.toBeInTheDocument();
  });

  it("brands the stage DOPPELGÄNGER only when the source says so", () => {
    const doppelganger = buildProofChain(fullChainInspection())[0]!;
    const other = buildProofChain(nonDoppelgangerExploratoryInspection())[0]!;

    expect(doppelganger).toMatchObject({ title: "DOPPELGÄNGER", state: "REACHED" });
    expect(other).toMatchObject({ title: "EXPLORATORY EVIDENCE", state: "REACHED" });
  });

  it("quotes the adversary's hypothesis only for a real DOPPELGÄNGER stage", () => {
    // The non-DOPPELGÄNGER fixture's counterexample carries no hypothesis, and
    // the stage falls back to the record's own claim rather than borrowing one.
    const stage = buildProofChain(nonDoppelgangerExploratoryInspection())[0]!;

    expect(stage.detail).toBe("operator flagged this rollback as risky");
  });
});

describe("replay linkage", () => {
  it("uses the evidence the veto cites, not every machine-verifiable record", async () => {
    serveRun({ world_alpha: partiallyLinkedInspection() });
    await selectAlpha();

    const panel = within(await chain());
    expect(panel.getByText("payment_retry failed")).toBeInTheDocument();
    // The unrelated passing check is not presented as proof of the veto.
    expect(panel.queryByText(/cost_budget/)).not.toBeInTheDocument();
  });

  it("still lists the unlinked record under supporting evidence", async () => {
    serveRun({ world_alpha: partiallyLinkedInspection() });
    await selectAlpha();

    const supporting = within(
      await within(inspector()).findByRole("region", { name: "Supporting evidence" }),
    );
    expect(
      supporting.getByText("cost_budget: daily spend within budget"),
    ).toBeInTheDocument();
    expect(supporting.getByText("PASS")).toBeInTheDocument();
    expect(supporting.getByText("FAIL")).toBeInTheDocument();
  });

  it("falls back to failing evidence when the backend states no linkage", () => {
    const inspection = partiallyLinkedInspection();
    const unlinked = {
      ...inspection,
      world: { ...inspection.world, veto: null },
      counterexamples: inspection.counterexamples.map((item) => ({
        ...item,
        supporting_evidence_ids: [],
      })),
    };

    const verified = buildProofChain(unlinked).find((s) => s.key === "verified")!;

    expect(verified.detail).toBe("payment_retry failed");
  });
});

// ----- the action a world actually rehearsed ----------------------------------
//
// The list endpoint only carried an id, a name, and a type, so the Inspector
// used to say parameter values were "not exposed". They are now, and these pin
// that the rendered values come from the backend rather than from a fixture.

describe("action detail", () => {
  it("renders the stored target and parameters", async () => {
    serveRun({ world_alpha: fullChainInspection() });
    await selectAlpha();

    const panel = within(inspector());
    await waitFor(() =>
      expect(panel.getByText("pricing-service")).toBeInTheDocument(),
    );
    // The stored parameter, key and value, exactly as the backend sent it.
    expect(panel.getByText("version")).toBeInTheDocument();
    expect(panel.getByText("v2.40")).toBeInTheDocument();
    // ...and it no longer claims the data is missing.
    expect(
      panel.queryByText(/not exposed per world by the current API/),
    ).not.toBeInTheDocument();
  });

  it("renders the stored risk, reversibility, and fingerprint", async () => {
    serveRun({ world_alpha: fullChainInspection() });
    await selectAlpha();

    const panel = within(inspector());
    await waitFor(() => expect(panel.getByText("HIGH")).toBeInTheDocument());
    expect(panel.getByText("SET_DEPLOYMENT_VERSION")).toBeInTheDocument();
    expect(panel.getByText("e91c4d2a7b30f558")).toBeInTheDocument();
  });

  it("renders the measured outcome, not a reconstructed one", async () => {
    serveRun({ world_alpha: fullChainInspection() });
    await selectAlpha();

    const panel = within(inspector());
    await waitFor(() =>
      expect(
        panel.getByText("checkout_error_rate 0.413 -> 0.021"),
      ).toBeInTheDocument(),
    );
    expect(panel.getByText("Goal attainment")).toBeInTheDocument();
    expect(panel.getByText("94%")).toBeInTheDocument();
  });

  it("says a world has not executed rather than showing zeros", async () => {
    const inspection = fullChainInspection();
    serveRun({ world_alpha: { ...inspection, outcome: null } });
    await selectAlpha();

    const panel = within(inspector());
    await waitFor(() =>
      expect(
        panel.getByText(/has not executed yet, so nothing has been measured/),
      ).toBeInTheDocument(),
    );
  });
});
