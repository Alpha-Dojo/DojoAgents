// SSE stream parser using fetch + ReadableStream
import type { ChatCompletionChunk } from '../types/openai'

export type SSEEventType = 'content_delta' | 'tool_call_delta' | 'message_end' | 'done' | 'error'

export interface SSEEvent {
  type: SSEEventType
  chunk?: ChatCompletionChunk
  content?: string
  error?: Error
}

export async function* parseSSEStream(
  response: Response,
): AsyncGenerator<SSEEvent, void, unknown> {
  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed || !trimmed.startsWith('data:')) continue

        const data = trimmed.slice(5).trim()
        if (data === '[DONE]') {
          yield { type: 'done' }
          return
        }

        try {
          const chunk: ChatCompletionChunk = JSON.parse(data)
          const delta = chunk.choices[0]?.delta
          const finishReason = chunk.choices[0]?.finish_reason

          if (delta?.content) {
            yield { type: 'content_delta', content: delta.content, chunk }
          }
          if (delta?.tool_calls) {
            yield { type: 'tool_call_delta', chunk }
          }
          if (finishReason) {
            yield { type: 'message_end', chunk }
          }
        } catch (e) {
          yield { type: 'error', error: new Error(`SSE parse error: ${e}`) }
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}
