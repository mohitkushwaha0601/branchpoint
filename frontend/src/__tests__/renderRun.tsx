/**
 * Mounting helpers.
 *
 * `renderApp` drives the real router, the real API client, the real adapters,
 * and the real components — only `fetch` is mocked. `renderFixture` mounts the
 * offline Phase 4.1 fixture, which is what the Phase 4.1 interaction tests use.
 */

import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { AppRoutes } from "../app/router";
import { RUN_ID } from "./apiFixtures";

export function renderApp(path = `/runs/${RUN_ID}`) {
  const user = userEvent.setup();
  const view = render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
  return { ...view, user };
}

/** The offline fixture route. No network, no polling. */
export function renderFixture() {
  return renderApp("/demo/hero");
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
