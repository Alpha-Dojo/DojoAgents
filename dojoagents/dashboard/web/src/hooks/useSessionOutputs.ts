import { useCallback, useEffect, useState } from 'react';
import { fetchSessionOutputs } from '../api/agent';
import { parseApiErrorMessage } from '../api/http';
import type { AgentSessionOutputFile } from '../types/agent';

export function useSessionOutputs(sessionId: string | null, refreshKey = 0) {
  const [files, setFiles] = useState<AgentSessionOutputFile[]>([]);
  const [outputDir, setOutputDir] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!sessionId) {
      setFiles([]);
      setOutputDir(null);
      setError(null);
      return;
    }
    setLoading(true);
    try {
      const payload = await fetchSessionOutputs(sessionId);
      setFiles(payload.files);
      setOutputDir(payload.output_dir);
      setError(null);
    } catch (err) {
      setFiles([]);
      setOutputDir(null);
      setError(parseApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    void refresh();
  }, [refresh, refreshKey]);

  return { files, outputDir, loading, error, refresh };
}
