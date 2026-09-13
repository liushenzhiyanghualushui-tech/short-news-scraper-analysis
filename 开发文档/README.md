# 开发文档

本目录包含短新闻爬取与分析系统的所有开发相关文档。

---

## 目录

| 文档 | 说明 |
|------|------|
| [MIGRATION.md](./MIGRATION.md) | 项目重构迁移指南，指导目录重组和服务迁移步骤 |

---

## MIGRATION.md

**项目重构迁移指南**提供了从当前架构迁移到新架构的详细步骤：

- Phase 1：准备与备份
- Phase 2：创建模块目录
- Phase 3：移动文件
- Phase 4：清理遗留文件
- Phase 5：更新配置文件
- Phase 6：验证与测试

每个阶段包含：
- 具体执行步骤
- 验证方式
- 完成条件
- 回滚方案

---

## 目标目录结构

```
短新闻爬取与分析/
├── backend/                         # 🔵 后端模块
│   ├── fastapi-service/             # AI/爬虫服务
│   └── spring-boot-service/         # 业务中台
├── frontend/                        # 🟢 前端模块
│   └── vue-frontend/               # Vue 3 前端
├── scripts/                         # 工具脚本
├── logs/                            # 日志目录
├── saved_models/                    # 模型文件
├── 开发文档/                         # 开发文档
└── 配置文件                          # docker-compose.yml 等
```

---

## 快速参考

### 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| MySQL | 3307 | 数据库 |
| FastAPI | 8000 | AI/爬虫服务 |
| Spring Boot | 8080 | 业务 API |
| Vue Frontend | 3000 | 前端页面 |

### 核心 API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/news/list` | GET | 获取新闻列表 |
| `/api/v1/news/{id}` | GET | 获取新闻详情 |
| `/api/v1/stats/overview` | GET | 统计概览 |
| `/internal/scrape/{source}` | POST | 运行爬虫 |
| `/api/v1/auth/login` | POST | 用户登录 |

---

## 更新记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-09-06 | 1.0 | 初始版本 |
| 2026-09-13 | 2.0 | 更新文档结构，移除旧架构文档 |
