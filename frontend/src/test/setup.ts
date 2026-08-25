import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import "@testing-library/jest-dom/vitest";

// Vitest runs without injected globals here, so Testing Library cannot find an
// `afterEach` to hook itself onto and never auto-cleans. Unmounting explicitly
// keeps each test looking at its own DOM instead of every prior test's.
afterEach(cleanup);

// jsdom implements no layout engine and ships no ResizeObserver. The branch
// graph measures lane geometry to draw its connectors; a no-op observer lets it
// mount and fall back to its zero-geometry path instead of throwing.
class NoopResizeObserver implements ResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

globalThis.ResizeObserver ??= NoopResizeObserver;
