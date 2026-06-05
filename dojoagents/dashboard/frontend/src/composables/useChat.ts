// useChat — core SSE streaming chat composable
import { ref } from 'vue'
import { useChatStore } from '../stores/chat'
import { useCanvasStore } from '../stores/canvas'
import { parseSSEStream } from '../utils/sse-parser'
import { extractDojoChart } from '../utils/chartParser'
import type { ChatCompletionRequest } from '../types/openai'

export function useChat() {
  const chatStore = useChatStore()
  const canvasStore = useCanvasStore()
  const isStreaming = ref(false)
  const error = ref<string | null>(null)

  async function sendMessage(userInput: string) {
    if (!userInput.trim() || isStreaming.value) return

    error.value = null
    chatStore.addMessage({ role: 'user', content: userInput })
    isStreaming.value = true
    chatStore.isStreaming = true

    const request: ChatCompletionRequest = {
      model: 'gpt-4.1',
      messages: chatStore.messages,
      stream: true,
      metadata: {
        session_id: chatStore.sessionId,
        channel: 'dashboard',
      },
    }

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      let chartRendered = false
      chatStore.addMessage({ role: 'assistant', content: '' })

      for await (const event of parseSSEStream(response)) {
        switch (event.type) {
          case 'content_delta':
            if (event.content) {
              chatStore.appendToLastAssistant(event.content)
              // Check for DOJO_CHART block in the accumulated assistant text (once)
              if (!chartRendered) {
                const lastMsg = chatStore.messages[chatStore.messages.length - 1]
                if (lastMsg?.role === 'assistant' && lastMsg.content) {
                  const payload = extractDojoChart(lastMsg.content)
                  if (payload) {
                    canvasStore.setPendingRender(payload)
                    chartRendered = true
                  }
                }
              }
            }
            break
          case 'tool_call_delta':
            // Tool calls are internal to the Agent loop; no frontend action needed.
            break
          case 'message_end':
            break
          case 'done':
            break
          case 'error':
            error.value = event.error?.message || 'Stream error'
            break
        }
      }
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Unknown error'
    } finally {
      isStreaming.value = false
      chatStore.isStreaming = false
    }
  }

  return { sendMessage, isStreaming, error }
}
