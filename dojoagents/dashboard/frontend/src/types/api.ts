// Backend API response types

export interface HealthResponse {
  ok: boolean
}

export interface ConfigResponse {
  [key: string]: unknown
}

export interface JobInfo {
  id: string
  name: string
  schedule: Record<string, unknown>
  [key: string]: unknown
}

export interface ExtensionInfo {
  name: string
  [key: string]: unknown
}
