// Chat store — conversation state management
import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { ChatMessage } from '../types/openai'

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const sessionId = ref(crypto.randomUUID())
  const isStreaming = ref(false)

  function addMessage(msg: ChatMessage) {
    messages.value.push(msg)
  }

  function appendToLastAssistant(text: string) {
    const last = messages.value[messages.value.length - 1]
    if (last?.role === 'assistant') {
      last.content = (last.content || '') + text
    }
  }

  function clearHistory() {
    messages.value = []
    sessionId.value = crypto.randomUUID()
  }

  return { messages, sessionId, isStreaming, addMessage, appendToLastAssistant, clearHistory }
})
