"""
数据库操作模块

提供统一的数据库连接管理和数据操作接口，支持：
1. 原始文章存储 (raw_articles表)
2. 爬虫日志 (spider_logs表)
3. ML结果 (ml_results表)
4. 事件 (events表)
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
                - table_prefix: 表前缀 (默认空)
        """
        self.config = config
        self.host = config.get("host", "localhost")
        self.port = config.get("port", 3306)
        self.username = config.get("username", "root")
        self.password = config.get("password", "")
        self.database = config.get("name", "news_scraper")
        self.charset = config.get("charset", "utf8mb4")
        self.table_prefix = config.get("table_prefix", "")

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
                rank_value INT UNSIGNED DEFAULT NULL,
                crawl_time DATETIME NOT NULL,
                raw_data JSON DEFAULT NULL,
                status ENUM('pending', 'cleaned', 'classified', 'failed') DEFAULT 'pending',
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
            CREATE TABLE IF NOT EXISTS {self.get_table_name('ml_results')} (
                id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
                article_id BIGINT UNSIGNED NOT NULL,
                task_type ENUM('classification', 'sentiment', 'embedding', 'ner', 'event') NOT NULL,
                model_name VARCHAR(128) NOT NULL,
                model_version VARCHAR(64) DEFAULT NULL,
                label VARCHAR(128) DEFAULT NULL,
                score DECIMAL(6,5) DEFAULT NULL,
                result_data JSON DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_article (article_id),
                INDEX idx_task_type (task_type),
                INDEX idx_model (model_name),
                INDEX idx_created (created_at)
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
                status ENUM('running', 'success', 'failed', 'stopped') DEFAULT 'running',
                items_count INT DEFAULT 0,
                error_message TEXT DEFAULT NULL,
                duration INT UNSIGNED DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_source (source_id),
                INDEX idx_start_time (start_time),
                INDEX idx_status (status)
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
         `rank_value`, crawl_time, raw_data, status)
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

    # ==================== 来源查询 ====================

    def get_source_by_code(self, code: str) -> Optional[Dict]:
        """根据来源编码获取来源信息"""
        query = f"SELECT * FROM scraper_sources WHERE code = %s"
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
            query = f"SELECT * FROM scraper_sources WHERE source_type = %s AND is_active = 1"
        else:
            query = f"SELECT * FROM scraper_sources WHERE is_active = 1"
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
