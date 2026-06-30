import { useCallback, useEffect, useMemo, useState, type ChangeEvent, type ReactNode } from 'react';
import { fetchSettingsConfig, updateSettingsConfig } from '../../api/settings';
import { useAgentModel } from '../../agent/AgentModelContext';
import { useTranslation } from '../../hooks/useTranslation';
import type { SettingsConfig, SettingsFormState, ProviderForm } from '../../types/settings';
import { DojoButton, DojoInput, DojoSelect } from '../ui';
import './SettingsModal.css';

const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'];
const CUSTOM_MODEL_VALUE = '__custom_model__';
const WEB_SEARCH_BACKENDS = ['', 'ddgs', 'tavily', 'exa', 'firecrawl', 'brave-free', 'parallel'];
const WEB_EXTRACT_BACKENDS = ['', 'firecrawl', 'tavily', 'exa', 'searxng', 'parallel'];

interface ModelPreset {
  value: string;
  label: string;
}

interface ProviderPreset {
  label: string;
  baseUrl: string;
  apiKeyEnv: string;
  models: ModelPreset[];
}

const LLM_PROVIDER_PRESETS: Record<string, ProviderPreset> = {
  openai: {
    label: 'OpenAI',
    baseUrl: 'https://api.openai.com/v1',
    apiKeyEnv: 'OPENAI_API_KEY',
    models: [
      { value: 'gpt-5.5', label: 'GPT-5.5' },
      { value: 'gpt-5.4', label: 'GPT-5.4' },
      { value: 'gpt-5.4-mini', label: 'GPT-5.4 Mini' },
      { value: 'gpt-5.4-nano', label: 'GPT-5.4 Nano' },
      { value: 'gpt-4.1', label: 'GPT-4.1' },
      { value: 'gpt-4.1-mini', label: 'GPT-4.1 Mini' },
    ],
  },
  anthropic: {
    label: 'Anthropic',
    baseUrl: 'https://api.anthropic.com/v1',
    apiKeyEnv: 'ANTHROPIC_API_KEY',
    models: [
      { value: 'claude-opus-4-8', label: 'Claude Opus 4.8' },
      { value: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6' },
      { value: 'claude-haiku-4-5', label: 'Claude Haiku 4.5' },
      { value: 'claude-sonnet-4-20250514', label: 'Claude Sonnet 4' },
    ],
  },
  gemini: {
    label: 'Google Gemini',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
    apiKeyEnv: 'GEMINI_API_KEY',
    models: [
      { value: 'gemini-3.5-flash', label: 'Gemini 3.5 Flash' },
      { value: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro' },
      { value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
      { value: 'gemini-2.5-flash-lite', label: 'Gemini 2.5 Flash-Lite' },
    ],
  },
  deepseek: {
    label: 'DeepSeek',
    baseUrl: 'https://api.deepseek.com/v1',
    apiKeyEnv: 'DEEPSEEK_API_KEY',
    models: [
      { value: 'deepseek-v4-flash', label: 'DeepSeek V4 Flash' },
      { value: 'deepseek-chat', label: 'DeepSeek Chat' },
      { value: 'deepseek-reasoner', label: 'DeepSeek Reasoner' },
    ],
  },
  qwen: {
    label: 'Alibaba Tongyi',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    apiKeyEnv: 'DASHSCOPE_API_KEY',
    models: [
      { value: 'qwen3.7-max', label: 'Qwen3.7 Max' },
      { value: 'qwen3.7-plus', label: 'Qwen3.7 Plus' },
      { value: 'qwen3.6-flash', label: 'Qwen3.6 Flash' },
      { value: 'qwen3.5-omni-plus', label: 'Qwen3.5 Omni Plus' },
      { value: 'qwen3-rerank', label: 'Qwen3 Rerank' },
    ],
  },
  zhipu: {
    label: 'Zhipu GLM',
    baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
    apiKeyEnv: 'ZHIPUAI_API_KEY',
    models: [
      { value: 'glm-5.2', label: 'GLM-5.2' },
      { value: 'glm-5v-turbo', label: 'GLM-5V Turbo' },
      { value: 'glm-5.1', label: 'GLM-5.1' },
      { value: 'glm-5', label: 'GLM-5' },
      { value: 'glm-4.7', label: 'GLM-4.7' },
      { value: 'glm-4.6', label: 'GLM-4.6' },
      { value: 'glm-4-plus', label: 'GLM-4 Plus' },
    ],
  },
  moonshot: {
    label: 'Moonshot',
    baseUrl: 'https://api.moonshot.cn/v1',
    apiKeyEnv: 'MOONSHOT_API_KEY',
    models: [
      { value: 'kimi-k2.7-code', label: 'Kimi K2.7 Code' },
      { value: 'kimi-k2.7-code-highspeed', label: 'Kimi K2.7 Code HighSpeed' },
      { value: 'kimi-k2.6', label: 'Kimi K2.6' },
      { value: 'kimi-k2.5', label: 'Kimi K2.5' },
      { value: 'moonshot-v1-8k', label: 'Moonshot v1 8K' },
      { value: 'moonshot-v1-32k', label: 'Moonshot v1 32K' },
      { value: 'moonshot-v1-128k', label: 'Moonshot v1 128K' },
    ],
  },
  ollama: {
    label: 'Ollama',
    baseUrl: 'http://localhost:11434/v1',
    apiKeyEnv: '',
    models: [
      { value: 'llama3.1', label: 'Llama 3.1' },
      { value: 'qwen2.5-coder', label: 'Qwen2.5 Coder' },
      { value: 'deepseek-r1', label: 'DeepSeek R1' },
      { value: 'mistral', label: 'Mistral' },
    ],
  },
  glm: {
    label: 'Zhipu GLM (legacy)',
    baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
    apiKeyEnv: 'ZHIPUAI_API_KEY',
    models: [
      { value: 'glm-5.2', label: 'GLM-5.2' },
      { value: 'glm-5v-turbo', label: 'GLM-5V Turbo' },
      { value: 'glm-5.1', label: 'GLM-5.1' },
      { value: 'glm-5', label: 'GLM-5' },
      { value: 'glm-4.7', label: 'GLM-4.7' },
      { value: 'glm-4.6', label: 'GLM-4.6' },
      { value: 'glm-4-plus', label: 'GLM-4 Plus' },
    ],
  },
  kimi: {
    label: 'Kimi (legacy)',
    baseUrl: 'https://api.moonshot.cn/v1',
    apiKeyEnv: 'MOONSHOT_API_KEY',
    models: [
      { value: 'kimi-k2.7-code', label: 'Kimi K2.7 Code' },
      { value: 'kimi-k2.7-code-highspeed', label: 'Kimi K2.7 Code HighSpeed' },
      { value: 'kimi-k2.6', label: 'Kimi K2.6' },
      { value: 'kimi-k2.5', label: 'Kimi K2.5' },
      { value: 'moonshot-v1-8k', label: 'Moonshot v1 8K' },
      { value: 'moonshot-v1-32k', label: 'Moonshot v1 32K' },
      { value: 'moonshot-v1-128k', label: 'Moonshot v1 128K' },
    ],
  },
  minimax: {
    label: 'MiniMax',
    baseUrl: 'https://api.minimax.chat/v1',
    apiKeyEnv: 'MINIMAX_API_KEY',
    models: [
      { value: 'abab6.5s-chat', label: 'ABAB6.5s Chat' },
      { value: 'abab6.5g-chat', label: 'ABAB6.5g Chat' },
    ],
  },
};

const KNOWN_PROVIDERS = Object.keys(LLM_PROVIDER_PRESETS);

interface SettingsModalProps {
  open: boolean;
  onClose: () => void;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function asNumber(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function asBool(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

function arrToLines(value: unknown): string {
  return Array.isArray(value) ? value.join('\n') : String(value ?? '');
}

function linesToArr(text: string): string[] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}

function providerLabel(name: string): string {
  return LLM_PROVIDER_PRESETS[name]?.label ?? name;
}

function modelPresetValue(provider: ProviderForm, preset?: ProviderPreset): string {
  if (!preset) return CUSTOM_MODEL_VALUE;
  return preset.models.some((model) => model.value === provider.model) ? provider.model : CUSTOM_MODEL_VALUE;
}

function configuredProviderModel(config: SettingsConfig | null, providerName: string): string {
  const llm = asRecord(config?.llm_provider);
  const provider = asRecord(asRecord(llm.providers)[providerName]);
  return asString(provider.model).trim();
}

function isConfiguredModel(model: string, configuredModel: string): boolean {
  return configuredModel.length > 0 && model === configuredModel;
}

function buildForm(cfg: SettingsConfig): SettingsFormState {
  const llm = asRecord(cfg.llm_provider);
  const providers: Record<string, ProviderForm> = {};

  for (const name of KNOWN_PROVIDERS) {
    providers[name] = { model: '', base_url: '', api_key_env: '', api_key: '' };
  }

  for (const [name, value] of Object.entries(asRecord(llm.providers))) {
    const provider = asRecord(value);
    providers[name] = {
      model: asString(provider.model),
      base_url: asString(provider.base_url),
      api_key_env: asString(provider.api_key_env),
      api_key: provider.api_key === '***' ? '' : asString(provider.api_key),
    };
  }

  const defaultProvider = asString(llm.default, 'openai');
  if (!providers[defaultProvider]) {
    providers[defaultProvider] = { model: '', base_url: '', api_key_env: '', api_key: '' };
  }

  const agent = asRecord(cfg.agent);
  const tools = asRecord(cfg.tools);
  const sandbox = asRecord(tools.sandbox);
  const web = asRecord(tools.web);
  const skills = asRecord(cfg.skills);
  const scheduler = asRecord(cfg.scheduler);
  const dashboard = asRecord(cfg.dashboard);
  const logging = asRecord(cfg.logging);
  const dojosdk = asRecord(cfg.dojosdk);
  const multiAgent = asRecord(cfg.multi_agent);
  const defaultAgents = Array.isArray(multiAgent.default_agents) ? multiAgent.default_agents : [];

  return {
    llm_provider: { default: defaultProvider, providers },
    agent: {
      model: asString(agent.model),
      max_iterations: asNumber(agent.max_iterations, 8),
      max_tool_workers: asNumber(agent.max_tool_workers, 4),
      default_skills: arrToLines(agent.default_skills),
      lazy_skills: asBool(agent.lazy_skills, true),
      enable_skill_cache: asBool(agent.enable_skill_cache, true),
      enable_guardrails: asBool(agent.enable_guardrails, true),
      enable_think_scrubbing: asBool(agent.enable_think_scrubbing, true),
      enable_context_compression: asBool(agent.enable_context_compression, true),
      compression_threshold_ratio: asNumber(agent.compression_threshold_ratio, 0.8),
      default_context_window: asNumber(agent.default_context_window, 32768),
      session_max_tokens_cap:
        agent.session_max_tokens_cap === null || agent.session_max_tokens_cap === undefined
          ? null
          : asNumber(agent.session_max_tokens_cap, 32768),
    },
    tools: {
      sandbox: {
        allowed_roots: arrToLines(sandbox.allowed_roots),
        allow_network: asBool(sandbox.allow_network, false),
        allowed_commands: arrToLines(sandbox.allowed_commands),
        timeout_seconds: asNumber(sandbox.timeout_seconds, 120),
      },
      web: {
        search_backend: asString(web.search_backend),
        extract_backend: asString(web.extract_backend),
        search_base_url: asString(web.search_base_url),
        extract_base_url: asString(web.extract_base_url),
        max_extract_urls: asNumber(web.max_extract_urls, 5),
        max_content_bytes: asNumber(web.max_content_bytes, 2_000_000),
        summary_threshold_chars: asNumber(web.summary_threshold_chars, 6000),
        max_summary_chars: asNumber(web.max_summary_chars, 2500),
        debug: asBool(web.debug, false),
      },
    },
    memory: {
      provider: asString(asRecord(cfg.memory).provider, 'skill_summary'),
      generated_skill_dir: asString(asRecord(cfg.memory).generated_skill_dir),
    },
    skills: {
      dir: asString(skills.dir),
      generated_skill_dir: asString(skills.generated_skill_dir),
      external_dirs: arrToLines(skills.external_dirs),
      disabled: arrToLines(skills.disabled),
      read_claude_skills: asBool(skills.read_claude_skills, false),
    },
    scheduler: {
      enabled: asBool(scheduler.enabled, true),
      timezone: asString(scheduler.timezone, 'Asia/Shanghai'),
      store: asString(scheduler.store),
    },
    dashboard: {
      host: asString(dashboard.host, '127.0.0.1'),
      port: asNumber(dashboard.port, 8765),
    },
    logging: {
      level: asString(logging.level, 'INFO'),
      format: asString(logging.format),
      date_format: asString(logging.date_format),
    },
    dojosdk: {
      api_key: dojosdk.api_key === '***' ? '' : asString(dojosdk.api_key),
      base_url: asString(dojosdk.base_url),
      timeout: asNumber(dojosdk.timeout, 60),
      max_retries: asNumber(dojosdk.max_retries, 1),
    },
    multi_agent: {
      enabled: asBool(multiAgent.enabled, false),
      max_workers: asNumber(multiAgent.max_workers, 3),
      default_agents: defaultAgents.map((item) => {
        const entry = asRecord(item);
        return {
          role: asString(entry.role),
          name: asString(entry.name),
          model: asString(entry.model),
        };
      }),
    },
  };
}

function buildPatch(form: SettingsFormState): SettingsConfig {
  const providers: Record<string, unknown> = {};
  for (const [name, provider] of Object.entries(form.llm_provider.providers)) {
    if (!provider.model && !provider.base_url && !provider.api_key_env && !provider.api_key && name !== form.llm_provider.default) {
      continue;
    }
    const next: Record<string, unknown> = { model: provider.model };
    if (provider.base_url) next.base_url = provider.base_url;
    if (provider.api_key_env) next.api_key_env = provider.api_key_env;
    if (provider.api_key) next.api_key = provider.api_key;
    providers[name] = next;
  }

  const sdkPatch: Record<string, unknown> = {
    base_url: form.dojosdk.base_url || null,
    timeout: form.dojosdk.timeout,
    max_retries: form.dojosdk.max_retries,
  };
  if (form.dojosdk.api_key) sdkPatch.api_key = form.dojosdk.api_key;

  return {
    llm_provider: { default: form.llm_provider.default, providers },
    agent: {
      ...form.agent,
      default_skills: linesToArr(form.agent.default_skills),
    },
    tools: {
      sandbox: {
        ...form.tools.sandbox,
        allowed_roots: linesToArr(form.tools.sandbox.allowed_roots),
        allowed_commands: linesToArr(form.tools.sandbox.allowed_commands),
      },
      web: {
        ...form.tools.web,
        search_backend: form.tools.web.search_backend || null,
        extract_backend: form.tools.web.extract_backend || null,
        search_base_url: form.tools.web.search_base_url || null,
        extract_base_url: form.tools.web.extract_base_url || null,
      },
    },
    memory: { ...form.memory },
    skills: {
      ...form.skills,
      external_dirs: linesToArr(form.skills.external_dirs),
      disabled: linesToArr(form.skills.disabled),
    },
    scheduler: { ...form.scheduler },
    dashboard: { ...form.dashboard },
    logging: { ...form.logging },
    dojosdk: sdkPatch,
    multi_agent: {
      enabled: form.multi_agent.enabled,
      max_workers: form.multi_agent.max_workers,
      default_agents: form.multi_agent.default_agents.map((agent) => ({
        role: agent.role,
        name: agent.name,
        model: agent.model || null,
      })),
    },
  };
}

function Section({ title, open, children }: { title: string; open?: boolean; children: ReactNode }) {
  return (
    <details className="settings-section" open={open}>
      <summary>{title}</summary>
      <div className="settings-section__body">{children}</div>
    </details>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="settings-field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function CheckboxField({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="settings-check">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

export function SettingsModal({ open, onClose }: SettingsModalProps) {
  const { t } = useTranslation();
  const { refreshModels } = useAgentModel();
  const [rawConfig, setRawConfig] = useState<SettingsConfig | null>(null);
  const [form, setForm] = useState<SettingsFormState | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const providerNames = useMemo(() => Object.keys(form?.llm_provider.providers ?? {}), [form]);

  const loadConfig = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchSettingsConfig()
      .then((config) => {
        setRawConfig(config);
        setForm(buildForm(config));
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : t('settings.loadFailed'));
      })
      .finally(() => setLoading(false));
  }, [t]);

  useEffect(() => {
    if (open && !rawConfig && !loading) loadConfig();
  }, [loadConfig, loading, open, rawConfig]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose, open]);

  if (!open) return null;

  const updateField = (mutator: (draft: SettingsFormState) => void) => {
    setForm((current) => {
      if (!current) return current;
      const draft = structuredClone(current) as SettingsFormState;
      mutator(draft);
      return draft;
    });
    setSaveStatus(null);
  };

  const textInput = (
    value: string,
    onChange: (value: string) => void,
    placeholder?: string,
    type = 'text',
  ) => (
    <DojoInput
      size="sm"
      type={type}
      value={value}
      placeholder={placeholder}
      autoComplete={type === 'password' ? 'off' : undefined}
      onChange={(event: ChangeEvent<HTMLInputElement>) => onChange(event.target.value)}
    />
  );

  const numberInput = (
    value: number,
    onChange: (value: number) => void,
    min = 0,
    max?: number,
  ) => (
    <DojoInput
      size="sm"
      type="number"
      value={value}
      min={min}
      max={max}
      onChange={(event) => onChange(Number(event.target.value))}
    />
  );

  const handleSave = async () => {
    if (!form) return;
    setSaving(true);
    setSaveStatus(null);
    try {
      const updated = await updateSettingsConfig(buildPatch(form));
      setRawConfig(updated);
      setForm(buildForm(updated));
      await refreshModels();
      setSaveStatus({ type: 'success', message: t('settings.saveSuccess') });
      window.setTimeout(() => setSaveStatus(null), 3000);
    } catch (err) {
      setSaveStatus({
        type: 'error',
        message: err instanceof Error ? err.message : t('settings.saveFailed'),
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="settings-modal" role="dialog" aria-modal="true" aria-labelledby="settings-title">
      <button className="settings-modal__scrim" type="button" aria-label={t('settings.close')} onClick={onClose} />
      <section className="settings-modal__panel">
        <header className="settings-modal__header">
          <div>
            <p className="settings-modal__eyebrow">{t('settings.eyebrow')}</p>
            <h2 id="settings-title">{t('settings.title')}</h2>
          </div>
          <button className="settings-modal__close" type="button" aria-label={t('settings.close')} onClick={onClose}>
            ×
          </button>
        </header>

        <div className="settings-modal__body">
          {loading ? <div className="settings-state">{t('settings.loading')}</div> : null}
          {error ? (
            <div className="settings-state settings-state--error">
              <span>{error}</span>
              <DojoButton size="sm" variant="secondary" onClick={loadConfig}>{t('settings.retry')}</DojoButton>
            </div>
          ) : null}

          {form ? (
            <div className="settings-form">
              <Section title="LLM Provider" open>
                <Field label="Default Provider">
                  <DojoSelect
                    size="sm"
                    value={form.llm_provider.default}
                    onChange={(event) => updateField((draft) => { draft.llm_provider.default = event.target.value; })}
                    options={providerNames.map((name) => ({ value: name, label: providerLabel(name) }))}
                  />
                </Field>
                {providerNames.map((name) => {
                  const provider = form.llm_provider.providers[name];
                  const preset = LLM_PROVIDER_PRESETS[name];
                  const selectedPresetValue = modelPresetValue(provider, preset);
                  const configuredModel = configuredProviderModel(rawConfig, name);
                  const configuredPresetValue = modelPresetValue(
                    { ...provider, model: configuredModel },
                    preset,
                  );
                  const currentModelIsConfigured = isConfiguredModel(
                    provider.model,
                    configuredModel,
                  );
                  return (
                    <form
                      className="settings-subsection"
                      key={name}
                      onSubmit={(event) => {
                        event.preventDefault();
                        void handleSave();
                      }}
                    >
                      <h3>{providerLabel(name)}</h3>
                      <Field label="Model Preset">
                        <DojoSelect
                          size="sm"
                          value={selectedPresetValue}
                          onChange={(event) => {
                            const model = preset?.models.find((item) => item.value === event.target.value);
                            if (!model) return;
                            updateField((draft) => {
                              const nextProvider = draft.llm_provider.providers[name];
                              nextProvider.model = model.value;
                              nextProvider.base_url = preset.baseUrl;
                              nextProvider.api_key_env = preset.apiKeyEnv;
                            });
                          }}
                          options={[
                            ...(preset?.models.map((model) => ({
                              value: model.value,
                              label:
                                model.value === configuredModel
                                  ? `${model.label} · ${t('settings.configured')}`
                                  : model.label,
                            })) ?? []),
                            {
                              value: CUSTOM_MODEL_VALUE,
                              label:
                                configuredModel &&
                                configuredPresetValue === CUSTOM_MODEL_VALUE
                                  ? `Custom model · ${t('settings.configured')}`
                                  : 'Custom model',
                            },
                          ]}
                        />
                      </Field>
                      <Field label="Model">
                        <div
                          className={`settings-model-control ${
                            currentModelIsConfigured
                              ? 'settings-model-control--configured'
                              : ''
                          }`}
                        >
                          <DojoInput
                            size="sm"
                            value={provider.model}
                            onChange={(event) =>
                              updateField((draft) => {
                                draft.llm_provider.providers[name].model = event.target.value;
                              })
                            }
                          />
                          {provider.model === configuredModel && currentModelIsConfigured ? (
                            <span className="settings-model-configured">
                              {t('settings.configured')}
                            </span>
                          ) : null}
                        </div>
                      </Field>
                      <Field label="Base URL">
                        {textInput(provider.base_url, (value) =>
                          updateField((draft) => { draft.llm_provider.providers[name].base_url = value; }), preset?.baseUrl ?? 'https://api.openai.com/v1')}
                      </Field>
                      <Field label="API Key Env">
                        {textInput(provider.api_key_env, (value) =>
                          updateField((draft) => { draft.llm_provider.providers[name].api_key_env = value; }), preset?.apiKeyEnv ?? 'OPENAI_API_KEY')}
                      </Field>
                      <Field label="API Key">
                        {textInput(provider.api_key, (value) =>
                          updateField((draft) => { draft.llm_provider.providers[name].api_key = value; }), '***', 'password')}
                      </Field>
                    </form>
                  );
                })}
              </Section>

              <Section title="Agent">
                <Field label="Model">{textInput(form.agent.model, (value) => updateField((draft) => { draft.agent.model = value; }))}</Field>
                <Field label="Max Iterations">{numberInput(form.agent.max_iterations, (value) => updateField((draft) => { draft.agent.max_iterations = value; }), 1)}</Field>
                <Field label="Max Tool Workers">{numberInput(form.agent.max_tool_workers, (value) => updateField((draft) => { draft.agent.max_tool_workers = value; }), 1)}</Field>
                <Field label="Default Skills (one per line)">
                  <textarea rows={3} value={form.agent.default_skills} onChange={(event) => updateField((draft) => { draft.agent.default_skills = event.target.value; })} />
                </Field>
                <div className="settings-check-grid">
                  <CheckboxField label="Lazy Skills" checked={form.agent.lazy_skills} onChange={(checked) => updateField((draft) => { draft.agent.lazy_skills = checked; })} />
                  <CheckboxField label="Enable Skill Cache" checked={form.agent.enable_skill_cache} onChange={(checked) => updateField((draft) => { draft.agent.enable_skill_cache = checked; })} />
                  <CheckboxField label="Enable Guardrails" checked={form.agent.enable_guardrails} onChange={(checked) => updateField((draft) => { draft.agent.enable_guardrails = checked; })} />
                  <CheckboxField label="Enable Think Scrubbing" checked={form.agent.enable_think_scrubbing} onChange={(checked) => updateField((draft) => { draft.agent.enable_think_scrubbing = checked; })} />
                  <CheckboxField label="Enable Context Compression" checked={form.agent.enable_context_compression} onChange={(checked) => updateField((draft) => { draft.agent.enable_context_compression = checked; })} />
                </div>
                <Field label="Compression Threshold Ratio (0-1)">
                  {numberInput(form.agent.compression_threshold_ratio, (value) => updateField((draft) => { draft.agent.compression_threshold_ratio = value; }), 0.1)}
                </Field>
                <Field label="Default Context Window (fallback tokens)">
                  {numberInput(form.agent.default_context_window, (value) => updateField((draft) => { draft.agent.default_context_window = value; }), 1024)}
                </Field>
              </Section>

              <Section title="Multi-Agent">
                <CheckboxField label="Enabled" checked={form.multi_agent.enabled} onChange={(checked) => updateField((draft) => { draft.multi_agent.enabled = checked; })} />
                <Field label="Max Workers">{numberInput(form.multi_agent.max_workers, (value) => updateField((draft) => { draft.multi_agent.max_workers = value; }), 1)}</Field>
                <div className="settings-subsection">
                  <h3>Default Agents Settings</h3>
                  {form.multi_agent.default_agents.map((agent, index) => (
                    <div className="settings-agent-row" key={`${agent.role}-${agent.name}`}>
                      <span>{agent.name || agent.role}</span>
                      {textInput(agent.model ?? '', (value) => updateField((draft) => { draft.multi_agent.default_agents[index].model = value; }), 'model override')}
                    </div>
                  ))}
                </div>
              </Section>

              <Section title="Tools / Sandbox">
                <Field label="Allowed Roots (one per line)">
                  <textarea rows={3} value={form.tools.sandbox.allowed_roots} onChange={(event) => updateField((draft) => { draft.tools.sandbox.allowed_roots = event.target.value; })} />
                </Field>
                <CheckboxField label="Allow Network" checked={form.tools.sandbox.allow_network} onChange={(checked) => updateField((draft) => { draft.tools.sandbox.allow_network = checked; })} />
                <Field label="Allowed Commands (one per line)">
                  <textarea rows={3} value={form.tools.sandbox.allowed_commands} onChange={(event) => updateField((draft) => { draft.tools.sandbox.allowed_commands = event.target.value; })} />
                </Field>
                <Field label="Timeout (seconds)">{numberInput(form.tools.sandbox.timeout_seconds, (value) => updateField((draft) => { draft.tools.sandbox.timeout_seconds = value; }), 1)}</Field>
              </Section>

              <Section title="Tools / Web">
                <Field label="Search Backend">
                  <DojoSelect
                    size="sm"
                    value={form.tools.web.search_backend}
                    onChange={(event) => updateField((draft) => { draft.tools.web.search_backend = event.target.value; })}
                    options={WEB_SEARCH_BACKENDS.map((value) => ({
                      value,
                      label: value || 'Disabled',
                    }))}
                  />
                </Field>
                <Field label="Extract Backend">
                  <DojoSelect
                    size="sm"
                    value={form.tools.web.extract_backend}
                    onChange={(event) => updateField((draft) => { draft.tools.web.extract_backend = event.target.value; })}
                    options={WEB_EXTRACT_BACKENDS.map((value) => ({
                      value,
                      label: value || 'Disabled',
                    }))}
                  />
                </Field>
                <Field label="Search Base URL">
                  {textInput(form.tools.web.search_base_url, (value) => updateField((draft) => { draft.tools.web.search_base_url = value; }))}
                </Field>
                <Field label="Extract Base URL">
                  {textInput(form.tools.web.extract_base_url, (value) => updateField((draft) => { draft.tools.web.extract_base_url = value; }))}
                </Field>
                <Field label="Max Extract URLs">
                  {numberInput(form.tools.web.max_extract_urls, (value) => updateField((draft) => { draft.tools.web.max_extract_urls = value; }), 1)}
                </Field>
                <Field label="Max Content Bytes">
                  {numberInput(form.tools.web.max_content_bytes, (value) => updateField((draft) => { draft.tools.web.max_content_bytes = value; }), 1)}
                </Field>
                <Field label="Summary Threshold Chars">
                  {numberInput(form.tools.web.summary_threshold_chars, (value) => updateField((draft) => { draft.tools.web.summary_threshold_chars = value; }), 1)}
                </Field>
                <Field label="Max Summary Chars">
                  {numberInput(form.tools.web.max_summary_chars, (value) => updateField((draft) => { draft.tools.web.max_summary_chars = value; }), 1)}
                </Field>
                <CheckboxField label="Debug Logging" checked={form.tools.web.debug} onChange={(checked) => updateField((draft) => { draft.tools.web.debug = checked; })} />
              </Section>

              <Section title="Memory">
                <Field label="Provider">{textInput(form.memory.provider, (value) => updateField((draft) => { draft.memory.provider = value; }))}</Field>
                <Field label="Generated Skill Dir">{textInput(form.memory.generated_skill_dir, (value) => updateField((draft) => { draft.memory.generated_skill_dir = value; }))}</Field>
              </Section>

              <Section title="Skills">
                <Field label="Skills Directory">{textInput(form.skills.dir, (value) => updateField((draft) => { draft.skills.dir = value; }))}</Field>
                <Field label="Generated Skill Dir">{textInput(form.skills.generated_skill_dir, (value) => updateField((draft) => { draft.skills.generated_skill_dir = value; }))}</Field>
                <Field label="External Dirs (one per line)">
                  <textarea rows={2} value={form.skills.external_dirs} onChange={(event) => updateField((draft) => { draft.skills.external_dirs = event.target.value; })} />
                </Field>
                <Field label="Disabled Skills (one per line)">
                  <textarea rows={2} value={form.skills.disabled} onChange={(event) => updateField((draft) => { draft.skills.disabled = event.target.value; })} />
                </Field>
                <CheckboxField label="Read Claude Skills" checked={form.skills.read_claude_skills} onChange={(checked) => updateField((draft) => { draft.skills.read_claude_skills = checked; })} />
              </Section>

              <Section title="Scheduler">
                <CheckboxField label="Enabled" checked={form.scheduler.enabled} onChange={(checked) => updateField((draft) => { draft.scheduler.enabled = checked; })} />
                <Field label="Timezone">{textInput(form.scheduler.timezone, (value) => updateField((draft) => { draft.scheduler.timezone = value; }))}</Field>
                <Field label="Store Path">{textInput(form.scheduler.store, (value) => updateField((draft) => { draft.scheduler.store = value; }))}</Field>
              </Section>

              <Section title="Dashboard">
                <Field label="Host">{textInput(form.dashboard.host, (value) => updateField((draft) => { draft.dashboard.host = value; }))}</Field>
                <Field label="Port">{numberInput(form.dashboard.port, (value) => updateField((draft) => { draft.dashboard.port = value; }), 1, 65535)}</Field>
              </Section>

              <Section title="Logging">
                <Field label="Level">
                  <DojoSelect
                    size="sm"
                    value={form.logging.level}
                    onChange={(event) => updateField((draft) => { draft.logging.level = event.target.value; })}
                    options={LOG_LEVELS.map((level) => ({ value: level, label: level }))}
                  />
                </Field>
                <Field label="Format">{textInput(form.logging.format, (value) => updateField((draft) => { draft.logging.format = value; }))}</Field>
                <Field label="Date Format">{textInput(form.logging.date_format, (value) => updateField((draft) => { draft.logging.date_format = value; }))}</Field>
              </Section>

              <Section title="Dojo SDK">
                <form
                  className="settings-credential-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void handleSave();
                  }}
                >
                  <Field label="API Key">{textInput(form.dojosdk.api_key, (value) => updateField((draft) => { draft.dojosdk.api_key = value; }), '***', 'password')}</Field>
                  <Field label="Base URL">{textInput(form.dojosdk.base_url, (value) => updateField((draft) => { draft.dojosdk.base_url = value; }))}</Field>
                  <Field label="Timeout (seconds)">{numberInput(form.dojosdk.timeout, (value) => updateField((draft) => { draft.dojosdk.timeout = value; }), 1)}</Field>
                  <Field label="Max Retries">{numberInput(form.dojosdk.max_retries, (value) => updateField((draft) => { draft.dojosdk.max_retries = value; }), 0)}</Field>
                </form>
              </Section>
            </div>
          ) : null}
        </div>

        <footer className="settings-modal__footer">
          {saveStatus ? <span className={`settings-save-status settings-save-status--${saveStatus.type}`}>{saveStatus.message}</span> : <span />}
          <div className="settings-modal__actions">
            <DojoButton size="sm" variant="secondary" onClick={onClose}>{t('settings.cancel')}</DojoButton>
            <DojoButton size="sm" variant="primary" disabled={!form || saving} onClick={() => void handleSave()}>
              {saving ? t('settings.saving') : t('settings.save')}
            </DojoButton>
          </div>
        </footer>
      </section>
    </div>
  );
}
