// useApi — REST API request composable
import { ref } from 'vue'
import type { HealthResponse, ConfigResponse, JobInfo, ExtensionInfo } from '../types/api'

export function useApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchJSON<T>(url: string): Promise<T | null> {
    loading.value = true
    error.value = null
    try {
      const res = await fetch(url)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return await res.json() as T
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Request failed'
      return null
    } finally {
      loading.value = false
    }
  }

  async function putJSON<T>(url: string, body: unknown): Promise<T | null> {
    loading.value = true
    error.value = null
    try {
      const res = await fetch(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}))
        throw new Error((errBody as Record<string, string>).error ?? `HTTP ${res.status}`)
      }
      return await res.json() as T
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Request failed'
      return null
    } finally {
      loading.value = false
    }
  }

  async function getHealth() {
    return fetchJSON<HealthResponse>('/api/health')
  }

  async function getConfig() {
    return fetchJSON<ConfigResponse>('/api/config')
  }

  async function getJobs() {
    return fetchJSON<JobInfo[]>('/api/jobs')
  }

  async function getExtensions() {
    return fetchJSON<ExtensionInfo[]>('/api/extensions')
  }

  async function updateConfig(patch: Record<string, unknown>) {
    return putJSON<ConfigResponse>('/api/config', patch)
  }

  return { loading, error, getHealth, getConfig, updateConfig, getJobs, getExtensions }
}
