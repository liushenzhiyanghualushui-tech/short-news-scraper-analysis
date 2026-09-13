-- =====================================================
-- 新华网爬虫 - 数据库初始化脚本
-- =====================================================

USE news_scraper;

-- =====================================================
-- 1. 新华网新闻表 (xinhua_news)
-- =====================================================
CREATE TABLE IF NOT EXISTS xinhua_news (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(500) NOT NULL COMMENT '新闻标题',
    subtitle VARCHAR(500) DEFAULT '' COMMENT '副标题',
    publish_time DATETIME DEFAULT NULL COMMENT '发布时间',
    source VARCHAR(100) DEFAULT '新华网' COMMENT '来源',
    editor VARCHAR(100) DEFAULT '' COMMENT '责任编辑',
    channel VARCHAR(50) DEFAULT '' COMMENT '所属频道',
    content LONGTEXT DEFAULT NULL COMMENT '正文内容',
    images TEXT DEFAULT NULL COMMENT '图片链接列表(JSON)',
    videos TEXT DEFAULT NULL COMMENT '视频链接列表(JSON)',
    keywords VARCHAR(500) DEFAULT '' COMMENT '关键词',
    url VARCHAR(2000) NOT NULL COMMENT '文章URL',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    status TINYINT DEFAULT 1 COMMENT '状态: 1正常 0软删除',
    retry_times INT DEFAULT 0 COMMENT '重试次数',
    
    UNIQUE KEY uk_url (url(255)),
    INDEX idx_publish_channel (publish_time, channel),
    INDEX idx_create_time (create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='新华网新闻数据表';

-- =====================================================
-- 2. 新华网频道字典表 (xinhua_channel)
-- =====================================================
CREATE TABLE IF NOT EXISTS xinhua_channel (
    id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(50) NOT NULL COMMENT '频道名称',
    code VARCHAR(50) NOT NULL UNIQUE COMMENT '频道编码',
    url VARCHAR(500) NOT NULL COMMENT '频道URL',
    category VARCHAR(50) DEFAULT 'news' COMMENT '分类',
    is_active TINYINT DEFAULT 1 COMMENT '是否启用',
    description VARCHAR(200) DEFAULT '' COMMENT '描述',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='新华网频道字典表';

-- =====================================================
-- 3. 初始化频道数据
-- =====================================================
INSERT INTO xinhua_channel (name, code, url, category) VALUES
('时政', 'politics', 'http://www.news.cn/politics/', 'news'),
('国际', 'world', 'http://www.news.cn/world/', 'news'),
('财经', 'fortune', 'http://www.news.cn/fortune/', 'news'),
('军事', 'mil', 'http://www.news.cn/mil/', 'news'),
('文化', 'culture', 'http://www.news.cn/culture/', 'news'),
('科技', 'tech', 'http://www.news.cn/tech/', 'news'),
('港澳', 'gangao', 'http://www.news.cn/gangao/', 'news'),
('台湾', 'tw', 'http://www.news.cn/tw/', 'news')
ON DUPLICATE KEY UPDATE url = VALUES(url);

SELECT '新华网数据库初始化完成!' AS status;
