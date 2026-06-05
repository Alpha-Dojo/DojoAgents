<template>
  <div class="chat-input">
    <textarea
      v-model="inputText"
      placeholder="Type your message... (Enter to send, Shift+Enter for newline)"
      :disabled="disabled"
      @keydown.enter.exact.prevent="send"
      rows="2"
    />
    <button @click="send" :disabled="disabled || !inputText.trim()">
      {{ disabled ? 'Streaming...' : 'Send' }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{ disabled?: boolean }>()
const emit = defineEmits<{ send: [text: string] }>()

const inputText = ref('')

function send() {
  const text = inputText.value.trim()
  if (!text || props.disabled) return
  emit('send', text)
  inputText.value = ''
}
</script>

<style scoped>
.chat-input {
  display: flex;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid #e0e0e0;
  background: #fff;
}
textarea {
  flex: 1;
  resize: none;
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 14px;
  font-family: inherit;
}
button {
  padding: 8px 16px;
  background: #0f3460;
  color: #fff;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
}
button:disabled {
  background: #999;
  cursor: not-allowed;
}
</style>
