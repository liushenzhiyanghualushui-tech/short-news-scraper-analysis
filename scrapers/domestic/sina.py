"""新浪新闻爬虫 - 适配 short_new 的 MySQL"""

import re
import logging
import json
import time
import concurrent.futures
from urllib.parse import urljoin
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup

from ..base import BaseScraper
from ..models import DomesticNewsItem


class SinaScraper(BaseScraper):
    """新浪新闻爬虫"""

    def __init__(self, config: dict, db_handler):
        super().__init__(config, db_handler)
        self.source_name = "新浪新闻"
        self.source_code = "sina"
        self.seed_url = "https://news.sina.com.cn/"
        self.keywords = config.get("keywords", [])
        
        # 默认配置
        self.concurrency = 5
        self.max_items = 1000

        # 尝试从 domestic_news.sources 中读取特定配置 (优先级高)
        domestic_conf = config.get("domestic_news", {})
        if isinstance(domestic_conf, dict):
            sources = domestic_conf.get("sources", [])
            for s in sources:
                if s.get("name") == "sina":
                    self.max_items = s.get("max_items", self.max_items)
                    self.concurrency = s.get("concurrency", self.concurrency)
                    break
        
        # 兼容旧逻辑：如果没在 sources 里显式配置，且有全局 scraper 配置，则回退读取
        # 注意：这里如果 sources 没配置，会用 1000；如果 scraper 配置了，会覆盖
        scraper_conf = config.get("scraper", {})
        if isinstance(scraper_conf, dict):
            global_max = scraper_conf.get("max_items")
            # 只有当特定配置未修改默认值 1000 时，才考虑全局配置，
            # 或者简单的逻辑：如果特定配置没找到（还是初始值），尝试全局配置
            # 这里简化处理：如果 max_items 还是 1000 (默认)，且全局有配置，则使用全局
            if self.max_items == 1000 and global_max:
                self.max_items = global_max
        else:
            if self.max_items == 1000 and config.get("max_items"):
                self.max_items = config.get("max_items")
        
        # 文章URL正则 - 新浪新闻文章URL格式: /频道/日期/doc-xxxx.shtml
        # 例如: /c/xl/2026-01-26/doc-inhirukw6267054.shtml
        #       /w/2026-01-27/doc-inhismhi7882042.shtml
        self.url_pattern = re.compile(r'/[a-z]+/\d{4}\-\d{2}\-\d{2}/doc\-[a-z0-9\-]+\.shtml', re.IGNORECASE)

    def get_source_config(self) -> Dict:
        return {
            "name": self.source_name,
            "code": self.source_code,
            "type": "domestic",
            "seed_url": self.seed_url
        }

    def run(self) -> int:
        """执行爬取"""
        self.logger.info(f"开始爬取 {self.source_name}，目标: {self.max_items}条，并发: {self.concurrency}")

        try:
            article_urls = self.fetch_article_list()

            count = 0
            # 使用线程池并发抓取
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.concurrency) as executor:
                # 提交所有任务
                future_to_url = {executor.submit(self._process_url, url): url for url in article_urls}
                
                for future in concurrent.futures.as_completed(future_to_url):
                    url = future_to_url[future]
                    try:
                        success = future.result()
                        if success:
                            count += 1
                    except Exception as exc:
                        self.logger.error(f"{url} generated an exception: {exc}")

            self.logger.info(f"{self.source_name} 爬取完成，共保存 {count} 条")
            return count
        except Exception as e:
            self.logger.error(f"{self.source_name} 爬取出错: {e}")
            return 0
    
    def _process_url(self, url: str) -> bool:
        """处理单个 URL：抓取 -> 保存"""
        try:
            article = self.fetch_article(url)
            if article and self.save_article(article):
                # 并发模式下，延迟可以减小或移除
                # 这里保留极短延迟，避免瞬间请求过于密集
                time.sleep(0.1) 
                return True
            return False
        except Exception as e:
            self.logger.error(f"处理 URL 失败 {url}: {e}")
            return False

    def fetch_article_list(self) -> List[str]:
        """获取文章列表页 - 使用新浪滚动新闻 API"""
        urls = []
        api_url = "https://feed.mix.sina.com.cn/api/roll/get"
        page = 1
        page_size = 50
        
        self.logger.info(f"开始从 API 获取文章列表，目标: {self.max_items} 条")

        try:
            while len(urls) < self.max_items:
                params = {
                    "pageid": 153,
                    "lid": 2509,
                    "k": "",
                    "num": page_size,
                    "page": page
                }
                
                self.logger.debug(f"正在获取第 {page} 页...")
                response = requests.get(
                    api_url,
                    params=params,
                    headers=self.get_headers(),
                    timeout=self.timeout
                )
                
                if response.status_code != 200:
                    self.logger.warning(f"API 请求失败: {response.status_code}")
                    break
                    
                try:
                    data = response.json()
                except json.JSONDecodeError:
                    self.logger.warning("API 返回非 JSON 格式")
                    break

                if not data.get("result") or not data["result"].get("data"):
                    self.logger.info("没有更多数据了")
                    break
                    
                items = data["result"]["data"]
                if not items:
                    break
                    
                new_count = 0
                for item in items:
                    url = item.get("url")
                    if url and self.url_pattern.search(url):
                        if url not in urls:
                            urls.append(url)
                            new_count += 1
                            
                self.logger.debug(f"第 {page} 页获取到 {new_count} 个新 URL，当前总数: {len(urls)}")
                
                page += 1
                time.sleep(1) # 礼貌延迟

            # 限制数量
            urls = urls[:self.max_items]
            self.logger.info(f"共找到 {len(urls)} 篇文章URL")

        except Exception as e:
            self.logger.error(f"获取文章列表失败: {e}")

        return urls

    def fetch_article(self, url: str) -> Optional[Dict]:
        """获取单篇文章详情"""
        try:
            response = requests.get(
                url,
                headers=self.get_headers(),
                timeout=self.timeout
            )
            soup = BeautifulSoup(response.content, 'lxml')

            # 提取标题
            title = ""
            if soup.title:
                title = soup.title.string.strip()
            else:
                h1 = soup.select_one('h1')
                if h1:
                    title = h1.get_text(strip=True)

            # 提取作者
            author = ""
            author_node = soup.select_one('.show_author')
            if author_node:
                author = author_node.get_text(strip=True)

            # 提取正文
            content = ""
            content_node = soup.select_one('.article') or soup.select_one('#article')
            if content_node:
                # 清理脚本和样式
                for script in content_node(['script', 'style', 'nav', 'footer']):
                    script.decompose()
                content = self.clean_text(content_node.get_text(separator='\n'))

            # 提取发布时间
            publish_date = None
            date_node = soup.select_one('meta[property="article:published_time"]')
            if date_node:
                publish_date = date_node.get("content")

            # 提取关键词
            keywords = []
            keywords_node = soup.select_one('meta[name="keywords"]')
            if keywords_node:
                keywords_str = keywords_node.get("content", "")
                keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]

            # 提取描述
            description = ""
            desc_node = soup.select_one('meta[name="description"]')
            if desc_node:
                description = desc_node.get("content", "")

            return {
                'url': url,
                'title': title,
                'author': author,
                'content': content,
                'publish_date': self.try_parse_date(publish_date) if publish_date else None,
                'keywords': keywords,
                'description': description
            }

        except Exception as e:
            self.logger.error(f"获取文章详情失败 {url}: {e}")
            return None

    def save_article(self, article: Dict) -> bool:
        """保存文章到 MySQL 数据库"""
        # 检查 URL 是否已存在
        if self.url_exists(article.get('url', '')):
            return False

        from ..models import RawArticleItem

        item = DomesticNewsItem(
            source_name=self.source_name,
            source_code=self.source_code,
            url=article.get('url', ''),
            title=article.get('title', ''),
            author=article.get('author', ''),
            content=article.get('content', ''),
            publish_date=article.get('publish_date'),
            keywords=article.get('keywords', []),
            description=article.get('description', '')
        )

        raw_item = RawArticleItem.from_domestic(item, self.source_code)
        return self.db.insert_raw_article(raw_item, self._get_source_id())

    def _get_source_id(self) -> int:
        """获取来源ID"""
        source = self.db.get_source_by_code(self.source_code)
        return source["id"] if source else 0
