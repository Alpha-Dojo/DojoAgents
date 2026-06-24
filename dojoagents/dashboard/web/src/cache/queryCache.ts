interface CacheEntry<T> {
  data: T;
  updatedAt: number;
}

const store = new Map<string, CacheEntry<unknown>>();
const inflight = new Map<string, Promise<unknown>>();

export function getCached<T>(key: string): T | null {
  const entry = store.get(key);
  return entry ? (entry.data as T) : null;
}

export function setCached<T>(key: string, data: T) {
  store.set(key, { data, updatedAt: Date.now() });
}

export function hasCached(key: string): boolean {
  return store.has(key);
}

export function invalidateCache(key: string) {
  store.delete(key);
  inflight.delete(key);
}

export function invalidateCachePrefix(prefix: string) {
  for (const key of store.keys()) {
    if (key.startsWith(prefix)) {
      store.delete(key);
      inflight.delete(key);
    }
  }
}

export async function fetchCached<T>(key: string, fetcher: () => Promise<T>): Promise<T> {
  const pending = inflight.get(key);
  if (pending) return pending as Promise<T>;

  const promise = fetcher()
    .then((data) => {
      setCached(key, data);
      inflight.delete(key);
      return data;
    })
    .catch((error) => {
      inflight.delete(key);
      throw error;
    });

  inflight.set(key, promise);
  return promise;
}
