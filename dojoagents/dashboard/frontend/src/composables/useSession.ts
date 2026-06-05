// useSession — session management composable
import { useChatStore } from '../stores/chat'

export function useSession() {
  const chatStore = useChatStore()

  function newSession() {
    chatStore.clearHistory()
  }

  function getSessionId(): string {
    return chatStore.sessionId
  }

  return { newSession, getSessionId }
}
