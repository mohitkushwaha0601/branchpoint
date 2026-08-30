/**
 * Routes.
 *
 * `/` is the public landing page. Everything under `/runs` and `/system` is
 * Mission Control and is unchanged.
 *
 * The catch-all still sends unknown paths to the run list. That is the existing
 * behaviour, and Phase 1A deliberately does not redefine it just because a
 * marketing route now exists — where a stray URL should land is a decision for
 * the phase that adds the rest of the public site.
 */

import { Navigate, Route, Routes } from "react-router-dom";

import { HeroDemoPage } from "../pages/HeroDemoPage";
import { HowItWorksPage } from "../pages/HowItWorksPage";
import { LandingPage } from "../pages/LandingPage";
import { RunPage } from "../pages/RunPage";
import { RunsPage } from "../pages/RunsPage";
import { SystemPage } from "../pages/SystemPage";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/how-it-works" element={<HowItWorksPage />} />
      <Route path="/runs" element={<RunsPage />} />
      <Route path="/runs/:runId" element={<RunPage />} />
      <Route path="/system" element={<SystemPage />} />
      {/* Offline fixture, for demos and tests. Never a fallback for a live run. */}
      <Route path="/demo/hero" element={<HeroDemoPage />} />
      <Route path="*" element={<Navigate to="/runs" replace />} />
    </Routes>
  );
}
