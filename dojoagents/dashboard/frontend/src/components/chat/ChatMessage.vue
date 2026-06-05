<template>
  <div class="chat-message" :class="[`role-${message.role}`]">
    <div class="avatar">{{ message.role === 'user' ? '👤' : '🤖' }}</div>
    <div class="content" v-html="renderedContent" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ChatMessage } from '../../types/openai'
import { renderMarkdown } from '../../utils/markdown'

const props = defineProps<{ message: ChatMessage }>()

const renderedContent = computed(() => {
  const text = props.message.content || ''
  if (!text) return '<em>typing...</em>'
  return renderMarkdown(text)
})
</script>

<style scoped>
.chat-message {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  max-width: 100%;
}
.role-user {
  background: #f0f4ff;
}
.role-assistant {
  background: #fff;
}
.avatar {
  font-size: 1.2em;
  flex-shrink: 0;
}
.content {
  flex: 1;
  overflow-wrap: break-word;
  line-height: 1.5;
}
.content :deep(pre) {
  background: #f5f5f5;
  padding: 8px;
  border-radius: 4px;
  overflow-x: auto;
}
.content :deep(code) {
  font-size: 0.9em;
}
</style>
