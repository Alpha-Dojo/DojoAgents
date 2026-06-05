// Canvas store — chart rendering state management
// Driven by DOJO_CHART blocks parsed from Agent text responses.
import { ref } from 'vue'
import { defineStore } from 'pinia'

export interface PendingRender {
  data: unknown
  script: string
}

export interface RenderHistoryEntry {
  data: unknown
  script: string
  timestamp: number
}

export const useCanvasStore = defineStore('canvas', () => {
  const pendingRender = ref<PendingRender | null>(null)
  const renderHistory = ref<RenderHistoryEntry[]>([])

  /** Called by useChat() when a DOJO_CHART block is parsed from the text stream. */
  function setPendingRender(payload: PendingRender) {
    pendingRender.value = payload
  }

  /** Called by useCanvas() after postMessage is sent to the iframe. */
  function markRendered() {
    if (pendingRender.value) {
      renderHistory.value.push({
        data: pendingRender.value.data,
        script: pendingRender.value.script,
        timestamp: Date.now(),
      })
      pendingRender.value = null
    }
  }

  /** Clear the pending render without recording to history. */
  function clearCanvas() {
    pendingRender.value = null
  }

  return {
    pendingRender,
    renderHistory,
    setPendingRender,
    markRendered,
    clearCanvas,
  }
})
