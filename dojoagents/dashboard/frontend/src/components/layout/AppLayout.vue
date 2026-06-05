<template>
  <div class="app-layout">
    <AppSidebar />
    <main class="main-content">
      <div class="canvas-area">
        <slot name="canvas" />
      </div>
      <div class="chat-area">
        <slot name="chat" />
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import AppSidebar from './AppSidebar.vue'
</script>

<style scoped>
.app-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}
.main-content {
  flex: 1;
  display: flex;
  overflow: hidden;
}
.canvas-area {
  flex: 1;
  overflow: auto;
  background: #f5f5f5;
}
.chat-area {
  width: 400px;
  min-width: 300px;
  display: flex;
  flex-direction: column;
  border-left: 1px solid #e0e0e0;
}
</style>
