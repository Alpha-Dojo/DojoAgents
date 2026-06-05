<template>
  <aside class="sidebar" :class="{ collapsed: appStore.sidebarCollapsed }">
    <button class="toggle-btn" @click="appStore.toggleSidebar">
      {{ appStore.sidebarCollapsed ? '▶' : '◀' }}
    </button>
    <nav v-show="!appStore.sidebarCollapsed">
      <ul>
        <li :class="{ active: appStore.currentView === 'chat' }" @click="appStore.setView('chat')">
          💬 Chatbot
        </li>
        <li :class="{ active: appStore.currentView === 'settings' }" @click="appStore.setView('settings')">
          ⚙️ Settings
        </li>
        <li :class="{ active: appStore.currentView === 'scheduler' }" @click="appStore.setView('scheduler')">
          📅 Scheduler
        </li>
      </ul>
    </nav>
  </aside>
</template>

<script setup lang="ts">
import { useAppStore } from '../../stores/app'

const appStore = useAppStore()
</script>

<style scoped>
.sidebar {
  width: 200px;
  background: #1a1a2e;
  color: #eee;
  display: flex;
  flex-direction: column;
  transition: width 0.3s;
  overflow: hidden;
}
.sidebar.collapsed {
  width: 40px;
}
.toggle-btn {
  background: none;
  border: none;
  color: #eee;
  cursor: pointer;
  padding: 8px;
  text-align: center;
}
nav ul {
  list-style: none;
  padding: 0;
  margin: 0;
}
nav li {
  padding: 12px 16px;
  cursor: pointer;
  transition: background 0.2s;
}
nav li:hover {
  background: #16213e;
}
nav li.active {
  background: #0f3460;
}
</style>
