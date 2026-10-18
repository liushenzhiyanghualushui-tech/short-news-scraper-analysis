"""网易新闻爬虫 - 高并发异步版 (API + aiohttp)"""

import asyncio
import re
import logging
import time
import random
import json
from typing import List, Dict, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from ..base import BaseScraper
from ..models import DomesticNewsItem, RawArticleItem

class NeteaseScraper(BaseScraper):
    """
    网易新闻高并发爬虫
    使用 3g.163.com 的 JSON API 获取列表，使用 aiohttp 异步获取详情
    """

    def __init__(self, config: dict, db_handler):
        super().__init__(config, db_handler)
        self.source_name = "网易新闻"
        self.source_code = "netease"
        self.seed_url = "https://news.163.com/"
        
        # 配置参数
        self.target_count = 3000  # 目标数量
        self.concurrency = 100    # 并发数
        self.limit_rate = 100     # 速率限制
        
        # 状态控制
        self.stop_event = asyncio.Event()
        self.crawled_urls: Set[str] = set()
        self.semaphore = asyncio.Semaphore(self.concurrency)
        self.stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "duplicate": 0
        }
        
        # 网易新闻 API 频道 ID 映射
        # API 格式: https://3g.163.com/touch/reconstruct/article/list/{ID}/{Offset}-{Limit}.html
        self.channels = {
            "news": "BBM54PGAwangning",      # 新闻/头条
            "entertainment": "BA10TA81wangning", # 娱乐
            "sports": "BA8E6OEOwangning",    # 体育
            "finance": "BA8EE5GMwangning",   # 财经
            "tech": "BA8D4A3Rwangning",      # 科技
            "military": "BAI67OGGwangning",  # 军事
            "mobile": "BAI6I0O5wangning",    # 手机
            "digital": "BAI6JOD9wangning",   # 数码
            "travel": "BEO4GINLwangning",    # 旅游
            "auto": "BA8DOPCSwangning",      # 汽车
            "home": "BAI6P3NDwangning",      # 家居
        }

    def get_source_config(self) -> Dict:
        """获取源配置"""
        return {
            "name": self.source_name,
            "code": self.source_code,
            "type": "domestic",
            "seed_url": self.seed_url
        }

    def run(self) -> int:
        """执行爬取 (同步入口)"""
        self.logger.info(f"启动{self.source_name}爬虫 (API模式)... 目标: {self.target_count}条")
        start_time = time.time()
        
        try:
            # 运行异步任务
            count = asyncio.run(self._async_run())
            
            duration = time.time() - start_time
            self.logger.info(f"{self.source_name} 爬取完成，耗时 {duration:.1f}秒")
            self.logger.info(f"统计: 总处理 {self.stats['total']}, 成功入库 {count}, 重复 {self.stats['duplicate']}, 失败 {self.stats['failed']}")
            return count
            
        except Exception as e:
            self.logger.error(f"{self.source_name} 运行出错: {e}")
            import traceback
            traceback.print_exc()
            return 0

    async def _async_run(self) -> int:
        """异步主逻辑"""
        source = self.db.get_source_by_code(self.source_code)
        self._source_id = source["id"] if source else 0

        async with aiohttp.ClientSession() as session:
            tasks = []
            # 为每个频道创建采集任务
            for name, channel_id in self.channels.items():
                tasks.append(self._crawl_channel_api(session, name, channel_id))
            
            await asyncio.gather(*tasks)
            
        return self.stats["success"]

    async def _crawl_channel_api(self, session: aiohttp.ClientSession, channel_name: str, channel_id: str):
        """爬取单个频道的 API"""
        offset = 0
        limit = 20 # 每次获取 20 条
        
        # 分离计数器：fetch_error_count (网络/解析错误), duplicate_count (连续重复)
        fetch_error_count = 0
        duplicate_count = 0
        
        self.logger.info(f"开始爬取频道: {channel_name} (ID: {channel_id})")
        
        while not self.stop_event.is_set():
            if self.stats["success"] >= self.target_count:
                self.stop_event.set()
                break
                
            # 构造 API URL
            # 格式: https://3g.163.com/touch/reconstruct/article/list/BBM54PGAwangning/0-20.html
            api_url = f"https://3g.163.com/touch/reconstruct/article/list/{channel_id}/{offset}-{limit}.html"
            
            try:
                content = await self._fetch(session, api_url)
                if not content:
                    fetch_error_count += 1
                    if fetch_error_count > 10: 
                        self.logger.warning(f"频道 {channel_name} 连续 {fetch_error_count} 次请求失败，停止爬取")
                        break
                    continue
                
                # 解析 JSONP
                # 响应格式: artiList({...})
                json_str = self._clean_jsonp(content)
                if not json_str:
                    fetch_error_count += 1
                    continue
                
                # 成功获取内容，重置错误计数
                fetch_error_count = 0
                    
                data = json.loads(json_str)
                articles = data.get(channel_id, [])
                
                if not articles:
                    self.logger.info(f"频道 {channel_name} 无更多数据")
                    break
                
                # 提取文章 URL 并并发处理
                tasks = []
                new_urls_count = 0
                
                for article in articles:
                    if self.stats["success"] >= self.target_count:
                        break
                    
                    # 增强 URL 提取，兼容不同字段
                    url = article.get('url') or article.get('docurl') or article.get('weburl')
                    if not url:
                        # 尝试构建 wap_url
                        if article.get('docid'):
                             url = f"https://3g.163.com/news/article/{article['docid']}.html"
                        else:
                            continue
                        
                    # 优先使用 HTTPS
                    if url.startswith('http://'):
                        url = url.replace('http://', 'https://')
                        
                    if self._is_duplicate(url):
                        self.stats["duplicate"] += 1
                        continue
                        
                    new_urls_count += 1
                    tasks.append(self._process_article(session, url, article))
                
                if tasks:
                    await asyncio.gather(*tasks)
                    duplicate_count = 0 # 只要有新任务，就重置重复计数
                else:
                    # 如果一页全是重复的，可能已经爬到底了，或者只是这页重复
                    duplicate_count += 1
                    if duplicate_count > 50: # 连续 50 页 (约1000条) 重复才停止，以便跨越旧数据
                        self.logger.info(f"频道 {channel_name} 连续 {duplicate_count} 页重复，停止爬取")
                        break
                
                offset += limit
                await asyncio.sleep(random.uniform(0.5, 1.0))
                
            except Exception as e:
                self.logger.error(f"频道 {channel_name} 爬取异常: {e}")
                fetch_error_count += 1
                await asyncio.sleep(2)
                if fetch_error_count > 10: break

    async def _process_article(self, session: aiohttp.ClientSession, url: str, api_data: dict):
        """处理单篇文章"""
        if self.stop_event.is_set():
            return

        async with self.semaphore:
            try:
                # 再次检查去重 (防止并发时的竞态条件)
                if self._is_duplicate(url):
                    self.stats["duplicate"] += 1
                    return

                html = await self._fetch(session, url)
                if not html:
                    self.stats["failed"] += 1
                    return

                item = self._parse_article(html, url, api_data)
                if item and self._save_article(item):
                    self.stats["success"] += 1
                    self.stats["total"] += 1
                    self.crawled_urls.add(url)
                    if self.stats["success"] % 100 == 0:
                        self.logger.info(f"进度: {self.stats['success']}/{self.target_count} (成功入库)")
                else:
                    self.stats["failed"] += 1

            except Exception as e:
                self.logger.error(f"处理文章失败 {url}: {e}")
                self.stats["failed"] += 1

    def _parse_article(self, html: str, url: str, api_data: dict) -> Optional[DomesticNewsItem]:
        """解析 HTML 提取文章内容"""
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # 1. 标题 (优先使用 API 数据，其次解析 HTML)
            title = api_data.get('title')
            if not title:
                title_node = soup.select_one('h1, .title, #title')
                if title_node:
                    title = title_node.get_text(strip=True)
            
            if not title:
                return None
                
            # 2. 发布时间
            publish_date = api_data.get('ptime') # API 提供的发布时间通常很准
            if not publish_date:
                # 尝试从 HTML 提取
                meta_time = soup.select_one('meta[property="article:published_time"], meta[name="publishdate"]')
                if meta_time:
                    publish_date = meta_time.get('content')
            
            # 3. 正文
            content = ""
            # 综合使用多种选择器
            selectors = [
                '#endText', '.post_text', '.article-content', '.news-content', 
                '.post-body', '.content-body', '#content', 'article'
            ]
            
            for selector in selectors:
                node = soup.select_one(selector)
                if node:
                    # 清理干扰元素
                    for tag in node(['script', 'style', 'iframe', 'div.share', 'div.ep-source']):
                        tag.decompose()
                    content = node.get_text(separator='\n', strip=True)
                    if len(content) > 50: # 只有内容足够长才认为是有效正文
                        break
            
            if not content:
                return None
                
            # 4. 作者/来源
            author = api_data.get('source')
            if not author:
                author_node = soup.select_one('.ep-editor, .author, .source')
                if author_node:
                    author = author_node.get_text(strip=True)

            # 5. 关键词
            keywords = []
            meta_kw = soup.select_one('meta[name="keywords"]')
            if meta_kw:
                kw_str = meta_kw.get('content', '')
                keywords = [k.strip() for k in kw_str.split(',') if k.strip()]

            return DomesticNewsItem(
                source_name=self.source_name,
                url=url,
                title=title,
                author=author or "",
                content=content,
                publish_date=self.try_parse_date(publish_date),
                keywords=','.join(keywords),
                description=content[:200]
            )

        except Exception as e:
            self.logger.debug(f"解析失败 {url}: {e}")
            return None

    def _save_article(self, item: DomesticNewsItem) -> bool:
        """保存文章到数据库"""
        try:
            # 保存到 raw_articles
            if self._source_id:
                raw_item = RawArticleItem.from_domestic(item, self.source_code)
                return self.db.insert_raw_article(raw_item, self._source_id)
            return False
        except Exception as e:
            self.logger.error(f"入库失败: {e}")
            return False

    async def _fetch(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """异步获取 URL 内容"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }
        
        for _ in range(3): # 重试 3 次
            try:
                async with session.get(url, headers=headers, timeout=10, ssl=False) as response:
                    if response.status == 200:
                        try:
                            return await response.text(encoding='utf-8', errors='ignore')
                        except:
                            raw = await response.read()
                            return raw.decode('gbk', errors='ignore') # 网易部分老页面是 GBK
                    elif response.status == 404:
                        return None
            except Exception:
                await asyncio.sleep(1)
        return None

    def _clean_jsonp(self, content: str) -> Optional[str]:
        """清理 JSONP 包装，提取 JSON"""
        try:
            # 匹配 artiList({...}) 或 callback({...})
            match = re.search(r'^\s*(?:artiList|callback)\s*\((.*)\)\s*$', content, re.DOTALL)
            if match:
                return match.group(1)
            
            # 如果本身就是 JSON
            if content.strip().startswith('{') and content.strip().endswith('}'):
                return content
                
            return None
        except:
            return None

    def _is_duplicate(self, url: str) -> bool:
        """检查 URL 是否已存在"""
        if url in self.crawled_urls:
            return True
        if self.db.url_exists(url):
            return True
        return False
