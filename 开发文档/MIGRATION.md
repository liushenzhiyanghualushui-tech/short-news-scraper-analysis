# 项目重构迁移计划

## 版本历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| 1.0 | 2026-09-13 | AI | 初始迁移计划 |
| 1.1 | 2026-09-13 | AI | 新增 Docker 一键启动工程化方案，移除遗留启动程序 |

---

## 目录

1. [背景与目标](#1-背景与目标)
2. [目标目录结构](#2-目标目录结构)
3. [迁移阶段](#3-迁移阶段)
4. [阶段零：移除遗留启动程序](#4-阶段零移除遗留启动程序)
5. [阶段一：准备与备份](#5-阶段一准备与备份)
6. [阶段二：创建模块目录](#6-阶段二创建模块目录)
7. [阶段三：移动文件](#7-阶段三移动文件)
8. [阶段四：清理遗留文件](#8-阶段四清理遗留文件)
9. [阶段五：更新配置文件](#9-阶段五更新配置文件)
10. [阶段六：验证与测试](#10-阶段六验证与测试)
11. [一键启动方案](#11-一键启动方案)
12. [回滚方案](#12-回滚方案)
13. [附录](#13-附录)

---

## 1. 背景与目标

### 1.1 当前问题

当前项目根目录存在以下问题：

| 问题类型 | 描述 |
|---------|------|
| **遗留代码散落** | `app.py`、`api/`、`static/`、`templates/` 是旧 Flask 代码，与新架构混在一起 |
| **模块边界不清** | `scrapers/` 单独存在，本应整合到 `fastapi-service/` 中 |
| **根目录文件过多** | 根目录有 `requirements.txt`、`config.json`、`docker-compose.yml` 等多个配置文件 |
| **工具脚本分散** | `scripts/` 和根目录部分 Python 脚本混杂 |
| **启动方式不统一** | 需要手动运行 `python app.py` 或 `python config_tool.py`，而非 Docker 一键启动 |
| **环境依赖混乱** | 本地 Python 环境与 Docker 环境边界不清 |

### 1.2 迁移目标

```
┌─────────────────────────────────────────────────────────────┐
│                        迁移目标                              │
├─────────────────────────────────────────────────────────────┤
│  1. 前后端分离：backend/ 和 frontend/ 两个顶级模块          │
│  2. 职责清晰：每个模块边界清晰，职责明确                    │
│  3. 便于开发：可独立启动/停止前后端                        │
│  4. 符合架构：与 docker-compose 部署方案一致               │
│  5. 便于 CI/CD：每个模块可独立构建镜像                     │
│  6. 一键启动：通过 Docker Compose 一次性启动所有服务        │
│  7. 零手动启动：无需手动运行 python app.py 等启动程序       │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 工程化目标：零手动启动架构

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        零手动启动架构                                         │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  用户操作:                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐     │
│  │  $ docker-compose up -d                                              │     │
│  │  $ open http://localhost:3000                                        │     │
│  └─────────────────────────────────────────────────────────────────────┘     │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐     │
│  │                      Docker 编排层                                   │     │
│  │  ┌─────────┐  ┌─────────────┐  ┌──────────────┐  ┌───────────┐     │     │
│  │  │  MySQL  │  │   FastAPI   │  │  Spring Boot │  │  Vue/Nginx │     │     │
│  │  │  :3307  │  │    :8000    │  │     :8080    │  │    :3000   │     │     │
│  │  └─────────┘  └─────────────┘  └──────────────┘  └───────────┘     │     │
│  └─────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
│  无需:                                                                        │
│  ✗ python app.py                                                             │
│  ✗ python config_tool.py                                                     │
│  ✗ python -m uvicorn main:app                                                │
│  ✗ 手动安装依赖 / 配置环境变量 / 启动数据库                                  │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 目标目录结构

### 2.1 整体结构

```
短新闻爬取与分析/
│
├── 📦 backend/                         # 🔵 后端模块
│   ├── fastapi-service/                # AI/爬虫服务
│   │   ├── api/                        # API 路由
│   │   ├── services/                   # 业务服务
│   │   ├── domain/                     # 领域层
│   │   │   ├── scrapers/               # 爬虫实现
│   │   │   ├── models/                 # ML 模型
│   │   │   └── nlp/                   # NLP 工具
│   │   ├── infrastructure/            # 基础设施
│   │   ├── core/                      # 核心工具
│   │   ├── main.py
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   │
│   └── spring-boot-service/            # 业务中台
│       ├── src/main/java/com/news/
│       │   ├── controller/             # REST 控制器
│       │   ├── service/               # 业务逻辑
│       │   ├── repository/            # 数据访问
│       │   ├── entity/                 # JPA 实体
│       │   ├── dto/                    # 数据传输对象
│       │   ├── config/                # 配置类
│       │   └── exception/             # 异常处理
│       ├── src/main/resources/
│       ├── pom.xml
│       └── Dockerfile
│
├── 📦 frontend/                        # 🟢 前端模块
│   └── vue-frontend/                  # Vue 3 前端
│       ├── src/
│       │   ├── api/                   # API 调用层
│       │   ├── views/                 # 页面视图
│       │   ├── components/            # 公共组件
│       │   ├── stores/               # Pinia 状态
│       │   └── router/                # 路由配置
│       ├── package.json
│       ├── vite.config.ts
│       └── Dockerfile
│
├── 📂 scripts/                         # 工具脚本
│   ├── init-db.sql                    # 数据库初始化
│   └── check_nlp_setup.py             # NLP 检查脚本
│
├── 📂 logs/                            # 日志目录
├── 📂 saved_models/                    # 模型文件
├── 📂 开发文档/                         # 开发文档
│   ├── README.md                      # 项目说明
│   └── MIGRATION.md                   # 本文档
│
├── 📄 docker-compose.yml               # Docker 编排
├── 📄 .env.example                    # 环境变量模板
├── 📄 .gitignore                      # Git 忽略配置
└── 📄 README.md                       # 项目入口说明
```

### 2.2 模块职责

| 模块 | 职责 | 技术栈 | 端口 |
|------|------|--------|------|
| `backend/fastapi-service/` | 爬虫执行、ML 训练/推理、NLP 分析 | Python + FastAPI | 8000 |
| `backend/spring-boot-service/` | 业务编排、API 网关、数据展示 | Java + Spring Boot | 8080 |
| `frontend/vue-frontend/` | 用户界面、新闻展示、数据可视化 | Vue 3 + TypeScript | 3000 |

---

## 3. 迁移阶段

### 3.1 阶段总览

| 阶段 | 内容 | 风险 | 工时估计 |
|------|------|------|----------|
| **Phase 0** | 移除遗留启动程序 | 低 | 5 分钟 |
| **Phase 1** | 准备与备份 | 低 | 5 分钟 |
| **Phase 2** | 创建模块目录 | 低 | 2 分钟 |
| **Phase 3** | 移动文件 | 中 | 10 分钟 |
| **Phase 4** | 清理遗留文件 | 中 | 5 分钟 |
| **Phase 5** | 更新配置文件 | 中 | 15 分钟 |
| **Phase 6** | 验证与测试 | 中 | 20 分钟 |

### 3.2 迁移流程图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           迁移流程                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Phase 0          Phase 1          Phase 2          Phase 3          Phase 4│
│  ┌───────┐       ┌───────┐       ┌───────┐       ┌───────┐       ┌───────┐│
│  │ 移除  │ ────> │ 备份  │ ────> │ 创建  │ ────> │ 移动  │ ────> │ 清理  ││
│  │ 遗留  │       │       │       │ 目录  │       │ 文件  │       │ 遗留  ││
│  └───────┘       └───────┘       └───────┘       └───────┘       └───────┘│
│       │               │               │               │               │   │
│       │               │               │               │               │   │
│       ▼               ▼               ▼               ▼               ▼   │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │  Phase 5: 更新配置                                        Phase 6     │ │
│  │  ┌─────────────┐                                                ┌────┴───┤
│  │  │ docker-     │                                                │ 验证  │
│  │  │ compose.yml │                                                │ 测试  │
│  │  └─────────────┘                                                └───────┘
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 阶段零：移除遗留启动程序

### 4.1 目标

移除根目录下的遗留启动程序，使系统完全依赖 Docker 启动，不再需要手动运行 Python 脚本。

### 4.2 需要移除的文件

| 类型 | 路径 | 说明 |
|------|------|------|
| **启动脚本** | `app.py` | 旧的 Flask/单体应用启动入口 |
| **配置工具** | `config_tool.py` | 旧的配置管理工具 |
| **旧 API 路由** | `api/` | 旧的 Flask API 路由目录 |
| **旧静态文件** | `static/` | 旧的静态资源目录 |
| **旧模板** | `templates/` | 旧的 Jinja2 模板目录 |
| **旧配置** | `config.json` | 旧的配置文件（配置已迁移到 docker-compose.yml） |

### 4.3 执行步骤

```powershell
# 确认要移除的文件存在
Get-Item "app.py" -ErrorAction SilentlyContinue
Get-Item "config_tool.py" -ErrorAction SilentlyContinue
Get-ChildItem "api" -ErrorAction SilentlyContinue
Get-ChildItem "static" -ErrorAction SilentlyContinue
Get-ChildItem "templates" -ErrorAction SilentlyContinue

# 移除遗留文件（确认无误后执行）
Remove-Item -Path "app.py" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "config_tool.py" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "api" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "static" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "templates" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "config.json" -Force -ErrorAction SilentlyContinue

# 清理 Python 缓存
Remove-Item -Path "__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "*.pyc" -Force -ErrorAction SilentlyContinue
```

### 4.4 移除后的启动方式

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          启动方式对比                                         │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  移除前（多步骤、依赖本地环境）:                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐     │
│  │  $ pip install -r requirements.txt                                   │     │
│  │  $ python config_tool.py  # 配置数据库                              │     │
│  │  $ python app.py         # 启动单体应用                            │     │
│  │  $ docker-compose up -d  # 仅启动 MySQL 等外部依赖                  │     │
│  └─────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
│  移除后（单一命令、Docker 封装）:                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐     │
│  │  $ docker-compose up -d        # 启动所有服务                       │     │
│  │  $ open http://localhost:3000  # 访问前端                          │     │
│  └─────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 4.5 验证方式

```powershell
# 确认遗留文件已删除
Test-Path app.py
Test-Path config_tool.py
Test-Path api
Test-Path static
Test-Path templates
Test-Path config.json

# 预期输出全部为 False
```

### 4.6 完成条件

- [x] `app.py` 已删除
- [x] `config_tool.py` 已删除
- [x] `api/` 目录已删除
- [x] `static/` 目录已删除
- [x] `templates/` 目录已删除
- [x] `config.json` 已删除

---

## 5. 阶段一：准备与备份

### 5.1 目标

确保所有更改可追溯，创建备份点。

### 5.2 执行步骤

#### 步骤 1.1：提交当前状态

```powershell
# 确保当前所有更改已提交
git status
git add .
git commit -m "chore: 迁移前的最后提交

- 保留所有当前文件状态
- 为目录重构创建备份点"
```

#### 步骤 1.2：创建备份标签

```powershell
git tag -a pre-refactor-20260913 -m "重构前的备份点"
```

### 5.3 验证方式

```powershell
git log --oneline -1
git tag | grep pre-refactor
```

### 5.4 完成条件

- [x] 所有更改已提交
- [x] 备份标签已创建
- [x] 无未提交的更改

---

## 6. 阶段二：创建模块目录

### 6.1 目标

创建新的模块目录结构 `backend/` 和 `frontend/`。

### 6.2 执行步骤

```powershell
# 进入项目目录
cd "C:\Users\Bye\Downloads\项目库\短新闻爬取与分析"

# 创建顶级模块目录
New-Item -ItemType Directory -Path "backend" -Force
New-Item -ItemType Directory -Path "frontend" -Force

# 验证目录创建
Get-ChildItem -Directory | Where-Object { $_.Name -in @('backend', 'frontend') }
```

### 7.3 验证方式

```powershell
Test-Path backend
Test-Path frontend
```

### 7.4 完成条件

- [ ] `backend/` 目录存在
- [ ] `frontend/` 目录存在

---

## 7. 阶段三：移动文件

### 7.1 目标

将现有文件移动到新的模块目录中。

### 7.2 执行步骤

#### 步骤 3.1：移动 FastAPI 服务

```powershell
# 移动 fastapi-service 到 backend/
Move-Item -Path "fastapi-service" -Destination "backend\"

# 移动 scrapers 到 backend/fastapi-service/domain/
# 注意：需要先检查是否存在冲突
Move-Item -Path "scrapers" -Destination "backend\fastapi-service\domain\"
```

#### 步骤 3.2：移动 Spring Boot 服务

```powershell
# 移动 spring-boot-service 到 backend/
Move-Item -Path "spring-boot-service" -Destination "backend\"
```

#### 步骤 3.3：移动 Vue 前端

```powershell
# 移动 vue-frontend 到 frontend/
Move-Item -Path "vue-frontend" -Destination "frontend\"
```

### 6.3 移动后的预期结构

```
backend/
├── fastapi-service/
│   ├── api/
│   ├── services/
│   ├── domain/
│   │   └── scrapers/          # 从根目录移动而来
│   ├── infrastructure/
│   ├── core/
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
│
└── spring-boot-service/
    ├── src/
    ├── pom.xml
    └── Dockerfile

frontend/
└── vue-frontend/
    ├── src/
    ├── package.json
    └── Dockerfile
```

### 6.4 验证方式

```powershell
# 验证文件结构
Get-ChildItem -Path "backend" -Recurse -Directory | Select-Object FullName
Get-ChildItem -Path "frontend" -Recurse -Directory | Select-Object FullName
```

### 6.5 完成条件

- [ ] `backend/fastapi-service/` 目录存在
- [ ] `backend/spring-boot-service/` 目录存在
- [ ] `frontend/vue-frontend/` 目录存在
- [ ] 根目录无 `fastapi-service/` 目录
- [ ] 根目录无 `spring-boot-service/` 目录
- [ ] 根目录无 `vue-frontend/` 目录

---

## 8. 阶段四：清理遗留文件

### 8.1 目标

删除旧的 Flask 相关文件和不再需要的遗留文件。

### 8.2 需要删除的文件/目录

| 类型 | 路径 | 说明 |
|------|------|------|
| **目录** | `api/` | 旧的 Flask API 路由 |
| **目录** | `static/` | 旧的静态文件 |
| **目录** | `templates/` | 旧的 Jinja2 模板 |
| **文件** | `app.py` | 旧的 Flask 入口 |
| **文件** | `config.json` | 旧配置文件（应迁移到对应服务） |
| **文件** | `config_tool.py` | 旧配置工具 |
| **文件** | `msedgedriver.exe` | 浏览器驱动（可选保留） |

### 8.3 执行步骤

#### 步骤 4.1：确认需要删除的文件

```powershell
# 列出将被删除的项目
Get-ChildItem -Path "api" -ErrorAction SilentlyContinue
Get-ChildItem -Path "static" -ErrorAction SilentlyContinue
Get-ChildItem -Path "templates" -ErrorAction SilentlyContinue
Get-Item "app.py" -ErrorAction SilentlyContinue
Get-Item "config.json" -ErrorAction SilentlyContinue
```

#### 步骤 4.2：删除文件（确认无误后执行）

```powershell
# 删除旧的 Flask 相关文件
Remove-Item -Path "api" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "static" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "templates" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "app.py" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "config.json" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "config_tool.py" -Force -ErrorAction SilentlyContinue
```

#### 步骤 4.3：处理根目录 Python 缓存

```powershell
Remove-Item -Path "__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "*.pyc" -Force -ErrorAction SilentlyContinue
```

### 8.4 验证方式

```powershell
# 确认文件已删除
Test-Path api
Test-Path static
Test-Path templates
Test-Path app.py
Test-Path config.json

# 确认核心文件仍存在
Test-Path backend\fastapi-service\main.py
Test-Path backend\spring-boot-service\pom.xml
Test-Path frontend\vue-frontend\package.json
```

### 8.5 完成条件

- [ ] `api/` 目录已删除
- [ ] `static/` 目录已删除
- [ ] `templates/` 目录已删除
- [ ] `app.py` 已删除
- [ ] `config.json` 已删除
- [ ] 核心服务文件仍存在

---

## 9. 阶段五：更新配置文件

### 9.1 目标

更新 `docker-compose.yml`、`.gitignore` 和项目引用路径。

### 9.2 更新 docker-compose.yml

#### 当前配置（需要修改）

```yaml
# 当前路径
services:
  fastapi:
    build:
      context: ./fastapi-service
  spring-boot:
    build:
      context: ./spring-boot-service
  frontend:
    build:
      context: ./vue-frontend
```

#### 修改后配置

```yaml
services:
  mysql:
    # ... (保持不变)
    
  fastapi:
    build:
      context: ./backend/fastapi-service
    volumes:
      - ./backend/fastapi-service:/app
      - saved_models:/app/saved_models
    
  spring-boot:
    build:
      context: ./backend/spring-boot-service
    volumes:
      - ./backend/spring-boot-service:/app
    
  frontend:
    build:
      context: ./frontend/vue-frontend
```

### 9.3 更新 .gitignore

#### 需要添加的内容

```gitignore
# ========== 重构后的目录结构 ==========
backend/fastapi-service/__pycache__/
backend/fastapi-service/*.pyc
backend/fastapi-service/.venv/
backend/fastapi-service/saved_models/
backend/spring-boot-service/target/
backend/spring-boot-service/*.class
frontend/vue-frontend/node_modules/
frontend/vue-frontend/dist/

# 保留根目录的日志和模型目录
logs/
saved_models/
```

### 9.4 执行步骤

#### 步骤 9.1：备份并更新 docker-compose.yml

```powershell
# 备份原文件
Copy-Item "docker-compose.yml" "docker-compose.yml.bak"

# 读取并更新内容（使用文本编辑器手动修改或 PowerShell 替换）
```

#### 步骤 9.2：更新 .gitignore

```powershell
# 追加新的忽略规则到 .gitignore
Add-Content -Path ".gitignore" -Value "`n# ========== 重构后的目录结构 ==========`nbackend/"
```

### 9.5 验证方式

```powershell
# 验证 docker-compose.yml 语法
docker-compose config

# 验证 .gitignore 内容
Get-Content ".gitignore" | Select-String "backend"
```

### 9.6 完成条件

- [ ] `docker-compose.yml` 已更新为新路径
- [ ] `.gitignore` 已更新
- [ ] Docker 配置验证通过

---

## 10. 阶段六：验证与测试

### 10.1 目标

确保重构后的项目可以正常构建和运行。

### 10.2 验证清单

#### 10.2.1 Git 状态检查

```powershell
git status
```

**预期结果**：
- 新增的 `backend/`、`frontend/` 目录
- 删除的旧文件（Flask 相关）
- 更新的 `docker-compose.yml`、`.gitignore`

#### 10.2.2 目录结构验证

```powershell
# 验证整体结构
Get-ChildItem -Path "." -Depth 1

# 验证 backend 内容
Get-ChildItem -Path "backend"
Get-ChildItem -Path "backend/fastapi-service"
Get-ChildItem -Path "backend/spring-boot-service"

# 验证 frontend 内容
Get-ChildItem -Path "frontend"
Get-ChildItem -Path "frontend/vue-frontend"
```

#### 10.2.3 Docker 构建测试

```powershell
# 测试 FastAPI 服务构建
docker-compose build fastapi

# 测试 Spring Boot 服务构建
docker-compose build spring-boot

# 测试前端构建
docker-compose build frontend
```

#### 10.2.4 服务启动测试

```powershell
# 启动所有服务
docker-compose up -d

# 检查服务状态
docker-compose ps

# 检查日志
docker-compose logs -f
```

#### 10.2.5 功能验证

| 服务 | 地址 | 验证命令 |
|------|------|----------|
| FastAPI | http://localhost:8000 | `curl http://localhost:8000/docs` |
| Spring Boot | http://localhost:8080 | `curl http://localhost:8080/actuator/health` |
| Vue Frontend | http://localhost:3000 | 浏览器访问 |

### 10.3 完成条件

- [ ] Git 状态显示正确的变更
- [ ] 目录结构符合预期
- [ ] Docker 构建成功
- [ ] 所有服务正常启动
- [ ] 核心功能可访问

---

## 11. 一键启动方案

### 11.1 方案概述

重构后的项目实现**零手动启动**，用户只需一条命令即可启动所有服务。

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           一键启动流程                                       │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  步骤 1: 创建环境变量文件                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐     │
│  │  cp .env.example .env                                                │     │
│  │  # 编辑 .env 填入必要的环境变量（见 11.2）                            │     │
│  └─────────────────────────────────────────────────────────────────────┘     │
│                                    │                                         │
│                                    ▼                                         │
│  步骤 2: 一键启动所有服务                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐     │
│  │  docker-compose up -d                                                │     │
│  └─────────────────────────────────────────────────────────────────────┘     │
│                                    │                                         │
│                                    ▼                                         │
│  步骤 3: 验证服务状态                                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐     │
│  │  docker-compose ps                                                   │     │
│  │  docker-compose logs -f                                              │     │
│  └─────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 11.2 环境变量配置

#### .env.example 文件内容

```bash
# ==================== 数据库配置 ====================
MYSQL_ROOT_PASSWORD=your_mysql_root_password_here
MYSQL_DATABASE=news_scraper
DB_USERNAME=newsapp
DB_PASSWORD=your_db_password_here

# ==================== 服务配置 ====================
DB_HOST=mysql
DB_PORT=3306

# ==================== FastAPI 配置 ====================
FASTAPI_API_KEY=your_fastapi_api_key_here
HF_ENDPOINT=https://hf-mirror.com
HF_MODEL_ID=bert-base-chinese
HF_TIMEOUT=120

# ==================== Spring Boot 配置 ====================
JWT_SECRET=your_jwt_secret_here_at_least_32_characters
```

### 11.3 服务启动顺序

Docker Compose 会自动处理服务依赖：

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           服务启动顺序                                        │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  启动顺序由 depends_on 和 healthcheck 控制:                                  │
│                                                                              │
│  1. MySQL (3307)          ← 基础依赖，无依赖                                │
│       ↓ 健康检查通过                                                         │
│  2. FastAPI (8000)        ← 依赖 MySQL                                     │
│       ↓ 健康检查通过                                                         │
│  3. Spring Boot (8080)    ← 依赖 MySQL + FastAPI                           │
│  4. Frontend (3000)       ← 依赖 Spring Boot                                │
│                                                                              │
│  用户只需: docker-compose up -d                                              │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 11.4 启动验证清单

```powershell
# 1. 检查所有容器状态
docker-compose ps

# 预期输出:
# NAME                IMAGE                    COMMAND                  SERVICE
# news-mysql          mysql:8.0                "docker-entrypoint.s…"   mysql
# news-fastapi        news_scraper-fastapi     "uvicorn main:app -…"   fastapi
# news-springboot     news_scraper-springboot  "java -jar app.jar"      spring-boot
# news-frontend       news_scraper-frontend    "/docker-entrypoint.…"   frontend

# 2. 检查服务健康状态
curl http://localhost:8000/api/health      # FastAPI
curl http://localhost:8080/actuator/health # Spring Boot

# 3. 访问前端
# 浏览器打开: http://localhost:3000
```

### 11.5 停止服务

```powershell
# 停止所有服务（保留数据卷）
docker-compose down

# 停止所有服务并删除数据卷（谨慎操作，会删除数据库数据）
docker-compose down -v
```

### 11.6 常用运维命令

```powershell
# 查看日志
docker-compose logs -f              # 查看所有服务日志
docker-compose logs -f fastapi     # 查看 FastAPI 日志
docker-compose logs --tail=100 mysql  # 查看 MySQL 最近 100 行日志

# 重启单个服务
docker-compose restart fastapi

# 重建单个服务
docker-compose up -d --build fastapi

# 进入容器调试
docker exec -it news-fastapi bash
docker exec -it news-mysql mysql -uroot -p
```

### 11.7 服务端口汇总

| 服务 | 容器端口 | 主机端口 | 说明 |
|------|----------|----------|------|
| MySQL | 3306 | 3307 | 数据库（外部访问） |
| FastAPI | 8000 | 8000 | AI/爬虫服务 API |
| Spring Boot | 8080 | 8080 | 业务中台 API |
| Frontend | 80 | 3000 | Vue + Nginx 前端 |

---

## 12. 回滚方案

### 12.1 回滚触发条件

- Docker 构建失败且无法在 30 分钟内解决
- 服务无法正常启动
- 关键文件丢失

### 12.2 回滚步骤

```powershell
# 1. 停止所有服务
docker-compose down

# 2. 恢复到备份标签
git checkout pre-refactor-20260913

# 3. 清理移动的文件（如果存在）
Remove-Item -Path "backend" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "frontend" -Recurse -Force -ErrorAction SilentlyContinue

# 4. 验证恢复
git log --oneline -1
```

### 12.3 回滚后操作

1. 分析失败原因
2. 修复问题后重新执行迁移
3. 记录失败原因到开发文档

---

## 13. 附录

### A. 快速执行脚本

```powershell
# 迁移执行脚本 - 请在确认理解每一步后再执行

# ========== Phase 0: 移除遗留启动程序 ==========
Remove-Item -Path "app.py" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "config_tool.py" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "api" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "static" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "templates" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "config.json" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "__pycache__" -Recurse -Force -ErrorAction SilentlyContinue

# ========== Phase 1: 备份 ==========
git add .
git commit -m "chore: 迁移前备份"
git tag -a pre-refactor-20260913 -m "重构前备份"

# ========== Phase 2: 创建目录 ==========
New-Item -ItemType Directory -Path "backend" -Force
New-Item -ItemType Directory -Path "frontend" -Force

# ========== Phase 3: 移动文件 ==========
Move-Item -Path "fastapi-service" -Destination "backend\"
Move-Item -Path "scrapers" -Destination "backend\fastapi-service\domain\"
Move-Item -Path "spring-boot-service" -Destination "backend\"
Move-Item -Path "vue-frontend" -Destination "frontend\"

# ========== Phase 4: 清理遗留 ==========
Remove-Item -Path "api" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "static" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "templates" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "app.py" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "config.json" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "config_tool.py" -Force -ErrorAction SilentlyContinue
Remove-Item -Path "__pycache__" -Recurse -Force -ErrorAction SilentlyContinue

# ========== Phase 5: 更新配置文件（手动执行）==========
# 编辑 docker-compose.yml 更新路径
# 编辑 .gitignore 添加新规则

# ========== Phase 6: 提交更改 ==========
git add .
git commit -m "refactor: 重组项目目录结构

- 创建 backend/ 和 frontend/ 顶级模块
- 移动后端服务到 backend/
- 移动前端到 frontend/
- 清理遗留的 Flask 文件
- 实现 Docker 一键启动架构"
```

### B. 一键启动快速参考

```powershell
# 首次使用
cp .env.example .env
# 编辑 .env 填入必要配置
docker-compose up -d

# 日常使用
docker-compose up -d          # 启动
docker-compose ps             # 查看状态
docker-compose logs -f        # 查看日志
docker-compose down            # 停止
```

### C. 术语表

| 术语 | 说明 |
|------|------|
| FastAPI | Python 异步 Web 框架，用于 AI/爬虫服务 |
| Spring Boot | Java 微服务框架，用于业务中台 |
| Vue 3 | 前端 JavaScript 框架 |
| docker-compose | Docker 容器编排工具 |
| Trust Boundary | 信任边界，系统内外分界线 |
| 零手动启动 | 通过 Docker 封装实现无需手动运行 Python 脚本的启动方式 |

---

## 变更记录

| 变更日期 | 变更内容 | 变更人 |
|----------|----------|--------|
| 2026-09-13 | 创建迁移计划文档 | AI |
| 2026-09-13 | 新增 Docker 一键启动工程化方案，新增 Phase 0 移除遗留启动程序 | AI |
