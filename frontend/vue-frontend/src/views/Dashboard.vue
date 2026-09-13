<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAppStore } from '@/stores/app'
import { spiderApi } from '@/api'
import { ElMessage } from 'element-plus'

const store = useAppStore()
const runningAll = ref(false)
const chartRef = ref()

onMounted(() => {
  store.fetchDashboard()
})

async function runAllScrapers() {
  runningAll.value = true
  try {
    await spiderApi.runAll()
    ElMessage.success('全量爬取任务已调度！')
    setTimeout(() => store.fetchDashboard(), 3000)
  } catch (e) {
    ElMessage.error('任务调度失败')
  } finally {
    runningAll.value = false
  }
}
</script>

<template>
  <div class="dashboard">
    <!-- 统计卡片 -->
    <el-row :gutter="20">
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value">{{ store.stats?.total_articles || 0 }}</div>
          <div class="stat-label">总文章数</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value">{{ store.stats?.articles_24h || 0 }}</div>
          <div class="stat-label">24小时新增</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value">{{ store.spiderStatus?.java_sources?.length || 0 }}</div>
          <div class="stat-label">Java爬虫源</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value">{{ store.spiderStatus?.python_sources?.length || 0 }}</div>
          <div class="stat-label">Python爬虫源</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 快捷操作 -->
    <el-card class="action-card" style="margin-top: 20px">
      <template #header>
        <span>⚡ 快捷操作</span>
      </template>
      <el-space>
        <el-button type="primary" :loading="runningAll" @click="runAllScrapers">
          🚀 一键全爬 (Java虚拟线程 + Python委托)
        </el-button>
        <el-button @click="store.fetchDashboard()">🔄 刷新数据</el-button>
      </el-space>
    </el-card>

    <!-- 来源统计 -->
    <el-card style="margin-top: 20px">
      <template #header>
        <span>📊 来源分布统计</span>
      </template>
      <el-table :data="store.stats?.by_source ? 
        Object.entries(store.stats.by_source).map(([k,v]) => ({code: k, ...v})) : []" 
        stripe size="small">
        <el-table-column prop="code" label="来源" width="120" />
        <el-table-column prop="name" label="名称" width="150" />
        <el-table-column prop="count" label="文章数" />
      </el-table>
    </el-card>

    <!-- 架构说明 -->
    <el-card style="margin-top: 20px">
      <template #header>
        <span>🏗️ 爬虫并发架构</span>
      </template>
      <el-alert type="info" :closable="false" show-icon>
        <template #title>
          Java虚拟线程 (轻量HTTP爬虫) vs Python FastAPI (重型浏览器爬虫)
        </template>
        <div style="margin-top: 8px; font-size: 13px; color: #666">
          <p>• <b>Java爬虫</b>: sina(50并发) tencent(40) netease(40) chinanews(30) pengpai(30) — OkHttp + Jsoup + 虚拟线程</p>
          <p>• <b>Python爬虫</b>: xinhua(aiohttp+Selenium) ifeng(多阶段+代理) cankaoxiaoxi(Selenium) — 委托FastAPI</p>
          <p>• <b>编排引擎</b>: ScraperOrchestrator — CompletableFuture + Virtual Threads — 所有来源并行执行</p>
        </div>
      </el-alert>
    </el-card>
  </div>
</template>

<style scoped>
.stat-card { text-align: center; }
.stat-value { font-size: 32px; font-weight: bold; color: #6366f1; }
.stat-label { font-size: 13px; color: #6b7280; margin-top: 8px; }
</style>
