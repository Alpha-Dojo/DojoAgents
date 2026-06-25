import { useCallback, useEffect, useMemo, useState, type ChangeEvent, type ReactNode } from 'react';
import { fetchSettingsConfig, updateSettingsConfig } from '../../api/settings';
import { useTranslation } from '../../hooks/useTranslation';
import type { SettingsConfig, SettingsFormState, ProviderForm } from '../../types/settings';
import './SettingsModal.css';

const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'];

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

function buildForm(cfg: SettingsConfig): SettingsFormState {
  const llm = asRecord(cfg.llm_provider);
  const providers: Record<string, ProviderForm> = {};
  const KNOWN_PROVIDERS = ['openai', 'anthropic', 'gemini', 'deepseek', 'glm', 'minimax', 'kimi'];

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

  const agent = asRecord(cfg.agent);
  const sandbox = asRecord(asRecord(cfg.tools).sandbox);
  const skills = asRecord(cfg.skills);
  const scheduler = asRecord(cfg.scheduler);
  const dashboard = asRecord(cfg.dashboard);
  const logging = asRecord(cfg.logging);
  const dojosdk = asRecord(cfg.dojosdk);
  const multiAgent = asRecord(cfg.multi_agent);
  const defaultAgents = Array.isArray(multiAgent.default_agents) ? multiAgent.default_agents : [];

  return {
    llm_provider: { default: asString(llm.default, 'openai'), providers },
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
    },
    tools: {
      sandbox: {
        allowed_roots: arrToLines(sandbox.allowed_roots),
        allow_network: asBool(sandbox.allow_network, false),
        allowed_commands: arrToLines(sandbox.allowed_commands),
        timeout_seconds: asNumber(sandbox.timeout_seconds, 120),
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
    <input
      type={type}
      value={value}
      placeholder={placeholder}
      onChange={(event: ChangeEvent<HTMLInputElement>) => onChange(event.target.value)}
    />
  );

  const numberInput = (
    value: number,
    onChange: (value: number) => void,
    min = 0,
    max?: number,
  ) => (
    <input
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
              <button type="button" onClick={loadConfig}>{t('settings.retry')}</button>
            </div>
          ) : null}

          {form ? (
            <form className="settings-form" onSubmit={(event) => {
              event.preventDefault();
              void handleSave();
            }}>
              <Section title="LLM Provider" open>
                <Field label="Default Provider">
                  {textInput(form.llm_provider.default, (value) =>
                    updateField((draft) => { draft.llm_provider.default = value; }))}
                </Field>
                {providerNames.map((name) => {
                  const provider = form.llm_provider.providers[name];
                  return (
                    <div className="settings-subsection" key={name}>
                      <h3>{name}</h3>
                      <Field label="Model">
                        {textInput(provider.model, (value) =>
                          updateField((draft) => { draft.llm_provider.providers[name].model = value; }))}
                      </Field>
                      <Field label="Base URL">
                        {textInput(provider.base_url, (value) =>
                          updateField((draft) => { draft.llm_provider.providers[name].base_url = value; }), 'https://api.openai.com/v1')}
                      </Field>
                      <Field label="API Key Env">
                        {textInput(provider.api_key_env, (value) =>
                          updateField((draft) => { draft.llm_provider.providers[name].api_key_env = value; }), 'OPENAI_API_KEY')}
                      </Field>
                      <Field label="API Key">
                        {textInput(provider.api_key, (value) =>
                          updateField((draft) => { draft.llm_provider.providers[name].api_key = value; }), '***', 'password')}
                      </Field>
                    </div>
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
                  <select value={form.logging.level} onChange={(event) => updateField((draft) => { draft.logging.level = event.target.value; })}>
                    {LOG_LEVELS.map((level) => <option key={level} value={level}>{level}</option>)}
                  </select>
                </Field>
                <Field label="Format">{textInput(form.logging.format, (value) => updateField((draft) => { draft.logging.format = value; }))}</Field>
                <Field label="Date Format">{textInput(form.logging.date_format, (value) => updateField((draft) => { draft.logging.date_format = value; }))}</Field>
              </Section>

              <Section title="Dojo SDK">
                <Field label="API Key">{textInput(form.dojosdk.api_key, (value) => updateField((draft) => { draft.dojosdk.api_key = value; }), '***', 'password')}</Field>
                <Field label="Base URL">{textInput(form.dojosdk.base_url, (value) => updateField((draft) => { draft.dojosdk.base_url = value; }))}</Field>
                <Field label="Timeout (seconds)">{numberInput(form.dojosdk.timeout, (value) => updateField((draft) => { draft.dojosdk.timeout = value; }), 1)}</Field>
                <Field label="Max Retries">{numberInput(form.dojosdk.max_retries, (value) => updateField((draft) => { draft.dojosdk.max_retries = value; }), 0)}</Field>
              </Section>
            </form>
          ) : null}
        </div>

        <footer className="settings-modal__footer">
          {saveStatus ? <span className={`settings-save-status settings-save-status--${saveStatus.type}`}>{saveStatus.message}</span> : <span />}
          <div className="settings-modal__actions">
            <button type="button" className="settings-button settings-button--ghost" onClick={onClose}>{t('settings.cancel')}</button>
            <button type="button" className="action-button settings-button settings-button--primary" disabled={!form || saving} onClick={() => void handleSave()}>
              {saving ? t('settings.saving') : t('settings.save')}
            </button>
          </div>
        </footer>
      </section>
    </div>
  );
}
