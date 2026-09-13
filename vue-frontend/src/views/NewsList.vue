<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { newsApi } from '@/api'
import dayjs from 'dayjs'

const articles = ref<any[]>([])
const total = ref(0)
const page = ref(0)
const loading = ref(false)
const searchKeyword = ref('')
const filterSource = ref('')

const sources = ['', 'sina', 'tencent', 'netease', 'chinanews', 'pengpai', 'xinhua', 'ifeng', 'cankaoxiaoxi']
const sourceLabels: Record<string, string> = {
  '': '全部', sina: '新浪', tencent: '腾讯', netease: '网易', chinanews: '中新网',
  pengpai: '澎湃', xinhua: '新华网', ifeng: '凤凰', cankaoxiaoxi: '参考消息'
}

async function fetchNews() {
  loading.value = true
  try {
    const res: any = await newsApi.list({
      sourceCode: filterSource.value,
      keyword: searchKeyword.value,
      page: page.value,
      size: 20
    })
    articles.value = res.data || []
    total.value = res.total || 0
  } finally {
    loading.value = false
  }
}

function formatTime(t: string) {
  return t ? dayjs(t).format('MM-DD HH:mm') : '-'
}

function truncate(text: string, len = 80) {
  if (!text) return ''
  return text.length > len ? text.slice(0, len) + '...' : text
}

onMounted(fetchNews)
</script>

<template>
  <div class="news-page">
    <el-card>
      <template #header>
        <div style="display:flex; justify-content:space-between; align-items:center">
          <span>📋 新闻列表 ({{ total }} 条)</span>
          <el-space>
            <el-select v-model="filterSource" placeholder="来源" @change="fetchNews" style="width:120px">
              <el-option v-for="s in sources" :key="s" :label="sourceLabels[s]" :value="s" />
            </el-select>
            <el-input v-model="searchKeyword" placeholder="搜索..." clearable 
              @clear="fetchNews" @keyup.enter="fetchNews" style="width:200px" />
            <el-button @click="fetchNews">搜索</el-button>
          </el-space>
        </div>
      </template>

      <el-table :data="articles" stripe v-loading="loading" size="small" max-height="calc(100vh - 280px)">
        <el-table-column prop="title" label="标题" min-width="300" show-overflow-tooltip />
        <el-table-column prop="sourceName" label="来源" width="100" />
        <el-table-column prop="category" label="分类" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.category" size="small" type="info">{{ row.category }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="发布时间" width="130">
          <template #default="{ row }">{{ formatTime(row.publishTime) }}</template>
        </el-table-column>
        <el-table-column label="摘要" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ truncate(row.description || row.content) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="window.open(row.url, '_blank')">原文</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div style="margin-top:16px; text-align:right">
        <el-pagination 
          v-model:current-page="page" 
          :total="total" 
          :page-size="20"
          layout="prev, pager, next" 
          @current-change="fetchNews" />
      </div>
    </el-card>
  </div>
</template>
