/**
 * The single place this app talks to the network.
 *
 * Components never call `fetch`. Everything goes through `request`, so the base
 * URL, cancellation, and error parsing have exactly one implementation.
 *
 * Base URL resolution:
 * - `VITE_API_BASE_URL` when set (a deployed frontend pointing at Railway).
 * - Otherwise the empty string, meaning same-origin — which in development is
 *   the Vite dev server proxying `/api` and `/health` to the backend, so the
 *   browser never makes a cross-origin request and CORS never applies.
 *
 * No credential of any kind is read here. Model, Daytona, and TrueForge keys
 * live in the backend and in TrueForge; the browser is never given one, and
 * TrueForge's own address never appears in this bundle.
 */

import { ApiError } from "./errors";

const BASE_URL = (import.meta.env["VITE_API_BASE_URL"] ?? "").replace(/\/$/, "");

export function apiBaseUrl(): string {
  return BASE_URL;
}

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  signal?: AbortSignal;
}

/**
 * Pull a human-readable reason out of whatever the server sent.
 *
 * FastAPI answers with `{"detail": "..."}`, but a proxy or a crash can produce
 * HTML or nothing at all. Parsing must never throw a second error on top of the
 * first, so every branch ends in a usable string.
 */
async function readDetail(response: Response): Promise<string> {
  let raw: string;
  try {
    raw = await response.text();
  } catch {
    return response.statusText || "request failed";
  }
  if (!raw) return response.statusText || "request failed";

  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed === "string") return parsed;
    if (parsed !== null && typeof parsed === "object") {
      const detail = (parsed as { detail?: unknown }).detail;
      if (typeof detail === "string") return detail;
      // FastAPI validation errors arrive as a list of objects.
      if (Array.isArray(detail)) {
        const messages = detail
          .map((item) =>
            item !== null && typeof item === "object" && "msg" in item
              ? String((item as { msg: unknown }).msg)
              : null,
          )
          .filter((msg): msg is string => msg !== null);
        if (messages.length > 0) return messages.join("; ");
      }
    }
  } catch {
    // Not JSON. The raw body is the best description available.
  }
  return raw.slice(0, 300);
}

export async function request<T>(
  path: string,
  { method = "GET", body, signal }: RequestOptions = {},
): Promise<T> {
  const url = `${BASE_URL}${path}`;
  let response: Response;

  try {
    response = await fetch(url, {
      method,
      signal,
      headers: body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    // An aborted request is a caller decision, not a failure: re-thrown so the
    // caller's own abort handling can ignore it.
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError({
      status: 0,
      detail: "BRANCHPOINT backend unreachable",
      method,
      path,
    });
  }

  if (!response.ok) {
    throw new ApiError({
      status: response.status,
      detail: await readDetail(response),
      method,
      path,
    });
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
