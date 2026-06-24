<template>
  <div class="settings-view">
    <h2>Configuration</h2>

    <div v-if="loading" class="loading">Loading...</div>
    <div v-if="error" class="error">{{ error }}</div>

    <form v-if="form" @submit.prevent="handleSave" class="settings-form">

      <!-- LLM Provider -->
      <details open class="config-section">
        <summary>LLM Provider</summary>
        <div class="section-body">
          <label class="field">
            <span>Default Provider</span>
            <input v-model="form.llm_provider.default" type="text" />
          </label>

          <div v-for="(prov, name) in form.llm_provider.providers" :key="name" class="provider-block">
            <h4>{{ name }}</h4>
            <label class="field">
              <span>Model</span>
              <input v-model="prov.model" type="text" />
            </label>
            <label class="field">
              <span>Base URL</span>
              <input v-model="prov.base_url" type="text" placeholder="https://api.openai.com/v1" />
            </label>
            <label class="field">
              <span>API Key Env</span>
              <input v-model="prov.api_key_env" type="text" placeholder="OPENAI_API_KEY" />
            </label>
            <label class="field">
              <span>API Key</span>
              <input v-model="prov.api_key" type="password" placeholder="***" />
            </label>
          </div>
        </div>
      </details>

      <!-- Agent -->
      <details class="config-section">
        <summary>Agent</summary>
        <div class="section-body">
          <label class="field">
            <span>Model</span>
            <input v-model="form.agent.model" type="text" />
          </label>
          <label class="field">
            <span>Max Iterations</span>
            <input v-model.number="form.agent.max_iterations" type="number" min="1" />
          </label>
          <label class="field">
            <span>Max Tool Workers</span>
            <input v-model.number="form.agent.max_tool_workers" type="number" min="1" />
          </label>
          <label class="field">
            <span>Default Skills (one per line)</span>
            <textarea v-model="form.agent.default_skills" rows="3"></textarea>
          </label>
          <label class="field checkbox">
            <input v-model="form.agent.lazy_skills" type="checkbox" />
            <span>Lazy Skills</span>
          </label>
          <label class="field checkbox">
            <input v-model="form.agent.enable_skill_cache" type="checkbox" />
            <span>Enable Skill Cache</span>
          </label>
          <label class="field checkbox">
            <input v-model="form.agent.enable_guardrails" type="checkbox" />
            <span>Enable Guardrails</span>
          </label>
          <label class="field checkbox">
            <input v-model="form.agent.enable_think_scrubbing" type="checkbox" />
            <span>Enable Think Scrubbing</span>
          </label>
          <label class="field checkbox">
            <input v-model="form.agent.enable_context_compression" type="checkbox" />
            <span>Enable Context Compression</span>
          </label>
        </div>
      </details>

      <!-- Multi-Agent -->
      <details class="config-section">
        <summary>Multi-Agent</summary>
        <div class="section-body">
          <label class="field checkbox">
            <input v-model="form.multi_agent.enabled" type="checkbox" />
            <span>Enabled</span>
          </label>
          <label class="field">
            <span>Max Workers</span>
            <input v-model.number="form.multi_agent.max_workers" type="number" min="1" />
          </label>
          <div class="multi-agent-list">
            <h4>Default Agents Settings</h4>
            <div v-for="(agent, idx) in form.multi_agent.default_agents" :key="idx" class="agent-setting-block">
              <h5>{{ agent.name }} ({{ agent.role }})</h5>
              <label class="field">
                <span>Model Override</span>
                <input v-model="agent.model" type="text" placeholder="e.g. gpt-4o, leave blank for default" />
              </label>
            </div>
          </div>
        </div>
      </details>

      <!-- Tools / Sandbox -->
      <details class="config-section">
        <summary>Tools / Sandbox</summary>
        <div class="section-body">
          <label class="field">
            <span>Allowed Roots (one per line)</span>
            <textarea v-model="form.tools.sandbox.allowed_roots" rows="3"></textarea>
          </label>
          <label class="field checkbox">
            <input v-model="form.tools.sandbox.allow_network" type="checkbox" />
            <span>Allow Network</span>
          </label>
          <label class="field">
            <span>Allowed Commands (one per line)</span>
            <textarea v-model="form.tools.sandbox.allowed_commands" rows="3"></textarea>
          </label>
          <label class="field">
            <span>Timeout (seconds)</span>
            <input v-model.number="form.tools.sandbox.timeout_seconds" type="number" min="1" />
          </label>
        </div>
      </details>

      <!-- Memory -->
      <details class="config-section">
        <summary>Memory</summary>
        <div class="section-body">
          <label class="field">
            <span>Provider</span>
            <input v-model="form.memory.provider" type="text" />
          </label>
          <label class="field">
            <span>Generated Skill Dir</span>
            <input v-model="form.memory.generated_skill_dir" type="text" />
          </label>
        </div>
      </details>

      <!-- Skills -->
      <details class="config-section">
        <summary>Skills</summary>
        <div class="section-body">
          <label class="field">
            <span>Skills Directory</span>
            <input v-model="form.skills.dir" type="text" />
          </label>
          <label class="field">
            <span>Generated Skill Dir</span>
            <input v-model="form.skills.generated_skill_dir" type="text" />
          </label>
          <label class="field">
            <span>External Dirs (one per line)</span>
            <textarea v-model="form.skills.external_dirs" rows="2"></textarea>
          </label>
          <label class="field">
            <span>Disabled Skills (one per line)</span>
            <textarea v-model="form.skills.disabled" rows="2"></textarea>
          </label>
          <label class="field checkbox">
            <input v-model="form.skills.read_claude_skills" type="checkbox" />
            <span>Read Claude Skills</span>
          </label>
        </div>
      </details>

      <!-- Scheduler -->
      <details class="config-section">
        <summary>Scheduler</summary>
        <div class="section-body">
          <label class="field checkbox">
            <input v-model="form.scheduler.enabled" type="checkbox" />
            <span>Enabled</span>
          </label>
          <label class="field">
            <span>Timezone</span>
            <input v-model="form.scheduler.timezone" type="text" />
          </label>
          <label class="field">
            <span>Store Path</span>
            <input v-model="form.scheduler.store" type="text" />
          </label>
        </div>
      </details>

      <!-- Dashboard -->
      <details class="config-section">
        <summary>Dashboard</summary>
        <div class="section-body">
          <label class="field">
            <span>Host</span>
            <input v-model="form.dashboard.host" type="text" />
          </label>
          <label class="field">
            <span>Port</span>
            <input v-model.number="form.dashboard.port" type="number" min="1" max="65535" />
          </label>
        </div>
      </details>

      <!-- Logging -->
      <details class="config-section">
        <summary>Logging</summary>
        <div class="section-body">
          <label class="field">
            <span>Level</span>
            <select v-model="form.logging.level">
              <option v-for="lvl in logLevels" :key="lvl" :value="lvl">{{ lvl }}</option>
            </select>
          </label>
          <label class="field">
            <span>Format</span>
            <input v-model="form.logging.format" type="text" />
          </label>
          <label class="field">
            <span>Date Format</span>
            <input v-model="form.logging.date_format" type="text" />
          </label>
        </div>
      </details>

      <!-- Dojo SDK -->
      <details class="config-section">
        <summary>Dojo SDK</summary>
        <div class="section-body">
          <label class="field">
            <span>API Key</span>
            <input v-model="form.dojosdk.api_key" type="password" placeholder="***" />
          </label>
          <label class="field">
            <span>Base URL</span>
            <input v-model="form.dojosdk.base_url" type="text" />
          </label>
          <label class="field">
            <span>Timeout (seconds)</span>
            <input v-model.number="form.dojosdk.timeout" type="number" min="1" />
          </label>
          <label class="field">
            <span>Max Retries</span>
            <input v-model.number="form.dojosdk.max_retries" type="number" min="0" />
          </label>
        </div>
      </details>

      <!-- Save bar -->
      <div class="save-bar">
        <button type="submit" :disabled="saving" class="save-btn">
          {{ saving ? 'Saving...' : 'Save Configuration' }}
        </button>
        <span v-if="saveStatus" :class="['save-status', saveStatus.type]">{{ saveStatus.message }}</span>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useApi } from '../../composables/useApi'

const { getConfig, updateConfig, loading, error } = useApi()

const logLevels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
const saving = ref(false)
const saveStatus = ref<{ type: 'success' | 'error'; message: string } | null>(null)

// Raw config from API (with api_key redacted as ***)
const rawConfig = ref<Record<string, any> | null>(null)

// Reactive form state — we normalize list fields to newline-separated strings
// for the textarea inputs, and convert back on save.
interface ProviderForm {
  model: string
  base_url: string
  api_key_env: string
  api_key: string
}

interface FormState {
  llm_provider: {
    default: string
    providers: Record<string, ProviderForm>
  }
  agent: {
    model: string
    max_iterations: number
    max_tool_workers: number
    default_skills: string // newline-separated
    lazy_skills: boolean
    enable_skill_cache: boolean
    enable_guardrails: boolean
    enable_think_scrubbing: boolean
    enable_context_compression: boolean
  }
  tools: {
    sandbox: {
      allowed_roots: string // newline-separated
      allow_network: boolean
      allowed_commands: string // newline-separated
      timeout_seconds: number
    }
  }
  memory: { provider: string; generated_skill_dir: string }
  skills: {
    dir: string
    generated_skill_dir: string
    external_dirs: string
    disabled: string
    read_claude_skills: boolean
  }
  scheduler: { enabled: boolean; timezone: string; store: string }
  dashboard: { host: string; port: number }
  logging: { level: string; format: string; date_format: string }
  dojosdk: { api_key: string; base_url: string; timeout: number; max_retries: number }
  multi_agent: {
    enabled: boolean
    max_workers: number
    default_agents: Array<{
      role: string
      name: string
      model?: string
    }>
  }
}

const form = ref<FormState | null>(null)

function arrToLines(arr: unknown): string {
  return Array.isArray(arr) ? arr.join('\n') : String(arr ?? '')
}

function linesToArr(text: string): string[] {
  return text.split('\n').map(s => s.trim()).filter(Boolean)
}

function buildForm(cfg: Record<string, any>): FormState {
  const llm = cfg.llm_provider ?? {}
  const providers: Record<string, ProviderForm> = {}
  for (const [name, prov] of Object.entries(llm.providers ?? {})) {
    const p = prov as Record<string, any>
    providers[name] = {
      model: p.model ?? '',
      base_url: p.base_url ?? '',
      api_key_env: p.api_key_env ?? '',
      api_key: p.api_key === '***' ? '' : (p.api_key ?? ''),
    }
  }
  const agent = cfg.agent ?? {}
  const sandbox = (cfg.tools ?? {}).sandbox ?? {}
  return {
    llm_provider: { default: llm.default ?? 'openai', providers },
    agent: {
      model: agent.model ?? '',
      max_iterations: agent.max_iterations ?? 8,
      max_tool_workers: agent.max_tool_workers ?? 4,
      default_skills: arrToLines(agent.default_skills),
      lazy_skills: agent.lazy_skills ?? true,
      enable_skill_cache: agent.enable_skill_cache ?? true,
      enable_guardrails: agent.enable_guardrails ?? true,
      enable_think_scrubbing: agent.enable_think_scrubbing ?? true,
      enable_context_compression: agent.enable_context_compression ?? true,
    },
    tools: {
      sandbox: {
        allowed_roots: arrToLines(sandbox.allowed_roots),
        allow_network: sandbox.allow_network ?? false,
        allowed_commands: arrToLines(sandbox.allowed_commands),
        timeout_seconds: sandbox.timeout_seconds ?? 120,
      },
    },
    memory: {
      provider: (cfg.memory ?? {}).provider ?? 'skill_summary',
      generated_skill_dir: (cfg.memory ?? {}).generated_skill_dir ?? '',
    },
    skills: {
      dir: (cfg.skills ?? {}).dir ?? '',
      generated_skill_dir: (cfg.skills ?? {}).generated_skill_dir ?? '',
      external_dirs: arrToLines((cfg.skills ?? {}).external_dirs),
      disabled: arrToLines((cfg.skills ?? {}).disabled),
      read_claude_skills: (cfg.skills ?? {}).read_claude_skills ?? false,
    },
    scheduler: {
      enabled: (cfg.scheduler ?? {}).enabled ?? true,
      timezone: (cfg.scheduler ?? {}).timezone ?? 'Asia/Shanghai',
      store: (cfg.scheduler ?? {}).store ?? '',
    },
    dashboard: {
      host: (cfg.dashboard ?? {}).host ?? '127.0.0.1',
      port: (cfg.dashboard ?? {}).port ?? 8765,
    },
    logging: {
      level: (cfg.logging ?? {}).level ?? 'INFO',
      format: (cfg.logging ?? {}).format ?? '',
      date_format: (cfg.logging ?? {}).date_format ?? '',
    },
    dojosdk: {
      api_key: (cfg.dojosdk ?? {}).api_key === '***' ? '' : ((cfg.dojosdk ?? {}).api_key ?? ''),
      base_url: (cfg.dojosdk ?? {}).base_url ?? '',
      timeout: (cfg.dojosdk ?? {}).timeout ?? 60,
      max_retries: (cfg.dojosdk ?? {}).max_retries ?? 1,
    },
    multi_agent: {
      enabled: (cfg.multi_agent ?? {}).enabled ?? false,
      max_workers: (cfg.multi_agent ?? {}).max_workers ?? 3,
      default_agents: ((cfg.multi_agent ?? {}).default_agents ?? []).map((agent: any) => ({
        role: agent.role ?? '',
        name: agent.name ?? '',
        model: agent.model ?? '',
      })),
    },
  }
}

/** Build a partial config patch from the form, omitting unchanged fields. */
function buildPatch(): Record<string, any> {
  if (!form.value || !rawConfig.value) return {}
  const f = form.value
  const patch: Record<string, any> = {}

  // LLM provider
  const provPatch: Record<string, any> = {}
  for (const [name, prov] of Object.entries(f.llm_provider.providers)) {
    const p: Record<string, any> = { model: prov.model }
    if (prov.base_url) p.base_url = prov.base_url
    if (prov.api_key_env) p.api_key_env = prov.api_key_env
    if (prov.api_key) p.api_key = prov.api_key // only send if user changed it
    provPatch[name] = p
  }
  patch.llm_provider = { default: f.llm_provider.default, providers: provPatch }

  // Agent
  patch.agent = {
    model: f.agent.model,
    max_iterations: f.agent.max_iterations,
    max_tool_workers: f.agent.max_tool_workers,
    default_skills: linesToArr(f.agent.default_skills),
    lazy_skills: f.agent.lazy_skills,
    enable_skill_cache: f.agent.enable_skill_cache,
    enable_guardrails: f.agent.enable_guardrails,
    enable_think_scrubbing: f.agent.enable_think_scrubbing,
    enable_context_compression: f.agent.enable_context_compression,
  }

  // Tools / sandbox
  patch.tools = {
    sandbox: {
      allowed_roots: linesToArr(f.tools.sandbox.allowed_roots),
      allow_network: f.tools.sandbox.allow_network,
      allowed_commands: linesToArr(f.tools.sandbox.allowed_commands),
      timeout_seconds: f.tools.sandbox.timeout_seconds,
    },
  }

  // Memory
  patch.memory = { ...f.memory }

  // Skills
  patch.skills = {
    dir: f.skills.dir,
    generated_skill_dir: f.skills.generated_skill_dir,
    external_dirs: linesToArr(f.skills.external_dirs),
    disabled: linesToArr(f.skills.disabled),
    read_claude_skills: f.skills.read_claude_skills,
  }

  // Scheduler
  patch.scheduler = { ...f.scheduler }

  // Dashboard
  patch.dashboard = { ...f.dashboard }

  // Logging
  patch.logging = { ...f.logging }

  // DojoSDK — omit api_key if not changed (it shows as ***)
  const sdkPatch: Record<string, any> = {
    base_url: f.dojosdk.base_url || null,
    timeout: f.dojosdk.timeout,
    max_retries: f.dojosdk.max_retries,
  }
  if (f.dojosdk.api_key) sdkPatch.api_key = f.dojosdk.api_key
  patch.dojosdk = sdkPatch

  // Multi-Agent
  patch.multi_agent = {
    enabled: f.multi_agent.enabled,
    max_workers: f.multi_agent.max_workers,
    default_agents: f.multi_agent.default_agents.map(agent => ({
      role: agent.role,
      name: agent.name,
      model: agent.model || null,
    })),
  }

  return patch
}

async function handleSave() {
  saving.value = true
  saveStatus.value = null
  const patch = buildPatch()
  const result = await updateConfig(patch)
  saving.value = false
  if (result) {
    saveStatus.value = { type: 'success', message: 'Configuration saved successfully.' }
    // Reload form from updated config
    rawConfig.value = result
    form.value = buildForm(result)
    setTimeout(() => { saveStatus.value = null }, 3000)
  } else {
    saveStatus.value = { type: 'error', message: error.value ?? 'Failed to save configuration.' }
  }
}

onMounted(async () => {
  const cfg = await getConfig()
  if (cfg) {
    rawConfig.value = cfg as Record<string, any>
    form.value = buildForm(cfg as Record<string, any>)
  }
})
</script>

<style scoped>
.settings-view {
  padding: 24px;
  max-width: 720px;
}
h2 {
  margin-top: 0;
}
.loading, .error {
  padding: 16px;
  color: #666;
}
.error {
  color: #c00;
}

/* Sections */
.config-section {
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  margin-bottom: 12px;
  overflow: hidden;
}
.config-section summary {
  cursor: pointer;
  padding: 12px 16px;
  font-weight: 600;
  background: #fafafa;
  user-select: none;
}
.config-section summary:hover {
  background: #f0f0f0;
}
.section-body {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* Fields */
.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.field > span {
  font-size: 0.85em;
  color: #555;
}
.field input[type="text"],
.field input[type="number"],
.field input[type="password"],
.field select,
.field textarea {
  padding: 8px 10px;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 0.9em;
  font-family: inherit;
}
.field textarea {
  resize: vertical;
}
.field.checkbox {
  flex-direction: row;
  align-items: center;
  gap: 8px;
}
.field.checkbox input[type="checkbox"] {
  width: 16px;
  height: 16px;
}

/* Provider block */
.provider-block {
  border-top: 1px solid #eee;
  padding-top: 12px;
  margin-top: 4px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.provider-block h4 {
  margin: 0;
  font-size: 0.95em;
  color: #333;
}

/* Multi-Agent styles */
.multi-agent-list {
  border-top: 1px solid #eee;
  padding-top: 12px;
  margin-top: 4px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.multi-agent-list h4 {
  margin: 0;
  font-size: 0.95em;
  color: #333;
}
.agent-setting-block {
  padding: 12px;
  background: #fcfcfc;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 8px;
}
.agent-setting-block h5 {
  margin: 0;
  font-size: 0.9em;
  color: #4b5563;
  font-weight: 600;
}

/* Save bar */
.save-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 0;
  position: sticky;
  bottom: 0;
  background: #fff;
  border-top: 1px solid #e0e0e0;
}
.save-btn {
  padding: 10px 24px;
  background: #2563eb;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 0.95em;
  cursor: pointer;
}
.save-btn:hover {
  background: #1d4ed8;
}
.save-btn:disabled {
  background: #93a3b8;
  cursor: not-allowed;
}
.save-status {
  font-size: 0.85em;
}
.save-status.success {
  color: #16a34a;
}
.save-status.error {
  color: #dc2626;
}
</style>
