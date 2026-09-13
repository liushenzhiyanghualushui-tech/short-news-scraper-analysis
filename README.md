# 短新闻爬取与分析系统

> **📌 注意**：本项目正在进行目录结构重构，详细迁移计划请参阅 [开发文档/MIGRATION.md](./开发文档/MIGRATION.md)。

## 项目简介

本项目是一个以国内新闻采集、统一入库、数据清洗、文本分类和 Web 管理为核心的综合系统。当前代码主线围绕以下能力展开：

- 多新闻源短新闻采集
- MySQL 统一存储与查询
- 新闻文本清洗、词频统计与训练数据准备
- 基于传统机器学习和深度学习的分类训练、评估、预测与批量应用
- 基于 Flask 的可视化管理后台与 REST API
- 基于 Tkinter 的本地配置与数据库初始化工具

## 当前实现概览

### 已接入的主要新闻源

当前代码中可直接创建和运行的新闻爬虫主要包括：

- 新浪新闻 `sina`
- 网易新闻 `netease`
- 中新网 `chinanews`
- 腾讯新闻 `tencent`
- 凤凰新闻 `ifeng`
- 澎湃新闻 `pengpai`
- 参考消息 `cankaoxiaoxi`
- 新华网 `xinhua`

说明：

- `scrapers/domestic/__init__.py` 中还注册了 `xinhua_discover`，用于新华网频道发现
- 配置文件和依赖中保留了 `hotsearch`、Scrapy、Selenium 等能力入口，但当前项目主流程以“国内新闻采集 + 新华网专表同步 + Web 管理后台”为主

### 核心能力

- **新闻采集**：面向多个国内新闻源的页面抓取、解析和去重入库
- **数据治理**：支持数据清洗、去重、分词、词频统计和训练样本准备
- **模型分析**：支持 `svm`、`rf`、`nb`、`lr`、`bert`、`bert_textcnn`、`cnn`、`lstm` 等模型相关流程
- **后台管理**：提供新闻列表、统计面板、日志查询、爬虫控制、模型训练和可视化接口
- **配置管理**：通过 `config_tool.py` 完成数据库连接测试、数据库初始化、配置保存和服务启动

## 系统架构

项目当前采用 `Crawler -> Database -> API -> Frontend/Tooling` 的分层结构：

1. **采集层**
   - 位于 `scrapers/` 与 `scrapers/domestic/`
   - 负责请求、解析、数据封装和入库
2. **存储层**
   - 位于 `scrapers/db.py`
   - 使用 `PyMySQL + 手写 SQL` 管理 MySQL 表结构与读写逻辑
3. **处理与建模层**
   - 位于 `scrapers/data_cleaner.py`、`scrapers/data_augmenter.py`、`scrapers/model_builder.py`
   - 负责数据清洗、增强、分类训练、评估和预测
4. **服务层**
   - 位于 `app.py` 与 `api/routes.py`
   - 提供 Web 页面与 REST API
5. **配置工具层**
   - 位于 `config_tool.py`
   - 提供本地 GUI，用于配置、初始化数据库和启动服务

## 技术栈

### 后端与服务

- Python 3.9+
- Flask
- Flask-CORS

### 爬虫与解析

- requests
- aiohttp
- httpx
- beautifulsoup4
- lxml
- Selenium
- Scrapy（当前主流程中保留依赖与配置，未形成完整独立子项目结构）

### 数据处理与建模

- pandas
- numpy
- jieba
- scikit-learn
- tensorflow
- transformers
- torch

### 数据库与日志

- MySQL
- PyMySQL
- PyYAML
- colorlog
- prometheus_client（当前主要在新华网爬虫中使用）

## 安装与配置

### 环境要求

- Python 3.9 及以上
- MySQL 5.7/8.0 或兼容版本
- Windows 环境下建议准备 Edge WebDriver（项目中已包含 `msedgedriver.exe`）

### 1. 创建虚拟环境

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Linux / macOS:

```bash
source .venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 修改配置

重点检查以下两个配置文件：

- `config.json`：本地配置工具和服务启动配置
- `scrapers/config.yaml`：爬虫、数据库、日志、训练增强等配置

建议至少确认以下配置项：

- 数据库地址、端口、用户名、密码、库名
- 服务监听地址与端口
- 各新闻源开关与采集参数
- 日志路径和运行模式

### 4. 初始化数据库

推荐方式是使用本地配置工具，因为当前项目的实际初始化流程不只是执行单个 SQL 文件。

```bash
python config_tool.py
```

在配置工具中依次完成：

1. 填写数据库连接信息
2. 测试数据库连接
3. 点击“初始化数据库”
4. 保存配置
5. 启动服务

当前数据库初始化的实际流程为：

1. 删除旧库并重建数据库
2. 调用 `scrapers/db.py` 中的 `init_database()` 创建主表
3. 执行 `scrapers/xinhua_init.sql` 创建新华网相关表
4. 调用 `scrapers/init.py` 初始化新闻来源字典数据

### 5. 启动服务

命令行方式：

```bash
python app.py --host 0.0.0.0 --port 5000 --debug
```

脚本方式：

- Windows PowerShell：`templates/scripts/run.ps1`
- Linux / macOS：`templates/scripts/run.sh`

环境初始化脚本：

- Windows：`templates/scripts/setup_venv.ps1`
- Linux / macOS：`templates/scripts/setup_venv.sh`

## 访问方式

### Web 页面

启动后可访问：

- `http://localhost:5000/`
- `http://localhost:5000/dashboard`
- `http://localhost:5000/news`
- `http://localhost:5000/logs`

### 主要 API

当前代码中已实现的主要 API 包括：

- `GET /api/dashboard/stats`
- `GET /api/news/list`
- `GET /api/news/detail/<article_id>`
- `GET /api/sources`
- `GET /api/logs`
- `GET /api/logs/stats`
- `GET /api/spider/list`
- `POST /api/spider/start`
- `POST /api/spider/run-all`
- `POST /api/spider/stop`
- `GET /api/admin/data/stats`
- `POST /api/admin/data/clean`
- `GET /api/admin/data/word-frequency`
- `POST /api/admin/model/train`
- `POST /api/admin/model/evaluate`
- `POST /api/admin/model/predict`
- `POST /api/admin/model/apply`
- `GET /api/admin/model/apply/status`
- `POST /api/admin/model/save`
- `POST /api/admin/model/load`
- `DELETE /api/admin/model/clear`（默认保留 `saved_models/pretrained` 预训练权重缓存）
- `DELETE /api/admin/model/clear?include_pretrained=1`（可选：连同预训练权重缓存一起清理）
- `GET /api/admin/visualize/data-quality`
- `GET /api/admin/visualize/collection-stats`
- `GET /api/health`

## 项目结构

> **📌 目录结构即将变更**：当前结构为重构前状态，迁移后将为 `backend/` + `frontend/` 双模块结构。详见 [开发文档/MIGRATION.md](./开发文档/MIGRATION.md)。

### 目标结构（迁移后）

```
短新闻爬取与分析/
├── backend/                         # 🔵 后端模块
│   ├── fastapi-service/             # AI/爬虫服务
│   │   ├── api/                     # API 路由
│   │   ├── services/                # 业务服务
│   │   ├── domain/                  # 领域层（包含 scrapers/）
│   │   └── main.py
│   └── spring-boot-service/         # 业务中台
│       ├── src/main/java/com/news/  # Java 源码
│       └── pom.xml
├── frontend/                        # 🟢 前端模块
│   └── vue-frontend/               # Vue 3 前端
├── scripts/                         # 工具脚本
├── logs/                            # 日志目录
├── saved_models/                    # 模型文件
├── docker-compose.yml               # Docker 编排
└── 开发文档/                         # 开发文档
```

### 当前结构（迁移前）

```text
短新闻爬取与分析/
├── api/                             # ⚠️ 旧的 Flask API（待删除）
├── fastapi-service/                 # → 迁移到 backend/
├── spring-boot-service/             # → 迁移到 backend/
├── vue-frontend/                    # → 迁移到 frontend/
├── scrapers/                        # → 合并到 backend/fastapi-service/domain/
├── static/                          # ⚠️ 旧的静态文件（待删除）
├── templates/                      # ⚠️ 旧的模板文件（待删除）
├── app.py                          # ⚠️ 旧的 Flask 入口（待删除）
└── ...

## 主要模块说明

### 1. Web 入口

- `app.py`：Flask 应用工厂、页面路由与服务启动入口

### 2. API 与业务接口

- `api/routes.py`：聚合统计、新闻查询、爬虫控制、数据清洗、模型训练、模型应用和可视化接口

### 3. 爬虫模块

- `scrapers/__init__.py`：爬虫注册与实例创建入口
- `scrapers/domestic/`：各新闻源爬虫实现
- `scrapers/base.py`：通用采集基类与公共流程

### 4. 数据处理与分析

- `scrapers/data_cleaner.py`：数据清洗与文本预处理
- `scrapers/data_augmenter.py`：训练数据增强
- `scrapers/model_builder.py`：分类器、训练器和深度学习模型封装

### 5. 数据库访问

- `scrapers/db.py`：数据库建表、插入、查询、统计、同步等核心逻辑

### 6. 配置工具

- `config_tool.py`：本地图形化配置工具，可执行数据库连接测试、数据库初始化、配置保存和服务启动

## 数据库分析

### 数据库选型与访问方式

当前项目使用 **MySQL + PyMySQL**，数据库访问方式不是 ORM，而是基于 `dataclass` 数据模型与手写 SQL 的轻量实现。  
这一设计更直接，便于按新闻采集场景控制建表、索引、批量插入和同步逻辑，但也意味着表结构维护需要依赖代码和 SQL 脚本保持一致。

### 当前实际使用的核心表

#### 1. `scraper_sources`

新闻来源字典表，用于维护来源元信息：

- `id`：来源主键
- `source_type`：来源类型，当前代码主要使用 `foreign` / `domestic`
- `name`：来源名称
- `code`：来源编码，唯一
- `platform_id`：平台编号
- `url_pattern`：URL 匹配规则
- `is_active`：是否启用

用途：

- 作为统一来源维表
- 供文章表和日志表通过 `source_id` 做逻辑关联

#### 2. `scraper_raw_articles`

统一原始文章主表，是当前系统最核心的数据表：

- `source_id`、`source_type`、`source_name`、`source_code`
- `url`、`title`、`title_en`、`author`
- `content`、`description`、`keywords`
- `category`
- `publish_time`
- `platform_id`
- `rank`
- `crawl_time`
- `raw_data`
- `status`

用途：

- 作为新闻展示、统计、清洗、模型训练和模型应用的统一数据入口
- 作为多新闻源数据汇总后的事实表

#### 3. `scraper_spider_logs`

爬虫运行日志表，用于记录任务执行状态：

- `spider_name`
- `source_id`
- `start_time`
- `end_time`
- `status`
- `items_count`
- `error_message`
- `duration`

用途：

- 支撑后台日志查询和任务运行追踪

#### 4. `domestic_news`

国内新闻明细表，当前在部分采集流程中保留使用，典型场景是网易新闻双写：

- `source_name`
- `source_code`
- `url`
- `title`
- `keywords`
- `author`
- `publish_date`
- `content`
- `description`
- `crawl_time`

用途：

- 保存国内新闻采集的原始明细
- 作为过渡表或兼容历史逻辑的专用表

#### 5. `xinhua_news`

新华网专用新闻表，由 `scrapers/xinhua_init.sql` 创建：

- `title`
- `subtitle`
- `publish_time`
- `source`
- `editor`
- `channel`
- `content`
- `images`
- `videos`
- `keywords`
- `url`
- `status`
- `retry_times`

用途：

- 保存新华网专用字段
- 与统一主表 `scraper_raw_articles` 形成“专表 + 汇总表”的双层结构

#### 6. `xinhua_channel`

新华网频道字典表：

- `name`
- `code`
- `url`
- `category`
- `is_active`
- `description`

用途：

- 存储新华网频道元信息
- 支撑频道发现与频道维度采集

### 表关系与数据流

#### 逻辑关系

- `scraper_sources` 是来源维表
- `scraper_raw_articles` 是统一文章事实表
- `scraper_spider_logs` 是采集任务日志表
- `xinhua_news` 是新华网专表，数据会同步进入 `scraper_raw_articles`
- `domestic_news` 是历史兼容/专用明细表，部分站点存在“专表 + 主表”双写

说明：

- 当前运行时建表逻辑中，`scraper_raw_articles` 和 `scraper_spider_logs` 主要通过 `source_id` 与 `scraper_sources` 建立**逻辑关联**
- 当前程序化建表没有全面声明数据库外键，更依赖应用层保证一致性

#### 采集到展示的数据通路

1. 各新闻源爬虫抓取页面并解析为数据对象
2. 数据通过 `DBHandler` 写入专表或统一主表
3. 新华网数据先写入 `xinhua_news`，再同步到 `scraper_raw_articles`
4. 部分国内新闻数据会先写入 `domestic_news`，再补写到 `scraper_raw_articles`
5. `api/routes.py` 中的大部分列表、统计、清洗、训练与预测接口都围绕 `scraper_raw_articles` 工作

### 索引设计分析

当前索引设计以“来源过滤 + 时间过滤 + 状态过滤 + 标题检索” 为主，较符合新闻后台常见查询模式：

- `scraper_sources`
  - `idx_source_type`
  - `idx_code`
- `scraper_raw_articles`
  - `idx_source`
  - `idx_source_type`
  - `idx_category`
  - `idx_publish_time`
  - `idx_crawl_time`
  - `idx_status`
  - `idx_title`
- `scraper_spider_logs`
  - `idx_source`
  - `idx_start_time`
  - `idx_status`
- `domestic_news`
  - `idx_source_code`
  - `idx_publish_date`
- `xinhua_news`
  - `idx_publish_channel`
  - `idx_create_time`

这些索引主要服务于以下场景：

- 后台列表分页与时间倒序展示
- 按来源、分类、状态统计
- 日志时间范围查询
- 新华网按频道和发布时间分析

### 当前数据库设计的特点

优点：

- 以 `scraper_raw_articles` 作为统一主表，便于前端展示和建模
- 为新华网保留专表，能容纳更丰富的结构化字段
- 手写 SQL 便于定制索引和批量操作

局限：

- `scrapers/init.sql` 与 `scrapers/db.py` 的实际建表逻辑并不完全一致
- 部分表是“历史遗留/预留设计”，并未完全纳入当前主流程
- 外键约束较少，主要依赖应用层维护一致性

### 数据库维护建议

如果后续继续演进，建议优先处理以下问题：

1. 统一 `scrapers/init.sql`、`scrapers/db.py`、`scrapers/xinhua_init.sql` 的建表定义
2. 明确哪些表属于当前生产主流程，哪些表属于预留或历史兼容
3. 为统一主表与来源表补充更清晰的一致性约束策略
4. 将模型结果、清洗记录、任务调度信息是否入库做明确设计

## 使用建议

- 首次部署优先使用 `config_tool.py` 初始化数据库和保存配置
- 常规展示、统计、训练相关功能应以 `scraper_raw_articles` 为分析基础
- 新增新闻源时，建议同时补充来源字典初始化、专用字段设计和统一主表映射
- 若启用深度学习或 BERT 模型，建议准备更高内存环境，必要时使用 GPU

## 已知问题与风险

- 新闻站点页面结构经常变化，解析规则需要持续维护
- 当前 README 应以“代码实际行为”为准，而不是旧版 SQL 脚本说明
- `hotsearch` 相关配置和依赖仍有保留，但与当前主流程存在一定脱节
- 数据库初始化主要依赖配置工具流程，单独执行 SQL 不能完全覆盖全部初始化动作
- 大模型和深度学习训练耗时较长，对 CPU、内存和磁盘空间有更高要求
- Selenium 相关采集对浏览器驱动、页面渲染和站点风控较敏感

## 许可证

本项目仅供学习与研究使用。请遵守目标网站的 robots 协议、服务条款及相关法律法规，不得用于非法用途或未经授权的商业场景。
