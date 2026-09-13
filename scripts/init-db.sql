-- ============================================
-- 短新闻爬取与分析系统 - 数据库初始化脚本
-- 版本: 1.0
-- 日期: 2026-09-06
-- ============================================

-- 创建数据库
CREATE DATABASE IF NOT EXISTS news_scraper
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE news_scraper;

-- ============================================
-- 1. 新闻来源字典表
-- ============================================
CREATE TABLE IF NOT EXISTS scraper_sources (
    id              SMALLINT UNSIGNED PRIMARY KEY AUTO_INCREMENT COMMENT '来源ID',
    source_type     ENUM('foreign', 'domestic', 'hotsearch') NOT NULL COMMENT '来源类型',
    name            VARCHAR(100) NOT NULL COMMENT '来源名称',
    code            VARCHAR(50) NOT NULL UNIQUE COMMENT '来源编码',
    platform_id     TINYINT UNSIGNED DEFAULT NULL COMMENT '平台ID(热搜)',
    url_pattern     VARCHAR(500) DEFAULT NULL COMMENT 'URL匹配规则',
    is_active       TINYINT UNSIGNED DEFAULT 1 COMMENT '是否启用: 0-禁用, 1-启用',
    config_json     JSON DEFAULT NULL COMMENT '采集配置',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    INDEX idx_source_type (source_type),
    INDEX idx_code (code),
    INDEX idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='新闻来源字典表';

-- ============================================
-- 2. 统一文章表
-- ============================================
CREATE TABLE IF NOT EXISTS raw_articles (
    id              BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT COMMENT '文章ID',
    source_id       SMALLINT UNSIGNED NOT NULL COMMENT '来源ID',
    source_type     ENUM('foreign', 'domestic', 'hotsearch') NOT NULL COMMENT '来源类型',
    source_name     VARCHAR(100) NOT NULL COMMENT '来源名称',
    source_code     VARCHAR(50) NOT NULL COMMENT '来源编码',
    url             VARCHAR(2000) NOT NULL COMMENT '文章URL',
    title           VARCHAR(500) DEFAULT '' COMMENT '标题',
    title_en        VARCHAR(500) DEFAULT '' COMMENT '英文标题',
    author          VARCHAR(200) DEFAULT '' COMMENT '作者',
    content         LONGTEXT DEFAULT NULL COMMENT '正文内容',
    description     TEXT DEFAULT NULL COMMENT '摘要描述',
    keywords        TEXT DEFAULT NULL COMMENT '关键词',
    category        VARCHAR(50) DEFAULT NULL COMMENT '分类',
    publish_time    DATETIME DEFAULT NULL COMMENT '发布时间',
    platform_id     TINYINT UNSIGNED DEFAULT NULL COMMENT '平台ID(热搜用)',
    rank_value      INT UNSIGNED DEFAULT NULL COMMENT '排名(热搜用)',
    crawl_time      DATETIME NOT NULL COMMENT '采集时间',
    raw_data        JSON DEFAULT NULL COMMENT '原始数据',
    status          ENUM('pending', 'cleaned', 'classified', 'failed') DEFAULT 'pending' COMMENT '处理状态',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    -- 索引设计
    INDEX idx_source (source_id),
    INDEX idx_source_type (source_type),
    INDEX idx_source_code (source_code),
    INDEX idx_category (category),
    INDEX idx_publish_time (publish_time),
    INDEX idx_crawl_time (crawl_time),
    INDEX idx_status (status),
    INDEX idx_title (title(100)),
    UNIQUE INDEX idx_url (url),
    
    -- 外键约束
    CONSTRAINT fk_article_source FOREIGN KEY (source_id) 
        REFERENCES scraper_sources(id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='统一文章表';

-- ============================================
-- 3. 爬虫执行日志表
-- ============================================
CREATE TABLE IF NOT EXISTS spider_logs (
    id              INT UNSIGNED PRIMARY KEY AUTO_INCREMENT COMMENT '日志ID',
    spider_name     VARCHAR(100) NOT NULL COMMENT '爬虫名称',
    source_id       SMALLINT UNSIGNED DEFAULT NULL COMMENT '来源ID',
    start_time      DATETIME NOT NULL COMMENT '开始时间',
    end_time        DATETIME DEFAULT NULL COMMENT '结束时间',
    status          ENUM('running', 'success', 'failed', 'stopped') DEFAULT 'running' COMMENT '执行状态',
    items_count     INT DEFAULT 0 COMMENT '采集数量',
    error_message   TEXT DEFAULT NULL COMMENT '错误信息',
    duration        INT UNSIGNED DEFAULT NULL COMMENT '执行耗时(秒)',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    
    INDEX idx_source (source_id),
    INDEX idx_start_time (start_time),
    INDEX idx_status (status),
    INDEX idx_spider_name (spider_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='爬虫执行日志表';

-- ============================================
-- 4. ML 模型结果表
-- ============================================
CREATE TABLE IF NOT EXISTS ml_results (
    id              BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT COMMENT '结果ID',
    article_id      BIGINT UNSIGNED NOT NULL COMMENT '文章ID',
    task_type       ENUM('classification', 'sentiment', 'embedding', 'ner', 'event') NOT NULL COMMENT '任务类型',
    model_name      VARCHAR(128) NOT NULL COMMENT '模型名称',
    model_version   VARCHAR(64) DEFAULT NULL COMMENT '模型版本',
    label           VARCHAR(128) DEFAULT NULL COMMENT '分类标签/情感标签',
    score           DECIMAL(6,5) DEFAULT NULL COMMENT '置信度分数',
    result_data     JSON DEFAULT NULL COMMENT '详细结果数据',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    
    INDEX idx_article (article_id),
    INDEX idx_task_type (task_type),
    INDEX idx_model (model_name),
    INDEX idx_created (created_at),
    
    CONSTRAINT fk_ml_article FOREIGN KEY (article_id) 
        REFERENCES raw_articles(id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ML模型结果表';

-- ============================================
-- 5. 事件聚合表
-- ============================================
CREATE TABLE IF NOT EXISTS events (
    id              BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT COMMENT '事件ID',
    window_start    DATETIME NOT NULL COMMENT '聚合窗口起始时间',
    window_end      DATETIME NOT NULL COMMENT '聚合窗口结束时间',
    title           VARCHAR(300) NOT NULL COMMENT '事件标题',
    summary         TEXT DEFAULT NULL COMMENT '事件摘要',
    frame           JSON DEFAULT NULL COMMENT '事件框架分析',
    article_count   INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '关联文章数量',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    INDEX idx_window (window_start, window_end),
    INDEX idx_article_count (article_count)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='事件聚合表';

-- ============================================
-- 6. 事件-文章关联表
-- ============================================
CREATE TABLE IF NOT EXISTS event_articles (
    event_id        BIGINT UNSIGNED NOT NULL COMMENT '事件ID',
    article_id      BIGINT UNSIGNED NOT NULL COMMENT '文章ID',
    similarity      DECIMAL(6,5) DEFAULT NULL COMMENT '相似度分数',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    
    PRIMARY KEY (event_id, article_id),
    INDEX idx_article (article_id),
    
    CONSTRAINT fk_event_article_event FOREIGN KEY (event_id) 
        REFERENCES events(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_event_article_article FOREIGN KEY (article_id) 
        REFERENCES raw_articles(id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='事件-文章关联表';

-- ============================================
-- 7. 用户表 (预留，用于管理后台)
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id              BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT COMMENT '用户ID',
    username        VARCHAR(50) NOT NULL UNIQUE COMMENT '用户名',
    password_hash   VARCHAR(255) NOT NULL COMMENT '密码哈希',
    email           VARCHAR(100) DEFAULT NULL COMMENT '邮箱',
    role            ENUM('admin', 'operator', 'viewer') DEFAULT 'viewer' COMMENT '角色',
    is_active       TINYINT UNSIGNED DEFAULT 1 COMMENT '是否启用',
    last_login      DATETIME DEFAULT NULL COMMENT '最后登录时间',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    
    INDEX idx_username (username),
    INDEX idx_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

-- ============================================
-- 8. 审计日志表
-- ============================================
CREATE TABLE IF NOT EXISTS audit_logs (
    id              BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT COMMENT '审计ID',
    user_id         BIGINT UNSIGNED DEFAULT NULL COMMENT '用户ID',
    username        VARCHAR(50) DEFAULT NULL COMMENT '用户名',
    action          VARCHAR(100) NOT NULL COMMENT '操作类型',
    resource        VARCHAR(100) DEFAULT NULL COMMENT '资源类型',
    resource_id     VARCHAR(100) DEFAULT NULL COMMENT '资源ID',
    ip_address      VARCHAR(45) DEFAULT NULL COMMENT 'IP地址',
    user_agent      VARCHAR(500) DEFAULT NULL COMMENT 'User-Agent',
    request_body    TEXT DEFAULT NULL COMMENT '请求体(脱敏)',
    response_status INT DEFAULT NULL COMMENT '响应状态',
    error_message   TEXT DEFAULT NULL COMMENT '错误信息',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
    
    INDEX idx_user (user_id),
    INDEX idx_action (action),
    INDEX idx_created (created_at),
    INDEX idx_resource (resource, resource_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='审计日志表';

-- ============================================
-- 初始化数据：新闻来源
-- ============================================
INSERT INTO scraper_sources (source_type, name, code, platform_id) VALUES
    -- 国内新闻
    ('domestic', '新浪新闻', 'sina', NULL),
    ('domestic', '网易新闻', 'netease', NULL),
    ('domestic', '中新网', 'chinanews', NULL),
    ('domestic', '腾讯新闻', 'tencent', NULL),
    ('domestic', '凤凰新闻', 'ifeng', NULL),
    ('domestic', '澎湃新闻', 'pengpai', NULL),
    ('domestic', '参考消息', 'cankaoxiaoxi', NULL),
    ('domestic', '新华网', 'xinhua', NULL),
    -- 热搜平台
    ('hotsearch', '微博热搜', 'weibo_hot', 3),
    ('hotsearch', '百度热搜', 'baidu_hot', 12),
    ('hotsearch', '抖音热搜', 'douyin_hot', 16),
    ('hotsearch', 'B站热搜', 'bilibili_hot', 15),
    ('hotsearch', '快手热搜', 'kuaishou_hot', 24)
ON DUPLICATE KEY UPDATE 
    name = VALUES(name);

-- ============================================
-- 初始化数据：默认管理员账户 (密码: admin123)
-- ============================================
INSERT INTO users (username, password_hash, email, role) VALUES
    ('admin', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.HkQ5YL8F4L0K6y', 'admin@example.com', 'admin')
ON DUPLICATE KEY UPDATE 
    role = VALUES(role);

-- ============================================
-- 完成提示
-- ============================================
SELECT '数据库初始化完成!' AS status;
SELECT COUNT(*) AS source_count FROM scraper_sources;
SELECT COUNT(*) AS user_count FROM users;
