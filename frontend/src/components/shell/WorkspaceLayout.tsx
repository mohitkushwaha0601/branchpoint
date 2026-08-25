/**
 * The Mission Control shell: header, three vertical panes, bottom drawer.
 *
 * Panes are separated by borders rather than floated as cards — the whole point
 * of the layout is that one continuous canvas holds the branch graph.
 */

import type { ReactNode } from "react";

import { AppHeader } from "./AppHeader";

export function WorkspaceLayout({
  sidebar,
  canvas,
  inspector,
  drawer,
}: {
  sidebar?: ReactNode;
  canvas: ReactNode;
  inspector?: ReactNode;
  drawer?: ReactNode;
}) {
  return (
    <div className="flex h-full flex-col bg-canvas">
      <AppHeader />
      <div className="flex min-h-0 flex-1">
        {sidebar}
        <main className="min-w-0 flex-1 overflow-y-auto">{canvas}</main>
        {inspector}
      </div>
      {drawer}
    </div>
  );
}
