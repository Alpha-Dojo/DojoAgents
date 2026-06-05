<template>
  <div class="scheduler-view">
    <h2>Scheduled Jobs</h2>
    <div v-if="loading" class="loading">Loading...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else-if="!jobs || jobs.length === 0" class="empty">No scheduled jobs.</div>
    <table v-else class="jobs-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>Name</th>
          <th>Schedule</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="job in jobs" :key="job.id">
          <td>{{ job.id }}</td>
          <td>{{ job.name }}</td>
          <td>{{ JSON.stringify(job.schedule) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useApi } from '../../composables/useApi'
import type { JobInfo } from '../../types/api'

const { getJobs, loading, error } = useApi()
const jobs = ref<JobInfo[] | null>(null)

onMounted(async () => {
  jobs.value = await getJobs()
})
</script>

<style scoped>
.scheduler-view {
  padding: 24px;
}
h2 {
  margin-top: 0;
}
.loading, .error, .empty {
  padding: 16px;
  color: #666;
}
.error {
  color: #c00;
}
.jobs-table {
  width: 100%;
  border-collapse: collapse;
}
.jobs-table th,
.jobs-table td {
  padding: 10px 16px;
  text-align: left;
  border-bottom: 1px solid #e0e0e0;
}
.jobs-table th {
  background: #f5f5f5;
  font-weight: 600;
}
</style>
