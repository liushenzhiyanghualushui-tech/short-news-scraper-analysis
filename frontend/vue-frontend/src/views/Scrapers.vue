<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { spiderApi } from '@/api'
import { ElMessage } from 'element-plus'

const spiders = ref<any>({})
const sources = ref<any[]>([])
const runningAll = ref(false)
const runningSingle = ref<Record<string, boolean>>({})

async function fetchData() {
  const [listRes, srcRes] = await Promise.all([
    spiderApi.list(),
    spiderApi.sources()
  ])
  spiders.value = (listRes as any).data || {}
  sources.value = (srcRes as any).data || []
}

async function runSingle(code: string) {
  runningSingle.value[code] = true
  try {
    await spiderApi.start(code)
    ElMessage.success(`${code} 爬取任务已启动`)
  } catch (e) {
    ElMessage.error(`${code} 启动失败`)
  } finally {
    runningSingle.value[code] = false
  }
}

async function runAll() {
  runningAll.value = true
  try {
    await spiderApi.runAll()
    ElMessage.success('全量爬取已调度！所有来源并行执行中...')
  } catch (e) {
    ElMessage.error('调度失败')
  } finally {
    runningAll.value = false
  }
}

onMounted(fetchData)
</script>

<template>
  <div class="scrapers-page">
    <el-card>
      <template #header>
        <div style="display:flex; justify-content:space-between; align-items:center">
          <span>🕷 爬虫管理</span>
          <el-button type="primary" :loading="runningAll" @click="runAll">
            🚀 一键全爬
          </el-button>
        </div>
      </template>

      <el-table :data="sources" stripe size="small">
        <el-table-column label="来源" width="120">
          <template #default="{ row }">
            <el-tag :type="row.scraperType === 'java' ? 'success' : 'warning'">
              {{ row.name }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="code" label="编码" width="120" />
        <el-table-column label="引擎" width="120">
          <template #default="{ row }">
            {{ row.scraperType === 'java' ? '☕ Java虚拟线程' : '🐍 Python/FastAPI' }}
          </template>
        </el-table-column>
        <el-table-column label="并发限制" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ row.concurrentLimit }} 线程</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="速率限制" width="120">
          <template #default="{ row }">
            {{ row.rateLimitMs }}ms/请求
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.isActive ? 'success' : 'danger'" size="small">
              {{ row.isActive ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button 
              size="small" 
              type="primary" 
              :loading="runningSingle[row.code]"
              @click="runSingle(row.code)">
              执行
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 引擎对比 -->
    <el-row :gutter="20" style="margin-top:20px">
      <el-col :span="12">
        <el-card>
          <template #header>☕ Java引擎爬虫 (虚拟线程)</template>
          <div v-for="(type, code) in spiders" :key="code">
            <el-tag v-if="type === 'java'" style="margin:4px">{{ code }}</el-tag>
          </div>
          <el-alert type="success" :closable="false" style="margin-top:12px">
            OkHttp + Jsoup · 虚拟线程 · 令牌桶限流 · 高并发
          </el-alert>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <template #header>🐍 Python引擎爬虫 (FastAPI委托)</template>
          <div v-for="(type, code) in spiders" :key="code">
            <el-tag v-if="type === 'python'" type="warning" style="margin:4px">{{ code }}</el-tag>
          </div>
          <el-alert type="warning" :closable="false" style="margin-top:12px">
            aiohttp · Selenium · 代理轮换 · 异步混合
          </el-alert>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>
