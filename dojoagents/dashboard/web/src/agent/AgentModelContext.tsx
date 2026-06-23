import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { fetchAgentModels } from '../api/agent';
import type { AgentModelItem } from '../types/agent';

interface AgentModelContextValue {
  models: AgentModelItem[];
  selectedModelId: string;
  selectedModel: AgentModelItem | null;
  geminiConfigured: boolean;
  loading: boolean;
  error: string | null;
  setSelectedModelId: (modelId: string) => void;
  refreshModels: () => Promise<void>;
}

const AgentModelContext = createContext<AgentModelContextValue | null>(null);

export function AgentModelProvider({ children }: { children: ReactNode }) {
  const [models, setModels] = useState<AgentModelItem[]>([]);
  const [selectedModelId, setSelectedModelIdState] = useState('gpt-4.1');
  const [geminiConfigured, setGeminiConfigured] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshModels = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAgentModels();
      setModels(data.models);
      setGeminiConfigured(data.gemini_configured);
      setSelectedModelIdState((current) => {
        const currentModel = data.models.find((model) => model.id === current);
        if (currentModel?.available) {
          return current;
        }
        const fallback =
          data.models.find((model) => model.id === data.default_model_id && model.available) ??
          data.models.find((model) => model.available);
        return fallback?.id ?? data.default_model_id;
      });
    } catch (err) {
      setGeminiConfigured(true);
      setModels([
        {
          id: 'gpt-4.1',
          label: 'openai:gpt-4.1',
          provider: 'openai',
          available: true,
        },
      ]);
      setSelectedModelIdState('gpt-4.1');
      setError(err instanceof Error ? err.message : 'Failed to load agent models');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshModels();
  }, [refreshModels]);

  const setSelectedModelId = useCallback(
    (modelId: string) => {
      const model = models.find((item) => item.id === modelId);
      if (!model?.available) {
        return;
      }
      setSelectedModelIdState(modelId);
    },
    [models],
  );

  const selectedModel = useMemo(
    () => models.find((model) => model.id === selectedModelId) ?? null,
    [models, selectedModelId],
  );

  const value = useMemo(
    () => ({
      models,
      selectedModelId,
      selectedModel,
      geminiConfigured,
      loading,
      error,
      setSelectedModelId,
      refreshModels,
    }),
    [
      models,
      selectedModelId,
      selectedModel,
      geminiConfigured,
      loading,
      error,
      setSelectedModelId,
      refreshModels,
    ],
  );

  return <AgentModelContext.Provider value={value}>{children}</AgentModelContext.Provider>;
}

export function useAgentModel() {
  const context = useContext(AgentModelContext);
  if (!context) {
    throw new Error('useAgentModel must be used within AgentModelProvider');
  }
  return context;
}
