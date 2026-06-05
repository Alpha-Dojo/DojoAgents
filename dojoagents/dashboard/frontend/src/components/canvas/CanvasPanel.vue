<template>
  <div class="canvas-panel">
    <div class="canvas-header">
      <h3>Canvas</h3>
    </div>
    <div class="canvas-body">
      <CanvasSandbox
        v-if="canvasStore.pendingRender || canvasStore.renderHistory.length > 0"
        ref="sandboxRef"
        template-url="/canvas-template.html"
        @ready="onSandboxReady"
      />
      <CanvasPlaceholder v-else />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, toRaw } from 'vue'
import { useCanvasStore } from '../../stores/canvas'
import CanvasSandbox from './CanvasSandbox.vue'
import CanvasPlaceholder from './CanvasPlaceholder.vue'

const canvasStore = useCanvasStore()
const sandboxRef = ref<InstanceType<typeof CanvasSandbox> | null>(null)
const iframeReady = ref(false)

// Reset iframeReady when sandbox is destroyed (v-if becomes false)
watch(sandboxRef, (newVal) => {
  if (!newVal) {
    iframeReady.value = false
  }
})

/** Called when the iframe's SANDBOX_READY message arrives. */
function onSandboxReady() {
  iframeReady.value = true
  // If a render was queued while the iframe was loading, send it now
  flushPendingRender()
}

/** Send the pending render to the iframe if it's ready. */
async function flushPendingRender() {
  const payload = canvasStore.pendingRender
  if (!payload) return
  await nextTick()
  // Re-check after await — state may have changed during the yield
  if (!iframeReady.value) return
  const iframeEl = sandboxRef.value?.iframeEl
  if (iframeEl?.contentWindow) {
    iframeEl.contentWindow.postMessage({
      type: 'RENDER',
      script: payload.script,
      data: toRaw(payload.data),
    }, '*')
  }
  canvasStore.markRendered()
}

// When a new pending render arrives, try to flush immediately (iframe may already be ready)
watch(
  () => canvasStore.pendingRender,
  (payload) => {
    if (payload && iframeReady.value) {
      flushPendingRender()
    }
  },
)
</script>

<style scoped>
.canvas-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.canvas-header {
  padding: 12px 16px;
  border-bottom: 1px solid #e0e0e0;
  background: #fff;
}
.canvas-header h3 {
  margin: 0;
  font-size: 1em;
}
.canvas-body {
  flex: 1;
  overflow: hidden;
}
</style>
