/**
 * Shared harness: mount the app at the hero run's route.
 *
 * Tests drive the real router and the real data module rather than a stub, so
 * what they assert is what a reviewer would actually see on screen.
 */

import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { AppRoutes } from "../app/router";
import { heroRun } from "../data/heroRun";

export function renderRun(path = `/runs/${heroRun.runId}`) {
  const user = userEvent.setup();
  const view = render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
  return { ...view, user };
}

/** The inspector column, so assertions can be scoped away from the graph. */
export function inspector(): HTMLElement {
  const panels = document.querySelectorAll<HTMLElement>(
    '[aria-label="Inspector"]',
  );
  const panel = panels[0];
  if (panel === undefined) throw new Error("inspector panel not rendered");
  return panel;
}

/** One world's lane in the branch graph. */
export function lane(labelStart: string): HTMLElement {
  const sections = document.querySelectorAll<HTMLElement>("section[aria-label]");
  for (const section of sections) {
    if (section.getAttribute("aria-label")?.startsWith(labelStart)) {
      return section;
    }
  }
  throw new Error(`no lane matching ${labelStart}`);
}
