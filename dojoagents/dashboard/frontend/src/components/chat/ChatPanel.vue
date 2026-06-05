<template>
  <div class="chat-panel">
    <div class="chat-header">
      <h3>Chatbot</h3>
      <button @click="session.newSession()" title="New session">🔄</button>
    </div>
    <div ref="messagesContainer" class="messages">
      <ChatMessage
        v-for="(msg, i) in chatStore.messages"
        :key="i"
        :message="msg"
      />
      <ChatToolStatus :is-streaming="chatStore.isStreaming" />
    </div>
    <ChatInput :disabled="chatStore.isStreaming" @send="handleSend" />
    <div v-if="chatError" class="error-bar">{{ chatError }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { useChatStore } from '../../stores/chat'
import { useChat } from '../../composables/useChat'
import { useSession } from '../../composables/useSession'
import ChatMessage from './ChatMessage.vue'
import ChatInput from './ChatInput.vue'
import ChatToolStatus from './ChatToolStatus.vue'

const chatStore = useChatStore()
const { sendMessage, error: chatError } = useChat()
const session = useSession()
const messagesContainer = ref<HTMLElement | null>(null)

async function handleSend(text: string) {
  await sendMessage(text)
  await nextTick()
  scrollToBottom()
}

function scrollToBottom() {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}
</script>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #e0e0e0;
  background: #fff;
}
.chat-header h3 {
  margin: 0;
  font-size: 1em;
}
.chat-header button {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 1.1em;
}
.messages {
  flex: 1;
  overflow-y: auto;
}
.error-bar {
  padding: 8px 16px;
  background: #fee;
  color: #c00;
  font-size: 0.85em;
}
</style>
