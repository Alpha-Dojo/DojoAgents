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
import { updateSettingsConfig } from '../api/settings';
import type { AgentModelItem } from '../types/agent';

interface AgentModelContextValue {
  models: AgentModelItem[];
  selectedModelId: string;
  selectedModel: AgentModelItem | null;
  agentReady: boolean;
  geminiConfigured: boolean;
  zhipuConfigured: boolean;
  loading: boolean;
  saving: boolean;
  error: string | null;
  setSelectedModelId: (modelId: string) => Promise<void>;
  refreshModels: () => Promise<void>;
}

const AgentModelContext = createContext<AgentModelContextValue | null>(null);

export function AgentModelProvider({ children }: { children: ReactNode }) {
  const [models, setModels] = useState<AgentModelItem[]>([]);
  const [selectedModelId, setSelectedModelIdState] = useState('gemini-3.5');
  const [agentReady, setAgentReady] = useState(false);
  const [geminiConfigured, setGeminiConfigured] = useState(false);
  const [zhipuConfigured, setZhipuConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshModels = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAgentModels();
      setModels(data.models);
      setAgentReady(data.agent_ready);
      setGeminiConfigured(data.gemini_configured);
      setZhipuConfigured(data.zhipu_configured);
      setSelectedModelIdState(() => {
        const fallback =
          data.models.find((model) => model.id === data.default_model_id && model.available) ??
          data.models.find((model) => model.available);
        return fallback?.id ?? data.default_model_id;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load agent models');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshModels();
  }, [refreshModels]);

  const setSelectedModelId = useCallback(
    async (modelId: string) => {
      const model = models.find((item) => item.id === modelId);
      if (!model?.available) {
        return;
      }
      const previousModelId = selectedModelId;
      setSaving(true);
      setError(null);
      setSelectedModelIdState(modelId);
      try {
        await updateSettingsConfig({ llm_provider: { default: modelId } });
      } catch (err) {
        setSelectedModelIdState(previousModelId);
        setError(err instanceof Error ? err.message : 'Failed to update default model');
      } finally {
        setSaving(false);
      }
    },
    [models, selectedModelId],
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
      agentReady,
      geminiConfigured,
      zhipuConfigured,
      loading,
      saving,
      error,
      setSelectedModelId,
      refreshModels,
    }),
    [
      models,
      selectedModelId,
      selectedModel,
      agentReady,
      geminiConfigured,
      zhipuConfigured,
      loading,
      saving,
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
