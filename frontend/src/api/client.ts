// Thin typed wrapper around the backend. Routes are listed in docs/architecture/api-routes.md.

export interface Health {
  ok: boolean;
  openrouter_configured: boolean;
  local_documents: number;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: unknown,
  ) {
    super(`API ${status}`);
  }
}

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal });
  const body: unknown = await response.json();
  if (!response.ok) throw new ApiError(response.status, body);
  return body as T;
}

export async function postJson<T>(
  path: string,
  payload: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  const body: unknown = await response.json();
  if (!response.ok) throw new ApiError(response.status, body);
  return body as T;
}

export const getHealth = (signal?: AbortSignal) => getJson<Health>("/api/health", signal);
