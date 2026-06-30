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

function readDetailMessage(detail: unknown): string | null {
  if (typeof detail === 'string' && detail.trim()) {
    return detail.trim();
  }
  if (typeof detail === 'object' && detail !== null && 'message' in detail) {
    const message = (detail as { message: unknown }).message;
    if (typeof message === 'string' && message.trim()) {
      return message.trim();
    }
  }
  return null;
}

export function parseApiErrorMessage(err: unknown, fallback = 'Request failed'): string {
  if (err instanceof ApiError) {
    if (typeof err.body === 'object' && err.body !== null && 'detail' in err.body) {
      const parsed = readDetailMessage((err.body as { detail: unknown }).detail);
      if (parsed) return parsed;
    }
    return err.message;
  }
  if (err instanceof Error && err.message.trim()) {
    return err.message;
  }
  return fallback;
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
