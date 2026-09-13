import { defineStore } from 'pinia'
import { ref } from 'vue'
import { dashboardApi, spiderApi } from '@/api'

export const useAppStore = defineStore('app', () => {
  const stats = ref<any>({})
  const spiderStatus = ref<any>({})
  const loading = ref(false)

  async function fetchDashboard() {
    loading.value = true
    try {
      const [statsRes, statusRes] = await Promise.all([
        dashboardApi.getStats(),
        spiderApi.status()
      ])
      stats.value = (statsRes as any).data || {}
      spiderStatus.value = (statusRes as any).data || {}
    } finally {
      loading.value = false
    }
  }

  return { stats, spiderStatus, loading, fetchDashboard }
})
