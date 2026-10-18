"""
新华网爬虫 - 高并发异步混合采集
"""

import asyncio
import hashlib
import json
import logging
import random
import time
import re
import os
import threading
from collections import deque
from datetime import datetime
from typing import List, Dict, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from prometheus_client import Counter, Gauge, Histogram, start_http_server

from ..base import BaseScraper
from ..models import XinhuaNewsItem, RawArticleItem
from ..db import DBHandler

# Prometheus Metrics
SPIDER_QPS = Gauge('xinhua_spider_qps', 'Current QPS of Xinhua spider')
SPIDER_SUCCESS_RATE = Gauge('xinhua_spider_success_rate', 'Success rate of Xinhua spider')
SPIDER_ITEMS_TOTAL = Counter('xinhua_spider_items_total', 'Total items crawled', ['status'])
SPIDER_DURATION = Histogram('xinhua_spider_duration_seconds', 'Time spent processing a page')

class XinhuaScraper(BaseScraper):
    """
    新华网全量/增量爬虫
    特性：
    1. 混合模式：aiohttp (SSR) + Selenium/Edge (Ajax)
    2. 高并发：asyncio + Semaphore
    3. 自动反爬：Cookie池 + UA轮询 + 代理切换
    4. 监控：Prometheus 指标暴露
    """

    def __init__(self, config: dict, db_handler: DBHandler):
        super().__init__(config, db_handler)
        self.source_name = "新华网"
        self.source_code = "xinhua"
        self.base_url = "http://www.news.cn/"
        
        # 配置参数
        self.concurrency = 500  # 并发数
        self.limit_rate = 80    # 全局限速 r/s
        self.max_pages = 200    # 最大翻页数
        self.target_count = 3000 # 目标采集数量
        self.driver_path = os.path.abspath("msedgedriver.exe")
        self.detail_task_buffer = 50
        self.metrics_port = 8001
        self.exists_cache_size = 50000

        xinhua_conf = config.get("xinhua", {}) if isinstance(config.get("xinhua"), dict) else {}
        crawl_conf = xinhua_conf.get("crawl", xinhua_conf) if isinstance(xinhua_conf, dict) else {}
        if isinstance(crawl_conf, dict):
            if crawl_conf.get("concurrency") is not None:
                self.concurrency = int(crawl_conf.get("concurrency"))
            if crawl_conf.get("limit_rate") is not None:
                self.limit_rate = float(crawl_conf.get("limit_rate"))
            if crawl_conf.get("max_pages") is not None:
                self.max_pages = int(crawl_conf.get("max_pages"))
            if crawl_conf.get("target_count") is not None:
                self.target_count = int(crawl_conf.get("target_count"))
            if crawl_conf.get("driver_path"):
                self.driver_path = str(crawl_conf.get("driver_path"))
            if crawl_conf.get("detail_task_buffer") is not None:
                self.detail_task_buffer = int(crawl_conf.get("detail_task_buffer"))
            if crawl_conf.get("metrics_port") is not None:
                self.metrics_port = int(crawl_conf.get("metrics_port"))
            if crawl_conf.get("exists_cache_size") is not None:
                self.exists_cache_size = int(crawl_conf.get("exists_cache_size"))
        
        # 状态控制
        self.stop_event = asyncio.Event()
        self.crawled_urls: Set[str] = set()
        self.semaphore = asyncio.Semaphore(self.concurrency)
        self.proxy_pool = []  # 代理池 (模拟)
        self.cookie_pool = [] # Cookie池 (模拟)
        self._raw_exists_cache: Dict[str, bool] = {}
        self._raw_exists_order = deque()

        # 统计
        self.stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "duplicate": 0,
            "synced": 0,
            "start_time": None
        }
        self._source_id = 0
        self._parse_stats: Dict[str, Dict[str, int]] = {}
        self._dumped_failed: Dict[str, int] = {}
        self._schedule_lock = threading.Lock()
        self._schedule_cap = max(0, self.target_count + self.detail_task_buffer)
        self._scheduled_total = 0
        self._success_lock = threading.Lock()

    def run(self) -> int:
        """入口方法 (同步 -> 异步)"""
        self.logger.info(f"启动新华网爬虫... 目标: {self.target_count}条")
        self.stats["start_time"] = time.time()
        
        # 启动 Prometheus HTTP 服务 (如果尚未启动)
        try:
            start_http_server(self.metrics_port)
        except Exception:
            pass # 可能已被其他进程启动

        return asyncio.run(self._async_run())

    async def _async_run(self) -> int:
        """异步执行主逻辑"""
        source = self.db.get_source_by_code(self.source_code)
        self._source_id = source["id"] if source else 0

        # 获取频道列表
        channels = [
            {"name": "时政", "url": "http://www.news.cn/politics/", "code": "politics"},
            {"name": "国际", "url": "http://www.news.cn/world/", "code": "world"},
        ]

        async with aiohttp.ClientSession() as session:
            tasks = []
            
            # 强制合并高价值频道 (无论数据库是否有配置，都确保这些频道被覆盖)
            mandatory_channels = [
                # 基础频道
                {"name": "时政", "url": "http://www.news.cn/politics/", "code": "politics"},
                {"name": "国际", "url": "http://www.news.cn/world/", "code": "world"},
                {"name": "财经", "url": "http://www.news.cn/fortune/", "code": "fortune"},
                {"name": "法治", "url": "http://www.news.cn/legal/", "code": "legal"},
                {"name": "军事", "url": "http://www.news.cn/mil/", "code": "mil"},
                {"name": "文化", "url": "http://www.news.cn/culture/", "code": "culture"},
                {"name": "科技", "url": "http://www.news.cn/tech/", "code": "tech"},
                {"name": "能源", "url": "http://www.news.cn/energy/", "code": "energy"},
                {"name": "汽车", "url": "http://www.news.cn/auto/", "code": "auto"},
                {"name": "房产", "url": "http://www.news.cn/house/", "code": "house"},
                {"name": "食品", "url": "http://www.news.cn/food/", "code": "food"},
                {"name": "体育", "url": "http://www.news.cn/sports/", "code": "sports"},
                {"name": "健康", "url": "http://www.news.cn/health/", "code": "health"},
                {"name": "地方", "url": "http://www.news.cn/local/", "code": "local"},
                {"name": "科普", "url": "http://www.news.cn/science/", "code": "science"},
                {"name": "教育", "url": "http://education.news.cn/", "code": "education"},
                {"name": "旅游", "url": "http://travel.news.cn/", "code": "travel"},
                
                # 画像报告发现的高价值频道
                {"name": "国际-Globalink", "url": "http://www.news.cn/world/globalink/index.html", "code": "world_globalink"},
                {"name": "财经-观察", "url": "http://www.news.cn/fortune/insight/index.html", "code": "fortune_insight"},
                {"name": "亚太中文", "url": "http://www.news.cn/asia/chinese/index.html", "code": "asia_chinese"},
                {"name": "金融", "url": "http://www.news.cn/finance/", "code": "finance"},
                {"name": "理财", "url": "http://www.news.cn/money/index.html", "code": "money"},
                {"name": "信息化", "url": "https://www.news.cn/info/rdzt/2025qyjttdnh/", "code": "info_rdzt"},
                
                # 热门专题
                {"name": "专题-冬季运动", "url": "https://www.news.cn/sports/2025dswjqyh/index.html", "code": "sports_winter2025"},
                {"name": "专题-地球", "url": "http://www.news.cn/zt/dqjcpy/index.html", "code": "zt_dqjcpy"},
                {"name": "专题-百姓", "url": "https://www.news.cn/zt/bxzgjgxb/index.html", "code": "zt_bxzgjgxb"},
                {"name": "专题-文旅", "url": "http://www.news.cn/zt/whzgx2024/index.html", "code": "zt_whzgx2024"},
            ]
            
            existing_urls = {c.get('url') for c in channels}
            for mc in mandatory_channels:
                if mc['url'] not in existing_urls:
                    channels.append(mc)
                    existing_urls.add(mc['url'])

            for channel in channels:
                tasks.append(self._crawl_channel(session, channel))
            
            await asyncio.gather(*tasks)

        for channel_code, stats in self._parse_stats.items():
            items = sorted(stats.items(), key=lambda x: x[1], reverse=True)[:12]
            if not items:
                continue
            summary = ", ".join([f"{k}={v}" for k, v in items])
            self.logger.info(f"结构统计[{channel_code}]: {summary}")

        self.logger.info(f"爬取完成. 总计: {self.stats['total']}, 成功: {self.stats['success']}, 重复: {self.stats['duplicate']}")
        return self.stats["success"]

    async def _crawl_channel(self, session: aiohttp.ClientSession, channel: Dict):
        """爬取单个频道"""
        if self.stop_event.is_set():
            return
        self.logger.info(f"开始爬取频道: {channel['name']} ({channel['url']})")
        
        # 判断频道类型 (SSR vs Ajax) - 简化逻辑，实际可配置
        is_ajax = self._is_ajax_channel(channel['url'])
        
        if is_ajax:
            # 动态频道使用 Selenium，放入线程池执行
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._crawl_dynamic_channel_sync, channel)
        else:
            await self._crawl_static_channel(session, channel)

    def _is_ajax_channel(self, url: str) -> bool:
        """判断是否为动态加载频道"""
        # 示例：根据URL特征判断，或通过配置文件
        # fortune 虽然也是重定向，但静态跟随即可解决，暂不强制 AJAX
        dynamic_keywords = ['roll', 'info', 'photo'] 
        return any(k in url for k in dynamic_keywords)

    async def _crawl_static_channel(self, session: aiohttp.ClientSession, channel: Dict):
        """静态页面爬取 (aiohttp)"""
        current_page = 1
        empty_count = 0
        
        while current_page <= self.max_pages and not self.stop_event.is_set():
            if self.stats["success"] >= self.target_count:
                self.stop_event.set()
                break
            # 构造分页URL (需根据实际新华网规则调整)
            if current_page == 1:
                url = channel['url']
            else:
                if channel['url'].endswith('/'):
                    url = f"{channel['url']}index_{current_page}.htm"
                else:
                    url = f"{channel['url']}/index_{current_page}.htm"

            content = await self._fetch(session, url)
            if not content:
                empty_count += 1
                if empty_count > 3: break
                continue

            urls = self._extract_urls(content, channel['url']) # 注意：这里如果 content 来自重定向后的页面，extract_urls 的 base_url 可能需要更新，但 fetch 返回的是内容字符串，丢失了最终 URL 信息。不过对于列表页，影响通常不大，除非相对路径非常复杂。
            if not urls:
                break
                
            # 并发爬取详情页
            selected_urls = [u for u in urls if u not in self.crawled_urls]
            allowed = self._reserve_schedule_slots(len(selected_urls))
            if allowed <= 0:
                self.stop_event.set()
                break
            selected_urls = selected_urls[:allowed]
            detail_tasks = [self._process_article(session, u, channel) for u in selected_urls]
            await asyncio.gather(*detail_tasks)
            
            current_page += 1
            await asyncio.sleep(random.uniform(0.5, 1.5))

    def _crawl_dynamic_channel_sync(self, channel: Dict):
        if self.stop_event.is_set():
            return
        if not os.path.exists(self.driver_path):
            self.logger.error(f"EdgeDriver 未找到: {self.driver_path}")
            return

        options = EdgeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument(f"user-agent={self._get_random_ua()}")

        service = EdgeService(executable_path=self.driver_path)
        driver = None
        loop = None

        try:
            driver = webdriver.Edge(service=service, options=options)
            driver.get(channel['url'])

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._crawl_dynamic_channel_async(driver, channel))
        except Exception as e:
            self.logger.error(f"Selenium 爬取异常: {e}")
        finally:
            try:
                if loop:
                    loop.close()
            finally:
                if driver:
                    driver.quit()

    async def _crawl_dynamic_channel_async(self, driver, channel: Dict):
        seen = set()
        async with aiohttp.ClientSession() as sub_session:
            for _ in range(self.max_pages):
                if self.stop_event.is_set():
                    break
                if self.stats["success"] >= self.target_count:
                    self.stop_event.set()
                    break

                links = driver.find_elements(By.TAG_NAME, "a")
                batch = []
                for link in links:
                    try:
                        href = link.get_attribute("href")
                        if not href:
                            continue
                        href = self._normalize_url(href)
                        if href in seen:
                            continue
                        if href in self.crawled_urls:
                            continue
                        if self._is_valid_url(href):
                            seen.add(href)
                            batch.append(href)
                    except Exception:
                        continue

                if batch:
                    allowed = self._reserve_schedule_slots(len(batch))
                    if allowed <= 0:
                        self.stop_event.set()
                        break
                    selected = batch[:allowed]
                    tasks = [self._process_article(sub_session, u, channel) for u in selected]
                    await asyncio.gather(*tasks)

                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                await asyncio.sleep(2)

    async def _fetch(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        content, _, _ = await self._fetch_ex(session, url)
        return content

    async def _fetch_ex(self, session: aiohttp.ClientSession, url: str) -> Tuple[Optional[str], str, bool]:
        current_url = url
        redirected = False
        last_effective_url = url

        for hop in range(4):
            content, effective_url = await self._fetch_once(session, current_url)
            if not content:
                return None, effective_url or last_effective_url, redirected

            last_effective_url = effective_url or last_effective_url

            redirect_match = re.search(r'window\.location\.href\s*=\s*["\']([^"\']+)["\']', content)
            if not redirect_match:
                return content, last_effective_url, redirected or (last_effective_url != url)

            new_url = redirect_match.group(1)
            full_redirect_url = urljoin(last_effective_url or current_url, new_url)
            self.logger.info(f"JS重定向检测: {current_url} -> {full_redirect_url}")
            current_url = full_redirect_url
            redirected = True

        self.logger.warning(f"重定向次数过多: {url}")
        return None, last_effective_url, True

    async def _fetch_once(self, session: aiohttp.ClientSession, url: str) -> Tuple[Optional[str], str]:
        async with self.semaphore:
            await asyncio.sleep(1 / self.limit_rate)

            headers = {"User-Agent": self._get_random_ua()}
            proxy = self._get_random_proxy()

            for _ in range(3):
                try:
                    with SPIDER_DURATION.time():
                        async with session.get(url, headers=headers, proxy=proxy, timeout=10, ssl=False) as response:
                            effective_url = str(response.url) if getattr(response, "url", None) else url
                            if response.status == 200:
                                raw = await response.read()
                                content = ""
                                try:
                                    content = raw.decode('utf-8')
                                except UnicodeDecodeError:
                                    try:
                                        content = raw.decode('gbk')
                                    except Exception:
                                        content = raw.decode('utf-8', errors='ignore')

                                return content, effective_url

                            if response.status in [403, 302]:
                                self.logger.warning(f"触发反爬 {response.status}: {url}")
                                proxy = self._switch_proxy()
                except Exception as e:
                    self.logger.debug(f"请求失败 {url}: {e}")

                await asyncio.sleep(random.uniform(1, 3))

            return None, url

    async def _process_article(self, session: aiohttp.ClientSession, url: str, channel: Dict):
        """处理单篇文章"""
        if self.stop_event.is_set():
            return
        url = self._normalize_url(url)
        if self.stats["success"] >= self.target_count:
            self.stop_event.set()
            return
        self.stats["total"] += 1
        if url in self.crawled_urls:
            self.stats["duplicate"] += 1
            return

        if self._cached_raw_url_exists(url):
            self.stats["duplicate"] += 1
            self._mark_crawled(url)
            return

        html = await self._fetch(session, url)
        if not html:
            self.stats["failed"] += 1
            SPIDER_ITEMS_TOTAL.labels(status='failed').inc()
            return

        try:
            item, reason = self._parse_article(html, url, channel)
            if item:
                if not self._can_accept_success():
                    self.stop_event.set()
                    self._mark_crawled(url)
                    return
                try:
                    loop = asyncio.get_running_loop()
                    success = await loop.run_in_executor(None, self._save_article, item)
                except RuntimeError:
                    success = self._save_article(item)
                
                if success:
                    if not self._commit_success():
                        self.stop_event.set()
                        self._mark_crawled(url)
                        return
                    SPIDER_ITEMS_TOTAL.labels(status='success').inc()
                    self._mark_crawled(url)
                    self._raw_exists_cache[url] = True
                    self._raw_exists_order.append(url)
                    self._evict_exists_cache(self._raw_exists_cache, self._raw_exists_order)
                else:
                    self.stats["failed"] += 1
            else:
                self.logger.warning(f"解析失败 ({reason}): {url}")
                self._dump_failed_html(channel.get("code") or "unknown", url, html, reason)
                self.stats["failed"] += 1
        except Exception as e:
            self.logger.error(f"解析错误 {url}: {e}")
            self._dump_failed_html(channel.get("code") or "unknown", url, html, "exception")
            self.stats["failed"] += 1

    def _parse_article(self, html: str, url: str, channel: Dict) -> Tuple[Optional[XinhuaNewsItem], str]:
        """解析文章内容"""
        soup = BeautifulSoup(html, 'lxml')
        
        # 标题
        title, title_selector = self._select_first(soup, ['h1', '.title', '#title', '.h-title', '.tit'])
        if not title:
            self._record_parse(channel.get("code") or "unknown", "missing_title")
            return None, "missing_title"
        title_text = title.get_text(strip=True)
        
        # 发布时间
        pub_time = None
        time_meta, time_selector = self._select_first(soup, ['meta[name="publishdate"]', 'meta[name="pubdate"]', '.time', '.info'])
        if time_meta:
            raw_time = time_meta.get('content') or time_meta.get_text(strip=True)
            pub_time = self.try_parse_date(raw_time)
            
        # 正文
        content_div, content_selector = self._select_first(soup, [
            '#Content',
            '#detail',
            '#p-detail',
            'article',
            '.article',
            '.main-content',
            '#xinwen',
            '.con_text',
            '.xl_content',
            '#article',
            '.main_text',
            '.main-article',
            '.domPC',
            '.content',
            '.contentMain'
        ])
        if not content_div:
            self._record_parse(channel.get("code") or "unknown", "missing_content")
            return None, "missing_content"
        
        # 清理
        for tag in content_div(['script', 'style', 'iframe']):
            tag.decompose()
            
        content = content_div.get_text(separator='\n', strip=True)
        if not content:
            self._record_parse(channel.get("code") or "unknown", "empty_content")
            return None, "empty_content"
        
        # 图片
        images = [urljoin(url, img['src']) for img in content_div.select('img[src]')]

        code = channel.get("code") or "unknown"
        self._record_parse(code, f"title:{title_selector or 'none'}")
        self._record_parse(code, f"time:{time_selector or 'none'}")
        self._record_parse(code, f"content:{content_selector or 'none'}")
        
        return XinhuaNewsItem(
            url=url,
            title=title_text,
            content=content,
            publish_time=pub_time,
            source="新华网",
            channel=channel['code'],
            images=images,
            keywords=""
        ), "ok"

    def _select_first(self, soup: BeautifulSoup, selectors: List[str]):
        for selector in selectors:
            node = soup.select_one(selector)
            if node:
                return node, selector
        return None, ""

    def _record_parse(self, channel_code: str, key: str):
        bucket = self._parse_stats.get(channel_code)
        if not bucket:
            bucket = {}
            self._parse_stats[channel_code] = bucket
        bucket[key] = bucket.get(key, 0) + 1

    def _dump_failed_html(self, channel_code: str, url: str, html: str, reason: str):
        # 用户已禁用失败报告生成
        return

    def _save_article(self, item: XinhuaNewsItem) -> bool:
        """保存文章到 raw_articles"""
        if not self._source_id:
            return False
        raw_item = self._raw_item_from_xinhua_item(item)
        return self.db.insert_raw_article(raw_item, self._source_id)

    def _raw_item_from_xinhua_item(self, item: XinhuaNewsItem) -> RawArticleItem:
        return RawArticleItem(
            source_type="domestic",
            source_name=self.source_name,
            source_code=self.source_code,
            url=item.url,
            title=item.title,
            author=item.editor or "",
            content=item.content,
            description=(item.content or "")[:200],
            keywords=item.keywords or "",
            publish_time=item.publish_time,
            raw_data={
                "xinhua": {
                    "channel": item.channel,
                    "images": item.images,
                    "videos": item.videos,
                    "subtitle": item.subtitle,
                    "editor": item.editor
                }
            }
        )

    def _raw_item_from_xinhua_row(self, row: Dict) -> RawArticleItem:
        content = row.get("content") or ""
        return RawArticleItem(
            source_type="domestic",
            source_name=self.source_name,
            source_code=self.source_code,
            url=row.get("url") or "",
            title=row.get("title") or "",
            author=row.get("editor") or "",
            content=content,
            description=content[:200],
            keywords=row.get("keywords") or "",
            publish_time=row.get("publish_time"),
            crawl_time=row.get("create_time") or datetime.now(),
            raw_data={"xinhua": row}
        )

    def _extract_urls(self, html: str, base_url: str) -> List[str]:
        """提取列表页URL"""
        soup = BeautifulSoup(html, 'lxml')
        urls = []
        raw_links = soup.select('a[href]')
        for a in raw_links:
            href = a['href']
            full_url = urljoin(base_url, href)
            normalized = self._normalize_url(full_url)
            if self._is_valid_url(normalized):
                urls.append(normalized)
        
        urls = self._dedupe_urls(urls)
        self.logger.info(f"提取URL: {len(urls)} / {len(raw_links)} (有效/总数) from {base_url}")
        return urls

    def _is_valid_url(self, url: str) -> bool:
        """URL过滤器"""
        if not url.startswith('http'): return False
        
        # 1. 严格校验域名
        parsed = urlparse(url)
        domain = parsed.netloc
        if 'news.cn' not in domain and 'xinhuanet.com' not in domain: 
            return False
            
        # 2. 排除特定关键词
        if any(x in url for x in ['.jpg', '.png', '.css', '.js', 'video', 'share.php']): 
            return False
            
        # 3. 兼容 YYYYMMDD (8位数字) 和 YYYY-MM/DD 格式
        # /c_\d+ 是旧版 ID 格式，保留兼容
        # 仅匹配 path 部分，避免匹配到 query 参数中的 URL
        path = parsed.path
        return bool(re.search(r'(\d{4}-\d{2}/\d{2})|(\d{8})|(/c_\d+)', path))

    def _normalize_url(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return url
            return parsed._replace(query="", fragment="").geturl()
        except Exception:
            return url

    def _dedupe_urls(self, urls: List[str]) -> List[str]:
        seen = set()
        out: List[str] = []
        for u in urls:
            if not u:
                continue
            if u in seen:
                continue
            seen.add(u)
            out.append(u)
        return out

    def _cached_raw_url_exists(self, url: str) -> bool:
        if url in self._raw_exists_cache:
            return self._raw_exists_cache[url]
        exists = bool(self.db.url_exists(url))
        self._raw_exists_cache[url] = exists
        self._raw_exists_order.append(url)
        self._evict_exists_cache(self._raw_exists_cache, self._raw_exists_order)
        return exists

    def _evict_exists_cache(self, cache: Dict[str, bool], order: deque):
        if self.exists_cache_size <= 0:
            cache.clear()
            order.clear()
            return
        while len(order) > self.exists_cache_size:
            old = order.popleft()
            cache.pop(old, None)

    def _reserve_schedule_slots(self, requested: int) -> int:
        if requested <= 0:
            return 0
        with self._schedule_lock:
            remaining = self._schedule_cap - self._scheduled_total
            if remaining <= 0:
                return 0
            allowed = min(requested, remaining)
            self._scheduled_total += allowed
            return allowed

    def _can_accept_success(self) -> bool:
        with self._success_lock:
            return self.stats["success"] < self.target_count

    def _commit_success(self, synced: bool = False) -> bool:
        with self._success_lock:
            if self.stats["success"] >= self.target_count:
                return False
            if synced:
                self.stats["synced"] += 1
            self.stats["success"] += 1
            if self.stats["success"] >= self.target_count:
                self.stop_event.set()
            return True

    def _is_duplicate(self, url: str) -> bool:
        """去重逻辑"""
        # 1. 内存去重
        if url in self.crawled_urls:
            return True
        return self.db.url_exists(url)

    def _mark_crawled(self, url: str):
        self.crawled_urls.add(url)

    def _get_random_ua(self):
        return random.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ])

    def _get_random_proxy(self):
        # 模拟代理池
        return None 

    def _switch_proxy(self):
        return None
    
    # 兼容 BaseScraper 接口
    def get_source_config(self):
        return {"name": self.source_name, "code": self.source_code}


class XinhuaChannelDiscoverScraper(XinhuaScraper):
    def __init__(self, config: dict, db_handler: DBHandler):
        super().__init__(config, db_handler)
        discover_conf = (config.get("xinhua") or {}).get("discover") if isinstance(config.get("xinhua"), dict) else {}
        self.discover_output_dir = discover_conf.get("output_dir") or os.path.join(os.getcwd(), "logs")
        self.discover_max_candidates = int(discover_conf.get("max_candidates", 200))
        self.discover_pages_per_channel = int(discover_conf.get("pages_per_channel", 2))
        self.discover_sample_articles = int(discover_conf.get("sample_articles", 10))
        self.discover_seeds = discover_conf.get("seeds") or []

        self.concurrency = int(discover_conf.get("concurrency", 50))
        self.limit_rate = float(discover_conf.get("limit_rate", 20))
        self.semaphore = asyncio.Semaphore(self.concurrency)

    def run(self) -> int:
        self.logger.info("启动新华网频道发现与画像模式...")
        return asyncio.run(self._async_discover())

    async def _async_discover(self) -> int:
        seeds = self._get_discover_seeds()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(self.discover_output_dir, exist_ok=True)
        output_path = os.path.join(self.discover_output_dir, f"xinhua_channel_report_{timestamp}.json")

        report: Dict[str, object] = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "seeds": seeds,
            "candidates": [],
            "channels": []
        }

        async with aiohttp.ClientSession() as session:
            candidates = await self._discover_channel_candidates(session, seeds)
            report["candidates"] = candidates

            tasks = [self._profile_channel(session, u) for u in candidates[: self.discover_max_candidates]]
            results = await asyncio.gather(*tasks)
            report["channels"] = [r for r in results if r]

        report["suggested_channels"] = self._suggest_channels(report["channels"])
        report["suggested_sql"] = self._suggest_channel_sql(report["suggested_channels"])

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        self.logger.info(f"频道画像报告已生成: {output_path}")
        return len(report.get("channels") or [])

    def _suggest_channels(self, channels: List[Dict[str, object]]) -> List[Dict[str, object]]:
        suggestions = []
        used_codes = set()
        for ch in channels:
            probe = ch.get("article_probe") or {}
            sample_total = int(probe.get("sample_total") or 0)
            ok = int(probe.get("ok") or 0)
            if sample_total <= 0:
                continue
            ok_ratio = ok / sample_total
            if ok_ratio < 0.6:
                continue

            url = ch.get("channel_url")
            raw_code = ch.get("code_guess") or "unknown"
            code = self._sanitize_channel_code(str(raw_code))
            if code in used_codes and url:
                digest = hashlib.md5(str(url).encode("utf-8")).hexdigest()[:6]
                code = f"{code}_{digest}"
            used_codes.add(code)

            suggestions.append({
                "channel_url": url,
                "code_guess": code,
                "ok_ratio": round(ok_ratio, 3),
                "article_urls_unique": int(ch.get("article_urls_unique") or 0)
            })

        suggestions.sort(key=lambda x: (x.get("ok_ratio", 0), x.get("article_urls_unique", 0)), reverse=True)
        return suggestions

    def _suggest_channel_sql(self, suggested_channels: List[Dict[str, object]]) -> List[str]:
        sqls = []
        used_codes = set()
        for ch in suggested_channels:
            url = ch.get("channel_url")
            code = ch.get("code_guess") or "unknown"
            if not url:
                continue
            code = self._sanitize_channel_code(str(code))
            if code in used_codes:
                digest = hashlib.md5(str(url).encode("utf-8")).hexdigest()[:6]
                code = f"{code}_{digest}"
            used_codes.add(code)

            name = str(code)
            safe_name = name.replace("'", "''")
            safe_code = code.replace("'", "''")
            safe_url = str(url).replace("'", "''")
            sqls.append(
                "INSERT INTO xinhua_channel (name, code, url, category, is_active, description) "
                f"VALUES ('{safe_name}', '{safe_code}', '{safe_url}', 'news', 0, 'discover_suggest');"
            )
        return sqls

    def _get_discover_seeds(self) -> List[str]:
        seeds = []
        if isinstance(self.discover_seeds, list):
            seeds.extend([s for s in self.discover_seeds if isinstance(s, str) and s.strip()])

        seeds.append(self.base_url)
        unique = []
        seen = set()
        for u in seeds:
            if u in seen:
                continue
            seen.add(u)
            unique.append(u)
        return unique

    async def _discover_channel_candidates(self, session: aiohttp.ClientSession, seeds: List[str]) -> List[str]:
        candidates: List[str] = []
        seen = set()

        for seed in seeds:
            html, effective_url, _ = await self._fetch_ex(session, seed)
            if not html:
                continue
            seed_candidates = self._extract_channel_candidates(html, effective_url or seed)
            for u in seed_candidates:
                if u in seen:
                    continue
                seen.add(u)
                candidates.append(u)

        candidates.sort()
        return candidates[: self.discover_max_candidates]

    def _extract_channel_candidates(self, html: str, base_url: str) -> List[str]:
        soup = BeautifulSoup(html, "lxml")
        urls: List[str] = []
        for a in soup.select("a[href]"):
            href = a.get("href")
            if not href:
                continue
            full_url = urljoin(base_url, href)
            if self._looks_like_channel_url(full_url):
                urls.append(full_url)
        return list(dict.fromkeys(urls))

    def _looks_like_channel_url(self, url: str) -> bool:
        if not url.startswith("http"):
            return False

        parsed = urlparse(url)
        domain = parsed.netloc
        if "news.cn" not in domain and "xinhuanet.com" not in domain:
            return False

        if any(x in url for x in [".jpg", ".png", ".css", ".js", "#"]):
            return False

        path = (parsed.path or "/").rstrip("/")
        if not path or path == "":
            return True

        if re.search(r'(\d{4}-\d{2}/\d{2})|(\d{8})|(/c_\d+)', path):
            return False

        segments = [s for s in path.split("/") if s]
        if len(segments) > 3:
            return False

        if segments and segments[-1].lower().startswith("index"):
            return True

        return url.endswith("/")

    async def _profile_channel(self, session: aiohttp.ClientSession, channel_url: str) -> Optional[Dict[str, object]]:
        code_guess = self._guess_channel_code(channel_url)
        is_ajax_guess = self._is_ajax_channel(channel_url)

        list_pages = self._build_list_pages(channel_url, self.discover_pages_per_channel)
        list_results = []
        article_urls: List[str] = []

        for page_url in list_pages:
            html, effective_url, redirected = await self._fetch_ex(session, page_url)
            ok = bool(html)
            extracted = []
            if html:
                extracted = self._extract_urls(html, effective_url or page_url)
                article_urls.extend(extracted)

            list_results.append({
                "url": page_url,
                "effective_url": effective_url,
                "ok": ok,
                "redirected": redirected,
                "extracted_total": len(extracted)
            })

        unique_articles = list(dict.fromkeys(article_urls))
        sample_articles = unique_articles[: self.discover_sample_articles]

        probe_stats = {
            "sample_total": len(sample_articles),
            "ok": 0,
            "reasons": {},
            "title_selectors": {},
            "time_selectors": {},
            "content_selectors": {}
        }

        for u in sample_articles:
            html, effective_url, redirected = await self._fetch_ex(session, u)
            if not html:
                probe_stats["reasons"]["fetch_failed"] = probe_stats["reasons"].get("fetch_failed", 0) + 1
                continue

            probe = self._probe_article(html)
            if probe.get("ok"):
                probe_stats["ok"] += 1
            else:
                reason = str(probe.get("reason") or "unknown")
                probe_stats["reasons"][reason] = probe_stats["reasons"].get(reason, 0) + 1

            for k, v in [("title_selectors", probe.get("title_selector")), ("time_selectors", probe.get("time_selector")), ("content_selectors", probe.get("content_selector"))]:
                if not v:
                    continue
                probe_stats[k][v] = probe_stats[k].get(v, 0) + 1

        return {
            "channel_url": channel_url,
            "code_guess": code_guess,
            "is_ajax_guess": is_ajax_guess,
            "list_pages": list_results,
            "article_urls_total": len(article_urls),
            "article_urls_unique": len(unique_articles),
            "article_urls_sample": sample_articles,
            "article_probe": probe_stats
        }

    def _build_list_pages(self, channel_url: str, pages: int) -> List[str]:
        urls: List[str] = []
        base = channel_url
        parsed = urlparse(base)
        path = parsed.path or "/"
        is_dir = base.endswith("/")
        is_html = path.lower().endswith((".htm", ".html"))
        if not is_dir and not is_html:
            base = base + "/"
            parsed = urlparse(base)
            path = parsed.path or "/"

        for i in range(1, max(1, pages) + 1):
            if i == 1:
                urls.append(base)
                continue
            page_path = path
            if page_path.lower().endswith(("index.htm", "index.html")):
                page_path = re.sub(r'index\.(htm|html)$', f'index_{i}.htm', page_path, flags=re.IGNORECASE)
            elif page_path.lower().endswith((".htm", ".html")):
                page_path = page_path.rsplit("/", 1)[0].rstrip("/") + f"/index_{i}.htm"
            else:
                page_path = page_path.rstrip("/") + f"/index_{i}.htm"

            urls.append(parsed._replace(path=page_path, query="", fragment="").geturl())

        return urls

    def _guess_channel_code(self, channel_url: str) -> str:
        try:
            parsed = urlparse(channel_url)
            netloc = (parsed.netloc or "").lower()
            host_label = ""
            if netloc:
                host_label = netloc.split(":")[0].split(".")[0]
                if host_label == "www":
                    host_label = ""

            segments = [s for s in (parsed.path or "").split("/") if s]
            code = ""
            if segments:
                head = segments[0].lower()
                if not head.startswith("index") and not head.endswith((".htm", ".html")):
                    code = head
            if not code and host_label:
                code = host_label
            return self._sanitize_channel_code(code or "unknown")
        except Exception:
            pass
        return "unknown"

    def _sanitize_channel_code(self, code: str) -> str:
        cleaned = re.sub(r"[^a-z0-9_-]+", "_", (code or "").lower()).strip("_")
        return cleaned or "unknown"

    def _probe_article(self, html: str) -> Dict[str, object]:
        soup = BeautifulSoup(html, "lxml")

        title, title_selector = self._select_first(soup, ['h1', '.title', '#title', '.h-title', '.tit'])
        if not title:
            return {"ok": False, "reason": "missing_title", "title_selector": title_selector}

        time_meta, time_selector = self._select_first(soup, ['meta[name=\"publishdate\"]', 'meta[name=\"pubdate\"]', '.time', '.info'])
        pub_time = None
        if time_meta:
            raw_time = time_meta.get('content') or time_meta.get_text(strip=True)
            pub_time = self.try_parse_date(raw_time)

        content_div, content_selector = self._select_first(soup, [
            '#Content',
            '#detail',
            '#p-detail',
            'article',
            '.article',
            '.main-content',
            '#xinwen',
            '.con_text',
            '.xl_content',
            '#article',
            '.main_text',
            '.main-article',
            '.domPC',
            '.content',
            '.contentMain'
        ])
        if not content_div:
            return {"ok": False, "reason": "missing_content", "title_selector": title_selector, "time_selector": time_selector, "content_selector": content_selector}

        for tag in content_div(['script', 'style', 'iframe']):
            tag.decompose()

        content = content_div.get_text(separator='\n', strip=True)
        if not content:
            return {"ok": False, "reason": "empty_content", "title_selector": title_selector, "time_selector": time_selector, "content_selector": content_selector}

        return {
            "ok": True,
            "title_selector": title_selector,
            "time_selector": time_selector if pub_time else (time_selector or "none"),
            "content_selector": content_selector
        }
