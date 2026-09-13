"""
统一爬虫基类

提供所有爬虫的通用功能：
1. HTTP 请求处理
2. 关键词匹配
3. 编码处理
4. 时间格式化
5. 统一存储接口
"""

import re
import time
import random
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, List, Dict, Any

import requests
from bs4 import BeautifulSoup
import chardet
from dateutil import parser as dateparser

from .db import DBHandler
from .models import RawArticleItem


class BaseScraper(ABC):
    """所有爬虫的基类，定义通用接口和功能"""

    def __init__(self, config: dict, db_handler: DBHandler):
        """
        初始化爬虫

        Args:
            config: 配置字典
            db_handler: 数据库处理器
        """
        self.config = config
        self.db = db_handler
        self.logger = logging.getLogger(self.__class__.__name__)

        # 通用配置
        scraper_conf = config.get("scraper", {}) if isinstance(config.get("scraper"), dict) else {}
        
        self.request_delay = scraper_conf.get("request_delay", config.get("request_delay", 2))
        self.timeout = scraper_conf.get("timeout", config.get("timeout", 10))
        self.retry_times = scraper_conf.get("retry_times", config.get("retry_times", 3))
        self.user_agents = scraper_conf.get("user_agents", config.get("user_agents", [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        ]))

        # 源配置（子类覆盖）
        self.source_name = ""
        self.source_code = ""
        self.source_type = ""

    # ==================== HTTP 请求 ====================

    def get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.8,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

    def fetch(self, url: str, encoding: Optional[str] = None, headers: Optional[Dict[str, str]] = None, cookies: Optional[Dict[str, str]] = None) -> Optional[str]:
        """
        获取URL内容

        Args:
            url: 目标URL
            encoding: 指定编码，为None时自动检测
            headers: 自定义请求头
            cookies: Cookie字典

        Returns:
            str: 页面内容，失败返回 None
        """
        for attempt in range(self.retry_times):
            try:
                req_headers = self.get_headers()
                if headers:
                    req_headers.update(headers)

                response = requests.get(url, headers=req_headers, cookies=cookies, timeout=self.timeout)
                response.raise_for_status()

                # 自动检测编码
                if encoding:
                    return response.content.decode(encoding, errors="ignore")

                raw = response.content
                detected = chardet.detect(raw)
                enc = detected.get("encoding", "utf-8")
                if not enc or enc.lower() == "ascii":
                    enc = "utf-8"
                return raw.decode(enc, errors="ignore")

            except requests.Timeout:
                self.logger.warning(f"请求超时 (尝试 {attempt + 1}/{self.retry_times}): {url}")
            except requests.ConnectionError as e:
                self.logger.warning(f"连接失败 (尝试 {attempt + 1}/{self.retry_times}): {url} - {e}")
            except requests.HTTPError as e:
                self.logger.warning(f"HTTP错误 (尝试 {attempt + 1}/{self.retry_times}): {e}")
            except Exception as e:
                self.logger.error(f"请求异常: {url} - {e}")

            if attempt < self.retry_times - 1:
                time.sleep(random.uniform(1, 3))

        return None

    def fetch_binary(self, url: str) -> Optional[bytes]:
        """获取二进制内容（如图片）"""
        try:
            response = requests.get(url, headers=self.get_headers(), timeout=self.timeout)
            response.raise_for_status()
            return response.content
        except Exception as e:
            self.logger.error(f"获取二进制内容失败: {url} - {e}")
            return None

    # ==================== HTML 解析 ====================

    def parse_html(self, html: str, parser: str = "lxml") -> BeautifulSoup:
        """解析HTML"""
        return BeautifulSoup(html, parser)

    def extract_links(self, html: str, selector: str, base_url: str) -> List[str]:
        """
        提取链接

        Args:
            html: HTML内容
            selector: CSS选择器
            base_url: 基础URL

        Returns:
            List[str]: 绝对路径URL列表
        """
        from urllib.parse import urljoin
        soup = self.parse_html(html)
        nodes = soup.select(selector)
        urls = []
        for n in nodes:
            href = n.get("href")
            if href:
                urls.append(urljoin(base_url, href))
        return urls

    # ==================== 工具方法 ====================

    def check_keywords(self, text: str, keywords: List[str]) -> bool:
        """
        检查文本是否包含关键词

        Args:
            text: 待检查的文本
            keywords: 关键词列表

        Returns:
            bool: 是否包含任一关键词
        """
        if not text or not keywords:
            return False
        text_lower = text.lower()
        for kw in keywords:
            if kw.lower() in text_lower:
                return True
        return False

    def try_parse_date(self, text: str) -> Optional[datetime]:
        """
        尝试解析日期字符串

        Args:
            text: 日期字符串

        Returns:
            datetime: 解析后的日期，失败返回 None
        """
        if not text:
            return None
        try:
            return dateparser.parse(text, fuzzy=True)
        except Exception:
            return None

    def clean_text(self, text: str, max_length: Optional[int] = None) -> str:
        """
        清洗文本

        Args:
            text: 原始文本
            max_length: 最大长度

        Returns:
            str: 清洗后的文本
        """
        if text is None:
            return ""
        # 去除HTML标签
        text = re.sub(r'<[^>]+>', '', text)
        # 去除多余空白
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        if max_length and len(text) > max_length:
            text = text[:max_length]
        return text

    def random_delay(self):
        """随机延迟"""
        time.sleep(random.uniform(self.request_delay * 0.5, self.request_delay * 1.5))

    # ==================== 存储接口 ====================

    def save_to_database(self, item: RawArticleItem) -> bool:
        """
        保存到数据库

        Args:
            item: 原始文章数据

        Returns:
            bool: 保存成功返回 True
        """
        source = self.db.get_source_by_code(self.source_code)
        if not source:
            self.logger.warning(f"未知来源: {self.source_code}")
            return False

        source_id = source["id"]

        # 如果是热搜数据，同时保存到 hot_search 表
        if item.source_type == "hotsearch" and item.platform_id is not None:
            from .models import HotSearchItem
            hot_item = HotSearchItem(
                platform_id=item.platform_id,
                rank=item.rank or 0,
                title=item.title,
                author=item.author,
                url=item.url,
                crawl_time=item.crawl_time
            )
            self.db.insert_hotsearch(hot_item, source_id)

        return self.db.insert_raw_article(item, source_id)

    def url_exists(self, url: str) -> bool:
        """检查URL是否已存在"""
        return self.db.url_exists(url)

    # ==================== 抽象方法 ====================

    @abstractmethod
    def run(self) -> int:
        """
        执行爬取

        Returns:
            int: 采集的数据条数
        """
        pass

    @abstractmethod
    def get_source_config(self) -> Dict[str, Any]:
        """
        获取源配置

        Returns:
            dict: 源配置信息
        """
        pass

