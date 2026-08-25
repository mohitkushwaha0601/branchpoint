/**
 * Routes. `/` opens the hero run directly: this product has one job on load,
 * and it is showing the decision a human is being asked to make.
 */

import { Navigate, Route, Routes } from "react-router-dom";

import { heroRun } from "../data/heroRun";
import { RunPage } from "../pages/RunPage";
import { RunsPage } from "../pages/RunsPage";
import { SystemPage } from "../pages/SystemPage";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to={`/runs/${heroRun.runId}`} replace />} />
      <Route path="/runs" element={<RunsPage />} />
      <Route path="/runs/:runId" element={<RunPage />} />
      <Route path="/system" element={<SystemPage />} />
      <Route path="*" element={<Navigate to={`/runs/${heroRun.runId}`} replace />} />
    </Routes>
  );
}
