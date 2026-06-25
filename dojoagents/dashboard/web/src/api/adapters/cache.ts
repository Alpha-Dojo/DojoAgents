const inflight = new Map<string, Promise<unknown>>();

export function dedupeFetch<T>(key: string, loader: () => Promise<T>): Promise<T> {
  const existing = inflight.get(key);
  if (existing) return existing as Promise<T>;
  const promise = loader().finally(() => {
    inflight.delete(key);
  });
  inflight.set(key, promise);
  return promise;
}
