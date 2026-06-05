// App store — global UI state
import { ref } from 'vue'
import { defineStore } from 'pinia'

export const useAppStore = defineStore('app', () => {
  const sidebarCollapsed = ref(false)
  const currentView = ref<'chat' | 'settings' | 'scheduler'>('chat')

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function setView(view: 'chat' | 'settings' | 'scheduler') {
    currentView.value = view
  }

  return { sidebarCollapsed, currentView, toggleSidebar, setView }
})
