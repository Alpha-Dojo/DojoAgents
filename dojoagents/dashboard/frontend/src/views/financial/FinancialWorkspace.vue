<template>
  <div class="financial-workspace">
    <div class="tabs">
      <button 
        :class="{ active: currentTab === 'dojo-core' }"
        @click="switchTab('dojo-core')"
      >DojoCore</button>
      <button 
        :class="{ active: currentTab === 'dojo-mesh' }"
        @click="switchTab('dojo-mesh')"
      >DojoMesh</button>
      <button 
        :class="{ active: currentTab === 'dojo-sphere' }"
        @click="switchTab('dojo-sphere')"
      >DojoSphere</button>
      <button 
        :class="{ active: currentTab === 'dojo-folio' }"
        @click="switchTab('dojo-folio')"
      >DojoFolio</button>
    </div>
    
    <div class="workspace-content">
      <div v-if="currentTab === 'dojo-core'">DojoCore Placeholder</div>
      <div v-if="currentTab === 'dojo-mesh'">DojoMesh Placeholder</div>
      <div v-if="currentTab === 'dojo-sphere'">DojoSphere Placeholder</div>
      <div v-if="currentTab === 'dojo-folio'">DojoFolio Placeholder</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useFinancialContextStore } from '../../stores/financial/context';

const contextStore = useFinancialContextStore();
const currentTab = computed(() => contextStore.dashboard_tab);

const switchTab = (tab: string) => {
  contextStore.setTab(tab);
};
</script>

<style scoped>
.financial-workspace {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.tabs {
  display: flex;
  gap: 1rem;
  padding: 1rem;
  background-color: var(--bg-color, #1e1e1e);
  border-bottom: 1px solid var(--border-color, #333);
}

.tabs button {
  background: none;
  border: none;
  color: var(--text-color, #ccc);
  padding: 0.5rem 1rem;
  cursor: pointer;
  border-radius: 4px;
}

.tabs button.active {
  background-color: var(--primary-color, #007bff);
  color: white;
}

.workspace-content {
  flex: 1;
  padding: 1rem;
  overflow-y: auto;
}
</style>
