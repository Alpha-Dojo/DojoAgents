export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly body?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    signal: init?.signal ?? AbortSignal.timeout(60_000),
    headers: {
      Accept: 'application/json',
      ...init?.headers,
    },
  });

  const text = await res.text();

  if (!res.ok) {
    let body: unknown = text;
    try {
      body = JSON.parse(text);
    } catch {
      // keep raw text body
    }
    throw new ApiError(`Request failed: ${res.status} ${res.statusText}`, res.status, body);
  }

  if (!text) {
    throw new ApiError(`Empty response: ${res.status} ${res.statusText}`, res.status);
  }

  return JSON.parse(text) as T;
}
