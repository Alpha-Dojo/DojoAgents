<template>
  <div class="canvas-sandbox">
    <iframe
      ref="iframeEl"
      :src="templateUrl"
      sandbox="allow-scripts"
      class="sandbox-iframe"
      title="Canvas Sandbox"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const props = defineProps<{ templateUrl?: string }>()
const emit = defineEmits<{ (e: 'ready'): void }>()
const iframeEl = ref<HTMLIFrameElement | null>(null)

function handleMessage(event: MessageEvent) {
  if (event.data?.type === 'SANDBOX_READY') {
    emit('ready')
  }
}

onMounted(() => {
  window.addEventListener('message', handleMessage)
})

onUnmounted(() => {
  window.removeEventListener('message', handleMessage)
})

defineExpose({ iframeEl })
</script>

<style scoped>
.canvas-sandbox {
  width: 100%;
  height: 100%;
}
.sandbox-iframe {
  width: 100%;
  height: 100%;
  border: none;
}
</style>
