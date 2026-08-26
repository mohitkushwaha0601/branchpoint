/**
 * Backend health.
 *
 * Only BRANCHPOINT's own `/health` is reachable from the browser. TrueForge,
 * the sandbox provider, and the model provider are private to the backend and
 * are never contacted from here — their status stays unknown until BRANCHPOINT
 * exposes one itself.
 */

import { request } from "./client";
import type { HealthDto } from "./types";

export function getHealth(signal?: AbortSignal): Promise<HealthDto> {
  return request<HealthDto>("/health", { signal });
}
