/** Current production reality, as BRANCHPOINT observes it. */

import { request } from "./client";
import type { DemoStateDto } from "./types";

/**
 * The reality source. What this returns is what is actually true right now —
 * so a change here after a commit is evidence the commit landed, in a way no
 * model output could be.
 */
export function getDemoState(signal?: AbortSignal): Promise<DemoStateDto> {
  return request<DemoStateDto>("/api/v1/demo/state", { signal });
}
