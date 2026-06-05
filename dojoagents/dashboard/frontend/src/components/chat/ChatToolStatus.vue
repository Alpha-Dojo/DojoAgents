<template>
  <div v-if="isStreaming" class="tool-status">
    <span class="spinner">⏳</span>
    <span>Agent is thinking...</span>
  </div>
</template>

<script setup lang="ts">
defineProps<{ isStreaming: boolean }>()
</script>

<style scoped>
.tool-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  color: #666;
  font-size: 0.85em;
}
.spinner {
  animation: spin 1s linear infinite;
  display: inline-block;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
