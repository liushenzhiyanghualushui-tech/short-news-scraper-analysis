"""
数据库操作模块

提供统一的数据库连接管理和数据操作接口，支持：
1. 原始文章存储 (raw_articles表)
2. 来源管理 (sources表)
3. 爬虫日志 (spider_logs表)
"""

import pymysql
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from pymysql.cursors import DictCursor

from .models import (
    DomesticNewsItem,
    RawArticleItem,
    XinhuaNewsItem
)


class DBHandler:
    """MySQL 数据库处理器"""

    def __init__(self, config: dict):

        """
        初始化数据库处理器

        Args:
            config: 数据库配置字典，包含以下字段:
                - host: 数据库主机地址
                - port: 数据库端口
                - username: 数据库用户名
                - password: 数据库密码
                - name: 数据库名称
                - charset: 字符集 (默认 utf8mb4)
                - table_prefix: 表前缀 (默认 scraper_)
        """
        self.config = config
        self.host = config.get("host", "localhost")
        self.port = config.get("port", 3306)
        self.username = config.get("username", "root")
        self.password = config.get("password", "")
        self.database = config.get("name", "news_scraper")
        self.charset = config.get("charset", "utf8mb4")
        self.table_prefix = config.get("table_prefix", "scraper_")

        self.logger = logging.getLogger(__name__)

    def get_connection(self) -> Optional[pymysql.Connection]:
        """
        获取数据库连接

        Returns:
            pymysql.Connection: 数据库连接对象，失败返回 None
        """
        try:
            return pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.username,
                password=self.password,
                database=self.database,
                charset=self.charset,
                cursorclass=DictCursor,
                autocommit=False
            )
        except pymysql.Error as e:
            self.logger.error(f"数据库连接失败: {e}")
            return None

    @contextmanager
    def get_connection_ctx(self):
        """上下文管理器方式获取连接"""
        conn = None
        try:
            conn = self.get_connection()
            yield conn
        finally:
            if conn:
                conn.close()

    def get_table_name(self, table: str) -> str:
        """获取带前缀的表名"""
        return f"{self.table_prefix}{table}"

    # ==================== 初始化相关 ====================

    def init_database(self):
        """初始化数据库表结构"""
        tables = [
            # 来源表
            f"""
            CREATE TABLE IF NOT EXISTS {self.get_table_name('sources')} (
                id TINYINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
                source_type ENUM('foreign', 'domestic') NOT NULL,
                name VARCHAR(100) NOT NULL,
                code VARCHAR(50) NOT NULL UNIQUE,
                platform_id TINYINT UNSIGNED DEFAULT NULL,
                url_pattern VARCHAR(500) DEFAULT NULL,
                is_active TINYINT UNSIGNED DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_source_type (source_type),
                INDEX idx_code (code)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            # 原始文章表
            f"""
            CREATE TABLE IF NOT EXISTS {self.get_table_name('raw_articles')} (
                id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
                source_id TINYINT UNSIGNED NOT NULL,
                source_type ENUM('foreign', 'domestic') NOT NULL,
                source_name VARCHAR(100) NOT NULL,
                source_code VARCHAR(50) NOT NULL,
                url VARCHAR(2000) NOT NULL,
                title VARCHAR(500) DEFAULT '',
                title_en VARCHAR(500) DEFAULT '',
                author VARCHAR(200) DEFAULT '',
                content LONGTEXT DEFAULT NULL,
                description TEXT DEFAULT NULL,
                keywords TEXT DEFAULT NULL,
                category VARCHAR(50) DEFAULT NULL,
                publish_time DATETIME DEFAULT NULL,
                platform_id TINYINT UNSIGNED DEFAULT NULL,
                `rank` INT UNSIGNED DEFAULT NULL,
                crawl_time DATETIME NOT NULL,
                raw_data JSON DEFAULT NULL,
                status ENUM('pending', 'processed', 'failed') DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_source (source_id),
                INDEX idx_source_type (source_type),
                INDEX idx_category (category),
                INDEX idx_publish_time (publish_time),
                INDEX idx_crawl_time (crawl_time),
                INDEX idx_status (status),
                INDEX idx_title (title(100))
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.get_table_name('article_nlp_results')} (
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
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.get_table_name('events')} (
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
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self.get_table_name('event_articles')} (
                event_id BIGINT UNSIGNED NOT NULL,
                article_id BIGINT UNSIGNED NOT NULL,
                score DECIMAL(6,5) DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (event_id, article_id),
                INDEX idx_article (article_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            # 爬虫执行日志表
            f"""
            CREATE TABLE IF NOT EXISTS {self.get_table_name('spider_logs')} (
                id INT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
                spider_name VARCHAR(100) NOT NULL,
                source_id TINYINT UNSIGNED DEFAULT NULL,
                start_time DATETIME NOT NULL,
                end_time DATETIME DEFAULT NULL,
                status ENUM('running', 'success', 'failed') DEFAULT 'running',
                items_count INT DEFAULT 0,
                error_message TEXT DEFAULT NULL,
                duration INT UNSIGNED DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_source (source_id),
                INDEX idx_start_time (start_time),
                INDEX idx_status (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            # 国内新闻表
            f"""
            CREATE TABLE IF NOT EXISTS domestic_news (
                id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
                source_name VARCHAR(100) NOT NULL,
                source_code VARCHAR(50) NOT NULL,
                url VARCHAR(500) NOT NULL UNIQUE,
                title VARCHAR(500) NOT NULL,
                keywords TEXT,
                author VARCHAR(100),
                publish_date DATETIME,
                content LONGTEXT,
                description TEXT,
                crawl_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_source_code (source_code),
                INDEX idx_publish_date (publish_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        ]

        try:
            with self.get_connection_ctx() as conn:
                if not conn:
                    self.logger.error("无法初始化数据库: 无法获取连接")
                    return False
                with conn.cursor() as cursor:
                    for sql in tables:
                        cursor.execute(sql)
                conn.commit()
                self.logger.info("数据库表初始化成功")
                return True
        except pymysql.Error as e:
            self.logger.error(f"初始化数据库失败: {e}")
            return False

    def init_sources(self, sources: List[Dict[str, Any]]):
        """
        初始化来源数据

        Args:
            sources: 来源配置列表，每项包含 source_type, name, code, platform_id
        """
        query = f"""
        INSERT INTO {self.get_table_name('sources')} (source_type, name, code, platform_id)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE name = VALUES(name)
        """

        try:
            with self.get_connection_ctx() as conn:
                with conn.cursor() as cursor:
                    for source in sources:
                        cursor.execute(query, (
                            source["source_type"],
                            source["name"],
                            source["code"],
                            source.get("platform_id")
                        ))
                conn.commit()
                self.logger.info(f"已初始化 {len(sources)} 个来源")
        except pymysql.Error as e:
            self.logger.error(f"初始化来源失败: {e}")

    # ==================== 原始文章操作 ====================

    def insert_raw_article(self, item: RawArticleItem, source_id: int) -> bool:
        """
        插入原始文章数据

        Args:
            item: 原始文章数据项
            source_id: 来源ID

        Returns:
            bool: 插入成功返回 True
        """
        query = f"""
        INSERT INTO {self.get_table_name('raw_articles')}
        (source_id, source_type, source_name, source_code, url, title, title_en,
         author, content, description, keywords, publish_time, platform_id,
         `rank`, crawl_time, raw_data, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        try:
            with self.get_connection_ctx() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (
                        source_id,
                        item.source_type,
                        item.source_name,
                        item.source_code,
                        item.url,
                        item.title,
                        item.title_en,
                        item.author,
                        item.content,
                        item.description,
                        item.keywords,
                        item.publish_time,
                        item.platform_id,
                        item.rank,
                        item.crawl_time,
                        json.dumps(item.raw_data, ensure_ascii=False, default=str),
                        "pending"
                    ))
                conn.commit()
                return True
        except pymysql.IntegrityError:
            self.logger.debug(f"URL已存在，跳过插入: {item.url}")
            return False
        except pymysql.Error as e:
            self.logger.error(f"插入原始文章失败: {e}")
            return False

    def url_exists(self, url: str) -> bool:
        """检查URL是否存在"""
        query = f"SELECT 1 FROM {self.get_table_name('raw_articles')} WHERE url = %s"
        try:
            with self.get_connection_ctx() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (url,))
                    result = cursor.fetchone()
                    return result is not None
        except pymysql.Error as e:
            self.logger.error(f"检查URL失败: {e}")
            return False

    # ==================== 新华网专用操作 ====================

    def insert_xinhua_news(self, item: XinhuaNewsItem) -> bool:
        """插入新华网新闻"""
        query = """
        INSERT INTO xinhua_news
        (url, title, subtitle, publish_time, source, editor, channel, 
         content, images, videos, keywords, status, retry_times, create_time, update_time)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
        title = VALUES(title),
        content = VALUES(content),
        update_time = VALUES(update_time)
        """
        try:
            with self.get_connection_ctx() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (
                        item.url,
                        item.title,
                        item.subtitle,
                        item.publish_time,
                        item.source,
                        item.editor,
                        item.channel,
                        item.content,
                        json.dumps(item.images, ensure_ascii=False),
                        json.dumps(item.videos, ensure_ascii=False),
                        item.keywords,
                        item.status,
                        item.retry_times,
                        item.create_time,
                        item.update_time
                    ))
                conn.commit()
                return True
        except pymysql.Error as e:
            self.logger.error(f"插入新华网新闻失败: {e}")
            return False

    def insert_domestic_news(self, item: DomesticNewsItem) -> bool:
        """插入国内新闻数据"""
        query = """
        INSERT INTO domestic_news
        (source_name, source_code, url, title, keywords, author, publish_date, content, description, crawl_time)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
        title = VALUES(title),
        content = VALUES(content),
        updated_at = CURRENT_TIMESTAMP
        """
        try:
            with self.get_connection_ctx() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (
                        item.source_name,
                        item.source_code,
                        item.url,
                        item.title,
                        item.keywords,
                        item.author,
                        item.publish_date,
                        item.content,
                        item.description,
                        item.crawl_time
                    ))
                conn.commit()
                return True
        except pymysql.Error as e:
            self.logger.error(f"插入国内新闻失败: {e}")
            return False

    def get_xinhua_channels(self) -> List[Dict]:
        """获取新华网频道列表"""
        query = "SELECT * FROM xinhua_channel WHERE is_active = 1"
        try:
            with self.get_connection_ctx() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    return cursor.fetchall()
        except pymysql.Error as e:
            self.logger.error(f"获取新华网频道失败: {e}")
            return []
    
    def xinhua_url_exists(self, url: str) -> bool:
        """检查新华网URL是否存在"""
        query = "SELECT 1 FROM xinhua_news WHERE url = %s"
        try:
            with self.get_connection_ctx() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (url,))
                    return cursor.fetchone() is not None
        except pymysql.Error as e:
            self.logger.error(f"检查新华网URL失败: {e}")
            return False

    def get_xinhua_news_by_url(self, url: str) -> Optional[Dict]:
        """根据URL获取新华网新闻"""
        query = "SELECT * FROM xinhua_news WHERE url = %s LIMIT 1"
        try:
            with self.get_connection_ctx() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (url,))
                    return cursor.fetchone()
        except pymysql.Error as e:
            self.logger.error(f"查询新华网新闻失败: {e}")
            return None

    def sync_xinhua_news_to_raw_articles(self, source_id: int, limit: int = 500) -> int:
        """把 xinhua_news 的数据同步到 raw_articles（用于系统展示口径统一）"""
        query = """
        SELECT url, title, publish_time, channel, content, images, videos, keywords, create_time
        FROM xinhua_news
        WHERE status = 1
        ORDER BY create_time DESC
        LIMIT %s
        """

        inserted = 0
        try:
            with self.get_connection_ctx() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (limit,))
                    rows = cursor.fetchall()

            for row in rows:
                url = row.get("url") or ""
                if not url or self.url_exists(url):
                    continue

                raw_item = RawArticleItem(
                    source_type="domestic",
                    source_name="新华网",
                    source_code="xinhua",
                    url=url,
                    title=row.get("title") or "",
                    author="",
                    content=row.get("content") or "",
                    description=(row.get("content") or "")[:200],
                    keywords=row.get("keywords") or "",
                    publish_time=row.get("publish_time"),
                    crawl_time=row.get("create_time") or datetime.now(),
                    raw_data={
                        "xinhua": {
                            "url": url,
                            "title": row.get("title"),
                            "publish_time": row.get("publish_time"),
                            "channel": row.get("channel"),
                            "images": row.get("images"),
                            "videos": row.get("videos"),
                            "keywords": row.get("keywords"),
                        }
                    }
                )

                if self.insert_raw_article(raw_item, source_id):
                    inserted += 1

            return inserted
        except pymysql.Error as e:
            self.logger.error(f"同步新华网到原始文章表失败: {e}")
            return inserted

    # ==================== 来源查询 ====================

    def get_source_by_code(self, code: str) -> Optional[Dict]:
        """根据来源编码获取来源信息"""
        query = f"SELECT * FROM {self.get_table_name('sources')} WHERE code = %s"
        try:
            with self.get_connection_ctx() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (code,))
                    return cursor.fetchone()
        except pymysql.Error as e:
            self.logger.error(f"查询来源失败: {e}")
            return None

    def get_all_sources(self, source_type: Optional[str] = None) -> List[Dict]:
        """获取所有来源"""
        if source_type:
            query = f"SELECT * FROM {self.get_table_name('sources')} WHERE source_type = %s AND is_active = 1"
        else:
            query = f"SELECT * FROM {self.get_table_name('sources')} WHERE is_active = 1"
        try:
            with self.get_connection_ctx() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (source_type,) if source_type else None)
                    return cursor.fetchall()
        except pymysql.Error as e:
            self.logger.error(f"查询来源列表失败: {e}")
            return []

    # ==================== 爬虫日志操作 ====================

    def log_spider_start(self, spider_name: str, source_id: Optional[int] = None) -> int:
        """
        记录爬虫开始执行

        Returns:
            int: 日志ID
        """
        query = f"""
        INSERT INTO {self.get_table_name('spider_logs')}
        (spider_name, source_id, start_time, status)
        VALUES (%s, %s, %s, 'running')
        """
        try:
            with self.get_connection_ctx() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (spider_name, source_id, datetime.now()))
                conn.commit()
                return cursor.lastrowid
        except pymysql.Error as e:
            self.logger.error(f"记录爬虫开始失败: {e}")
            return 0

    def log_spider_end(self, log_id: int, status: str, items_count: int, error_message: Optional[str] = None):
        """记录爬虫结束执行"""
        query = f"""
        UPDATE {self.get_table_name('spider_logs')}
        SET end_time = %s, status = %s, items_count = %s, error_message = %s,
            duration = TIMESTAMPDIFF(SECOND, start_time, %s)
        WHERE id = %s
        """
        try:
            with self.get_connection_ctx() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (
                        datetime.now(),
                        status,
                        items_count,
                        error_message,
                        datetime.now(),
                        log_id
                    ))
                conn.commit()
        except pymysql.Error as e:
            self.logger.error(f"记录爬虫结束失败: {e}")

    # ==================== 数据查询 ====================

    def get_recent_articles(self, limit: int = 100, offset: int = 0, source_type: Optional[str] = None, category: Optional[str] = None, source_code: Optional[str] = None) -> List[Dict]:
        """获取最近的采集文章"""
        conditions = []
        params = []
        
        if source_type:
            conditions.append("source_type = %s")
            params.append(source_type)
            
        if category:
            conditions.append("category = %s")
            params.append(category)

        if source_code:
            conditions.append("source_code = %s")
            params.append(source_code)
            
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        query = f"""
        SELECT * FROM {self.get_table_name('raw_articles')}
        {where_clause}
        ORDER BY crawl_time DESC
        LIMIT %s OFFSET %s
        """
        params.append(limit)
        params.append(offset)
        
        try:
            with self.get_connection_ctx() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, tuple(params))
                    return cursor.fetchall()
        except pymysql.Error as e:
            self.logger.error(f"查询文章失败: {e}")
            return []

    def close(self):
        """关闭连接（PyMySQL 连接是短连接，此方法保留以保持接口一致）"""
        pass
