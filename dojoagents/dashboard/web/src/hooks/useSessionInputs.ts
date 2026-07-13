import { useCallback, useEffect, useState } from 'react';
import { fetchSessionInputs } from '../api/agent';
import { parseApiErrorMessage } from '../api/http';
import type { AgentSessionInputFile } from '../types/agent';

export function useSessionInputs(sessionId: string | null, refreshKey = 0) {
  const [files, setFiles] = useState<AgentSessionInputFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!sessionId) {
      setFiles([]);
      setError(null);
      return;
    }
    setLoading(true);
    try {
      const payload = await fetchSessionInputs(sessionId);
      setFiles(payload.files);
      setError(null);
    } catch (err) {
      setFiles([]);
      setError(parseApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    void refresh();
  }, [refresh, refreshKey]);

  return { files, loading, error, refresh };
}
