export interface ProviderForm {
  model: string;
  base_url: string;
  api_key_env: string;
  api_key: string;
}

export interface SettingsFormState {
  llm_provider: {
    default: string;
    providers: Record<string, ProviderForm>;
  };
  agent: {
    model: string;
    max_iterations: number;
    max_tool_workers: number;
    default_skills: string;
    lazy_skills: boolean;
    enable_skill_cache: boolean;
    enable_guardrails: boolean;
    enable_think_scrubbing: boolean;
    enable_context_compression: boolean;
  };
  tools: {
    sandbox: {
      allowed_roots: string;
      allow_network: boolean;
      allowed_commands: string;
      timeout_seconds: number;
    };
  };
  memory: { provider: string; generated_skill_dir: string };
  skills: {
    dir: string;
    generated_skill_dir: string;
    external_dirs: string;
    disabled: string;
    read_claude_skills: boolean;
  };
  scheduler: { enabled: boolean; timezone: string; store: string };
  dashboard: { host: string; port: number };
  logging: { level: string; format: string; date_format: string };
  dojosdk: { api_key: string; base_url: string; timeout: number; max_retries: number };
  multi_agent: {
    enabled: boolean;
    max_workers: number;
    default_agents: Array<{
      role: string;
      name: string;
      model?: string;
    }>;
  };
}

export type SettingsConfig = Record<string, unknown>;
