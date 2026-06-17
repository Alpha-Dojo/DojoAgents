import { fetchJson } from './http';
import { USE_INTERACTIVE_MOCKS } from '../mocks/interactiveMockData';
import type { SettingsConfig } from '../types/settings';

const API_URL = '/api/config';
const API_DELAY_MS = 120;

let mockConfig: SettingsConfig = {
  llm_provider: {
    default: 'openai',
    providers: {
      openai: {
        model: 'gpt-4.1',
        base_url: 'https://api.openai.com/v1',
        api_key_env: 'OPENAI_API_KEY',
        api_key: '***',
      },
      gemini: {
        model: 'gemini-2.5-pro',
        base_url: '',
        api_key_env: 'GEMINI_API_KEY',
        api_key: '***',
      },
    },
  },
  agent: {
    model: 'gpt-4.1',
    max_iterations: 8,
    max_tool_workers: 4,
    default_skills: ['market-analysis', 'reporting'],
    lazy_skills: true,
    enable_skill_cache: true,
    enable_guardrails: true,
    enable_think_scrubbing: true,
    enable_context_compression: true,
  },
  multi_agent: {
    enabled: true,
    max_workers: 3,
    default_agents: [
      { role: 'researcher', name: 'Research', model: '' },
      { role: 'analyst', name: 'Analyst', model: '' },
    ],
  },
  tools: {
    sandbox: {
      allowed_roots: ['~/workspace', '~/Downloads'],
      allow_network: false,
      allowed_commands: ['python', 'node', 'npm'],
      timeout_seconds: 120,
    },
  },
  memory: {
    provider: 'skill_summary',
    generated_skill_dir: '~/.dojo/skills/generated',
  },
  skills: {
    dir: '~/.dojo/skills',
    generated_skill_dir: '~/.dojo/skills/generated',
    external_dirs: [],
    disabled: [],
    read_claude_skills: false,
  },
  scheduler: {
    enabled: true,
    timezone: 'Asia/Shanghai',
    store: '~/.dojo/scheduler/jobs.json',
  },
  dashboard: {
    host: '127.0.0.1',
    port: 8765,
  },
  logging: {
    level: 'INFO',
    format: '%(asctime)s %(levelname)s %(name)s: %(message)s',
    date_format: '%Y-%m-%d %H:%M:%S',
  },
  dojosdk: {
    api_key: '***',
    base_url: '',
    timeout: 60,
    max_retries: 1,
  },
};

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => {
    window.setTimeout(() => resolve(structuredClone(value) as T), API_DELAY_MS);
  });
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function deepMerge(base: SettingsConfig, patch: SettingsConfig): SettingsConfig {
  const next: SettingsConfig = { ...base };
  for (const [key, value] of Object.entries(patch)) {
    const current = next[key];
    next[key] = isPlainObject(current) && isPlainObject(value) ? deepMerge(current, value) : value;
  }
  return next;
}

export async function fetchSettingsConfig(): Promise<SettingsConfig> {
  if (USE_INTERACTIVE_MOCKS) return delay(mockConfig);
  return fetchJson<SettingsConfig>(API_URL);
}

export async function updateSettingsConfig(patch: SettingsConfig): Promise<SettingsConfig> {
  if (USE_INTERACTIVE_MOCKS) {
    mockConfig = deepMerge(mockConfig, patch);
    return delay(mockConfig);
  }

  return fetchJson<SettingsConfig>(API_URL, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
}
