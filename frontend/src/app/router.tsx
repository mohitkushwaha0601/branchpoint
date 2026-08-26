/**
 * Routes.
 *
 * `/` opens the run list rather than a hardcoded run: which run matters is now
 * a backend fact, and there may not be one yet.
 */

import { Navigate, Route, Routes } from "react-router-dom";

import { HeroDemoPage } from "../pages/HeroDemoPage";
import { RunPage } from "../pages/RunPage";
import { RunsPage } from "../pages/RunsPage";
import { SystemPage } from "../pages/SystemPage";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/runs" replace />} />
      <Route path="/runs" element={<RunsPage />} />
      <Route path="/runs/:runId" element={<RunPage />} />
      <Route path="/system" element={<SystemPage />} />
      {/* Offline fixture, for demos and tests. Never a fallback for a live run. */}
      <Route path="/demo/hero" element={<HeroDemoPage />} />
      <Route path="*" element={<Navigate to="/runs" replace />} />
    </Routes>
  );
}
