<template>
  <div id="dojo-app">
    <AppLayout>
      <template #canvas>
        <div v-if="appStore.currentView === 'chat'" style="height: 100%">
          <CanvasPanel />
        </div>
        <div v-else-if="appStore.currentView === 'settings'" style="height: 100%; overflow: auto">
          <SettingsView />
        </div>
        <div v-else-if="appStore.currentView === 'scheduler'" style="height: 100%; overflow: auto">
          <SchedulerView />
        </div>
      </template>
      <template #chat>
        <ChatPanel />
      </template>
    </AppLayout>
  </div>
</template>

<script setup lang="ts">
import AppLayout from './components/layout/AppLayout.vue'
import ChatPanel from './components/chat/ChatPanel.vue'
import CanvasPanel from './components/canvas/CanvasPanel.vue'
import SettingsView from './components/settings/SettingsView.vue'
import SchedulerView from './components/scheduler/SchedulerView.vue'
import { useAppStore } from './stores/app'

const appStore = useAppStore()
</script>

<style>
#dojo-app {
  height: 100vh;
  overflow: hidden;
}
</style>
