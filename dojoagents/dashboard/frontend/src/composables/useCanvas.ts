// useCanvas — Canvas iframe communication composable
import { ref, watch } from 'vue'
import { useCanvasStore } from '../stores/canvas'

export function useCanvas() {
  const canvasStore = useCanvasStore()
  const iframeRef = ref<HTMLIFrameElement | null>(null)

  watch(
    () => canvasStore.pendingRender,
    (payload) => {
      if (payload && iframeRef.value?.contentWindow) {
        iframeRef.value.contentWindow.postMessage({
          type: 'RENDER',
          script: payload.script,
          data: payload.data,
        }, '*')
        canvasStore.markRendered()
      }
    },
  )

  return { iframeRef }
}
