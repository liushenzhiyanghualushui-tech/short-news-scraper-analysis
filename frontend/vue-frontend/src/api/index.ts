import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 300000  // 5分钟超时（爬虫可能慢）
})

// 响应拦截器
api.interceptors.response.use(
  res => res.data,
  err => {
    console.error('API Error:', err.message)
    return Promise.reject(err)
  }
)

// ===== 仪表盘 =====
export const dashboardApi = {
  getStats: () => api.get('/dashboard/stats')
}

// ===== 新闻 =====
export const newsApi = {
  list: (params: any) => api.get('/news/list', { params }),
  detail: (id: number) => api.get(`/news/detail/${id}`)
}

// ===== 爬虫管理 =====
export const spiderApi = {
  list: () => api.get('/spider/list'),
  sources: () => api.get('/spider/sources'),
  start: (sourceCode: string) => api.post('/spider/start', { sourceCode }),
  runAll: () => api.post('/spider/run-all'),
  status: () => api.get('/spider/status'),
  logs: (limit = 50) => api.get('/spider/logs', { params: { limit } })
}

// ===== 健康检查 =====
export const healthApi = {
  check: () => api.get('/health')
}

export default api
