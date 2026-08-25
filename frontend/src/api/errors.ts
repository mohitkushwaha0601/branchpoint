/**
 * One error type for every backend call.
 *
 * The UI has to tell four situations apart — unreachable, not found, a
 * conflict the human must read, and a server fault — so the status, the
 * backend's own detail string, and the request that produced them all travel
 * together rather than being flattened into a message.
 */

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly method: string;
  readonly path: string;

  constructor(init: {
    status: number;
    detail: string;
    method: string;
    path: string;
  }) {
    super(`${init.method} ${init.path} failed (${init.status}): ${init.detail}`);
    this.name = "ApiError";
    this.status = init.status;
    this.detail = init.detail;
    this.method = init.method;
    this.path = init.path;
  }

  /** Status 0 means the request never reached a server. */
  get isUnreachable(): boolean {
    return this.status === 0;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  /** A stale or mismatched approval — the human needs to re-read the run. */
  get isConflict(): boolean {
    return this.status === 409;
  }
}

/** Whether a thrown value is an aborted request rather than a real failure. */
export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
