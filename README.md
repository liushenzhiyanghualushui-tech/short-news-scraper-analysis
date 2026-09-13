# 短新闻爬取与分析系统

一个基于 Docker 的分布式新闻爬取与分析平台，支持多源新闻采集、AI 分类、情感分析和事件聚合。

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Vue Frontend                              │
│                     (localhost:3000)                              │
│                          │                                       │
│                          ▼                                       │
│              ┌─────────────────────────┐                        │
│              │    Spring Boot API       │                        │
│              │    (localhost:8080)      │                        │
│              └───────────┬─────────────┘                        │
│                          │                                       │
│              ┌───────────┴─────────────┐                        │
│              │                         │                        │
│              ▼                         ▼                        │
│  ┌───────────────────────┐   ┌───────────────────────┐        │
│  │     MySQL 8.0         │   │      FastAPI          │        │
│  │    (localhost:3307)   │   │    (localhost:8000)   │        │
│  │   存储新闻与任务       │   │   AI推理/爬虫服务      │        │
│  └───────────────────────┘   └───────────────────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 前端 | Vue 3 + Vite + TypeScript | SPA 单页应用 |
| 后端 API | Spring Boot 21 | 业务中台，提供 REST API |
| AI/爬虫 | FastAPI + Python 3.11 | 新闻采集、AI 分类、情感分析 |
| 数据库 | MySQL 8.0 | 关系型数据库 |
| 容器化 | Docker + Docker Compose | 一键部署 |

## 快速开始

### 环境要求

- Docker 20.10+
- Docker Compose 2.0+
- 内存: 最少 4GB (推荐 8GB+)

### 1. 克隆项目

```bash
git clone <repository-url>
cd 短新闻爬取与分析
```

### 2. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，修改以下必填项:
# - MYSQL_ROOT_PASSWORD: MySQL root 密码
# - DB_PASSWORD: 应用数据库密码
# - JWT_SECRET: JWT 密钥 (至少 32 字符)
# - FASTAPI_API_KEY: FastAPI 内部 API 密钥
```

### 3. 一键启动

```bash
# 构建并启动所有服务
docker-compose up -d --build

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

### 4. 验证服务

启动后访问以下地址：

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端 | http://localhost:3000 | Vue 应用 |
| Spring Boot | http://localhost:8080/api/health | 后端健康检查 |
| FastAPI | http://localhost:8000/api/health | AI服务健康检查 |
| MySQL | localhost:3307 | 数据库 (外部) |

### 5. 停止服务

```bash
docker-compose down

# 清除数据卷 (慎用)
docker-compose down -v
```

## 目录结构

```
.
├── backend/
│   ├── fastapi-service/          # FastAPI AI/爬虫服务
│   │   ├── domain/               # 业务领域
│   │   ├── main.py               # 应用入口
│   │   ├── Dockerfile            # Docker 构建文件
│   │   └── .dockerignore         # Docker 忽略文件
│   │
│   └── spring-boot-service/       # Spring Boot 业务服务
│       ├── src/                   # 源代码
│       ├── pom.xml               # Maven 配置
│       ├── Dockerfile            # Docker 构建文件
│       └── .dockerignore          # Docker 忽略文件
│
├── frontend/
│   └── vue-frontend/             # Vue 前端应用
│       ├── src/                  # 源代码
│       ├── package.json          # npm 配置
│       ├── Dockerfile            # Docker 构建文件
│       └── .dockerignore          # Docker 忽略文件
│
├── scripts/
│   └── init-db.sql               # 数据库初始化脚本
│
├── docker-compose.yml            # Docker Compose 编排
├── .env.example                  # 环境变量模板
├── .gitignore                    # Git 忽略规则
├── .dockerignore                 # Docker 忽略规则 (根目录)
└── README.md                     # 本文档
```

## 环境变量说明

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `MYSQL_ROOT_PASSWORD` | 是 | - | MySQL root 密码 |
| `MYSQL_DATABASE` | 否 | news_scraper | 数据库名 |
| `DB_USERNAME` | 否 | newsapp | 数据库用户名 |
| `DB_PASSWORD` | 是 | - | 数据库密码 |
| `DB_HOST` | 否 | mysql | 数据库主机 |
| `DB_PORT` | 否 | 3306 | 数据库端口 |
| `JWT_SECRET` | 是 | - | JWT 签名密钥 (≥32字符) |
| `FASTAPI_API_KEY` | 是 | - | FastAPI 内部 API 密钥 |
| `HF_ENDPOINT` | 否 | https://hf-mirror.com | HuggingFace 镜像 |
| `HF_MODEL_ID` | 否 | bert-base-chinese | AI 模型 ID |
| `FRONTEND_EXTERNAL_PORT` | 否 | 3000 | 前端外部端口 |
| `SPRING_BOOT_EXTERNAL_PORT` | 否 | 8080 | 后端外部端口 |
| `FASTAPI_EXTERNAL_PORT` | 否 | 8000 | AI服务外部端口 |
| `MYSQL_EXTERNAL_PORT` | 否 | 3307 | 数据库外部端口 |

## Docker Compose 命令

```bash
# 启动所有服务
docker-compose up -d

# 启动并重新构建
docker-compose up -d --build

# 只启动特定服务
docker-compose up -d mysql fastapi

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f [service_name]

# 停止服务
docker-compose stop

# 停止并删除容器
docker-compose down

# 停止并删除容器、数据卷
docker-compose down -v

# 重启服务
docker-compose restart [service_name]

# 进入容器
docker exec -it news-springboot bash
docker exec -it news-fastapi bash
docker exec -it news-mysql mysql -uroot -p
```

## 开发说明

### 前端开发

```bash
cd frontend/vue-frontend
npm install
npm run dev
```

### 后端开发 (Spring Boot)

使用 IDE (IntelliJ IDEA / VS Code) 打开 `backend/spring-boot-service` 目录。

### AI 服务开发 (FastAPI)

```bash
cd backend/fastapi-service
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

## 安全注意事项

⚠️ **重要**: 以下文件包含敏感信息，**禁止提交到 Git**:

- `.env` (包含数据库密码、JWT 密钥、API 密钥)
- `*.pem`, `*.key`, `*.crt` (证书密钥)
- `config.json`, `secrets.json` (配置文件)
- `keystore.jks`, `*.p12` (密钥库)

请使用 `.env.example` 作为模板创建本地配置文件。

## 隐私文件清单

已配置的 `.gitignore` 会自动忽略:

| 类型 | 模式 |
|------|------|
| 环境变量 | `.env`, `.env.*` |
| 密钥文件 | `*.pem`, `*.key`, `*.jks`, `*.p12` |
| 日志文件 | `logs/`, `*.log` |
| 数据库文件 | `*.db`, `*.sqlite` |
| 缓存目录 | `.cache/`, `__pycache__/` |
| IDE 配置 | `.idea/`, `.vscode/` |
| 虚拟环境 | `.venv/`, `venv/` |
| 依赖目录 | `node_modules/` |
| 构建产物 | `dist/`, `target/` |

## 许可证

MIT License
