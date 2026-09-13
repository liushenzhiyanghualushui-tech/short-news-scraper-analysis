-- =====================================================
-- 统一爬虫项目 - 数据库初始化脚本
-- =====================================================
-- 使用前请先创建数据库:
-- CREATE DATABASE news_scraper DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- =====================================================

USE news_scraper;

-- =====================================================
-- 1. 新闻来源表 (sources)
-- =====================================================
CREATE TABLE IF NOT EXISTS scraper_sources (
    id TINYINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    source_type ENUM('hotsearch', 'domestic') NOT NULL COMMENT '来源类型',
    name VARCHAR(100) NOT NULL COMMENT '来源名称',
    code VARCHAR(50) NOT NULL UNIQUE COMMENT '来源编码',
    platform_id TINYINT UNSIGNED DEFAULT NULL COMMENT '热搜平台ID',
    url_pattern VARCHAR(500) DEFAULT NULL COMMENT 'URL匹配模式',
    is_active TINYINT UNSIGNED DEFAULT 1 COMMENT '是否启用',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_source_type (source_type),
    INDEX idx_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='新闻来源表';

-- =====================================================
-- 2. 热搜榜单表 (hot_search)
-- =====================================================
CREATE TABLE IF NOT EXISTS scraper_hot_search (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    source_id TINYINT UNSIGNED NOT NULL COMMENT '来源ID',
    platform_id TINYINT UNSIGNED NOT NULL COMMENT '平台ID(1-26)',
    rank INT UNSIGNED NOT NULL COMMENT '排名',
    title VARCHAR(500) NOT NULL COMMENT '热搜标题',
    author VARCHAR(200) DEFAULT '' COMMENT '作者/发布者',
    url VARCHAR(2000) DEFAULT '' COMMENT '话题链接',
    heat_index INT UNSIGNED DEFAULT NULL COMMENT '热度指数',
    crawl_time DATETIME NOT NULL COMMENT '爬取时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_platform_rank (platform_id, rank, crawl_time),
    INDEX idx_platform (platform_id),
    INDEX idx_crawl_time (crawl_time),
    INDEX idx_rank (rank),
    FOREIGN KEY (source_id) REFERENCES scraper_sources(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='热搜榜单表';

-- =====================================================
-- 3. 原始文章表 (raw_articles)
-- =====================================================
CREATE TABLE IF NOT EXISTS scraper_raw_articles (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    source_id TINYINT UNSIGNED NOT NULL COMMENT '来源ID',
    source_type ENUM('hotsearch', 'domestic') NOT NULL COMMENT '来源类型',
    source_name VARCHAR(100) NOT NULL COMMENT '来源名称',
    source_code VARCHAR(50) NOT NULL COMMENT '来源编码',
    url VARCHAR(2000) NOT NULL UNIQUE COMMENT '文章URL',
    title VARCHAR(500) DEFAULT '' COMMENT '标题',
    title_en VARCHAR(500) DEFAULT '' COMMENT '英文标题',
    author VARCHAR(200) DEFAULT '' COMMENT '作者',
    content LONGTEXT DEFAULT NULL COMMENT '正文内容',
    description TEXT DEFAULT NULL COMMENT '描述摘要',
    keywords TEXT DEFAULT NULL COMMENT '关键词',
    category VARCHAR(50) DEFAULT NULL COMMENT '分类标签',
    publish_time DATETIME DEFAULT NULL COMMENT '发布时间',
    platform_id TINYINT UNSIGNED DEFAULT NULL COMMENT '热搜平台ID',
    rank INT UNSIGNED DEFAULT NULL COMMENT '热搜排名',
    crawl_time DATETIME NOT NULL COMMENT '爬取时间',
    raw_data JSON DEFAULT NULL COMMENT '原始数据',
    status ENUM('pending', 'processed', 'failed') DEFAULT 'pending' COMMENT '处理状态',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_source (source_id),
    INDEX idx_source_type (source_type),
    INDEX idx_category (category),
    INDEX idx_publish_time (publish_time),
    INDEX idx_crawl_time (crawl_time),
    INDEX idx_status (status),
    INDEX idx_title (title(100)),
    FOREIGN KEY (source_id) REFERENCES scraper_sources(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='原始文章表';

CREATE TABLE IF NOT EXISTS scraper_article_nlp_results (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    article_id BIGINT UNSIGNED NOT NULL,
    task VARCHAR(64) NOT NULL,
    provider VARCHAR(16) NOT NULL,
    model VARCHAR(128) NOT NULL,
    version VARCHAR(64) DEFAULT NULL,
    label VARCHAR(128) DEFAULT NULL,
    score DECIMAL(6,5) DEFAULT NULL,
    result_json JSON DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_article_task (article_id, task),
    INDEX idx_task_created (task, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS scraper_events (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    window_start DATETIME NOT NULL,
    window_end DATETIME NOT NULL,
    title VARCHAR(300) NOT NULL,
    summary TEXT DEFAULT NULL,
    frame_json JSON DEFAULT NULL,
    article_count INT UNSIGNED NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_window (window_start, window_end),
    INDEX idx_article_count (article_count)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS scraper_event_articles (
    event_id BIGINT UNSIGNED NOT NULL,
    article_id BIGINT UNSIGNED NOT NULL,
    score DECIMAL(6,5) DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id, article_id),
    INDEX idx_article (article_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =====================================================
-- 4. 爬虫执行日志表 (spider_logs)
-- =====================================================
CREATE TABLE IF NOT EXISTS scraper_spider_logs (
    id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    spider_name VARCHAR(100) NOT NULL COMMENT '爬虫名称',
    source_id TINYINT UNSIGNED DEFAULT NULL COMMENT '来源ID',
    start_time DATETIME NOT NULL COMMENT '开始时间',
    end_time DATETIME DEFAULT NULL COMMENT '结束时间',
    status ENUM('running', 'success', 'failed') DEFAULT 'running' COMMENT '执行状态',
    items_count INT DEFAULT 0 COMMENT '采集数量',
    error_message TEXT DEFAULT NULL COMMENT '错误信息',
    duration INT UNSIGNED DEFAULT NULL COMMENT '执行时长(秒)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_spider_name (spider_name),
    INDEX idx_source (source_id),
    INDEX idx_start_time (start_time),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='爬虫执行日志表';

-- =====================================================
-- 5. 初始化来源数据
-- =====================================================

-- 热搜平台
INSERT INTO scraper_sources (source_type, name, code, platform_id) VALUES
('hotsearch', '微博热搜', 'hotsearch_weibo', 3),
('hotsearch', '百度热点', 'hotsearch_baidu', 12),
('hotsearch', '抖音热点', 'hotsearch_douyin', 16),
('hotsearch', 'B站热门', 'hotsearch_bilibili', 15),
('hotsearch', '快手热榜', 'hotsearch_kuaishou', 24);

-- 国内新闻
INSERT INTO scraper_sources (source_type, name, code) VALUES
('domestic', '新浪新闻', 'sina'),
('domestic', '网易新闻', 'netease'),
('domestic', '中新网', 'chinanews');

-- =====================================================
-- 6. 平台信息表 (扩展)
-- =====================================================
CREATE TABLE IF NOT EXISTS scraper_platforms (
    id TINYINT UNSIGNED PRIMARY KEY,
    name VARCHAR(50) NOT NULL COMMENT '平台名称',
    spider_name VARCHAR(50) NOT NULL COMMENT '爬虫名称',
    description VARCHAR(255) NULL COMMENT '平台描述',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='平台信息表';

INSERT INTO scraper_platforms (id, name, spider_name, description) VALUES
(3, '微博', 'weibo', '微博热搜'),
(12, '百度', 'baidu_hot', '百度热点'),
(15, 'B站', 'bilibili', 'B站热门'),
(16, '抖音', 'douyin_hot_hot', '抖音热点'),
(24, '快手', 'kuaishou_hot', '快手热榜');

-- =====================================================
-- 7. 分类标签表 (供后续分类系统使用)
-- =====================================================
CREATE TABLE IF NOT EXISTS scraper_classification_labels (
    id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    label_code VARCHAR(50) NOT NULL UNIQUE COMMENT '标签编码',
    label_name VARCHAR(100) NOT NULL COMMENT '标签名称',
    label_name_en VARCHAR(100) DEFAULT '' COMMENT '英文名称',
    parent_id INT UNSIGNED DEFAULT NULL COMMENT '父级标签ID',
    description TEXT DEFAULT NULL COMMENT '标签描述',
    priority INT DEFAULT 0 COMMENT '显示优先级',
    color VARCHAR(20) DEFAULT '#1890FF' COMMENT '展示颜色',
    is_active TINYINT DEFAULT 1 COMMENT '是否启用',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_parent (parent_id),
    INDEX idx_priority (priority)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='分类标签表';

INSERT INTO scraper_classification_labels (label_code, label_name, label_name_en, priority) VALUES
('politics', '政治', 'Politics', 1),
('economy', '经济', 'Economy', 2),
('sports', '体育', 'Sports', 3),
('entertainment', '娱乐', 'Entertainment', 4),
('technology', '科技', 'Technology', 5),
('education', '教育', 'Education', 6),
('society', '社会', 'Society', 7),
('military', '军事', 'Military', 8),
('culture', '文化', 'Culture', 9);

-- =====================================================
-- 完成提示
-- =====================================================
SELECT '数据库初始化完成!' AS status;
SELECT COUNT(*) AS source_count FROM scraper_sources;

