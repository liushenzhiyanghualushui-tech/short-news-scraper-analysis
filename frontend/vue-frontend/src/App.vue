<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'

const router = useRouter()
const route = useRoute()

const menuItems = [
  { path: '/', title: '仪表盘', icon: 'Odometer' },
  { path: '/news', title: '新闻分析', icon: 'Document' },
  { path: '/scrapers', title: '新闻采集', icon: 'Connection' },
  { path: '/logs', title: '采集日志', icon: 'Tickets' }
]

const isCollapse = ref(false)
const activeMenu = computed(() => route.path)

function navigate(path: string) {
  router.push(path)
}
</script>

<template>
  <el-container class="app-container">
    <!-- 侧边栏 -->
    <el-aside :width="isCollapse ? '64px' : '220px'" class="app-aside">
      <div class="logo">
        <span v-if="!isCollapse">📰 新闻采集系统</span>
        <span v-else>📰</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapse"
        background-color="#1d1e2c"
        text-color="#a0aec0"
        active-text-color="#6366f1"
        @select="navigate"
      >
        <el-menu-item v-for="item in menuItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- 主内容 -->
    <el-container>
      <el-header class="app-header">
        <el-button text @click="isCollapse = !isCollapse">
          <el-icon :size="20"><Fold v-if="!isCollapse" /><Expand v-else /></el-icon>
        </el-button>
        <div class="header-title">短新闻爬取与分析系统 v2.0</div>
        <div class="header-right">
          <el-tag type="success" effect="dark">🟢 运行中</el-tag>
        </div>
      </el-header>
      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.app-container { height: 100vh; }
.app-aside { background: #1d1e2c; overflow: hidden; }
.logo { padding: 20px; color: #fff; font-size: 16px; font-weight: bold; text-align: center; white-space: nowrap; }
.app-header { background: #fff; display: flex; align-items: center; border-bottom: 1px solid #e5e7eb; padding: 0 20px; }
.header-title { flex: 1; font-size: 18px; font-weight: 600; color: #1f2937; margin-left: 12px; }
.app-main { background: #f3f4f6; padding: 24px; }
</style>
