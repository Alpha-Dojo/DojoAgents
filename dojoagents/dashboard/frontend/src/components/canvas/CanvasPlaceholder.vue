<template>
  <div class="canvas-placeholder">
    <div class="placeholder-content">
      <span class="icon">📊</span>
      <p>No chart to display yet.</p>
      <p class="hint">Ask the agent to analyze data and display charts.</p>
    </div>
  </div>
</template>

<style scoped>
.canvas-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #999;
}
.placeholder-content {
  text-align: center;
}
.icon {
  font-size: 3em;
  display: block;
  margin-bottom: 16px;
}
.hint {
  font-size: 0.85em;
  color: #bbb;
}
</style>
