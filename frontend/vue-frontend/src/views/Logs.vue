<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { spiderApi } from '@/api'
import dayjs from 'dayjs'

const logs = ref<any[]>([])
const loading = ref(false)

async function fetchLogs() {
  loading.value = true
  try {
    const res: any = await spiderApi.logs(100)
    logs.value = res.data || []
  } finally {
    loading.value = false
  }
}

function formatTime(t: string) { return t ? dayjs(t).format('MM-DD HH:mm:ss') : '-' }

onMounted(fetchLogs)
</script>

<template>
  <div class="logs-page">
    <el-card>
      <template #header>
        <div style="display:flex; justify-content:space-between">
          <span>📋 采集日志</span>
          <el-button @click="fetchLogs">🔄 刷新</el-button>
        </div>
      </template>
      <el-table :data="logs" stripe v-loading="loading" size="small" max-height="calc(100vh - 250px)">
        <el-table-column prop="spiderName" label="爬虫" width="120" />
        <el-table-column label="引擎" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.executor === 'java' ? 'success' : 'warning'">
              {{ row.executor }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'success' ? 'success' : row.status === 'failed' ? 'danger' : 'info'">
              {{ row.status === 'success' ? '成功' : row.status === 'failed' ? '失败' : '运行中' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="itemsCount" label="采集数" width="90" />
        <el-table-column prop="duration" label="耗时(s)" width="90">
          <template #default="{ row }">{{ row.duration }}s</template>
        </el-table-column>
        <el-table-column label="开始时间" width="160">
          <template #default="{ row }">{{ formatTime(row.startTime) }}</template>
        </el-table-column>
        <el-table-column label="结束时间" width="160">
          <template #default="{ row }">{{ formatTime(row.endTime) }}</template>
        </el-table-column>
        <el-table-column prop="errorMessage" label="错误信息" min-width="200" show-overflow-tooltip />
      </el-table>
    </el-card>
  </div>
</template>
