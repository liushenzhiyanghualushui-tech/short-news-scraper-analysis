"""参考消息网爬虫 - 适配 short_new 的 MySQL"""

import json
import logging
import random
import time
import os
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any, Set
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import urllib3
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from ..base import BaseScraper
from ..models import DomesticNewsItem, RawArticleItem
from .uc_proxy import UCProxyPool  # 复用代理池逻辑

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class CankaoxiaoxiRequestThrottler:
    """请求频率控制器"""
    def __init__(self, min_interval: float = 0.5, enable_jitter: bool = True, jitter_range: tuple = (0.5, 1.5)):
        self.min_interval = min_interval
        self.enable_jitter = enable_jitter
        self.jitter_range = jitter_range
        self.last_request_time = {}

    def wait(self, domain: str = None):
        domain = domain or 'default'
        current_time = time.time()
        last_time = self.last_request_time.get(domain, 0)
        interval = self.min_interval
        if self.enable_jitter:
            interval *= random.uniform(*self.jitter_range)
        elapsed = current_time - last_time
        if elapsed < interval:
            time.sleep(interval - elapsed)
        self.last_request_time[domain] = time.time()

PLATFORM_USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]

class CankaoxiaoxiScraper(BaseScraper):
    """参考消息网爬虫 (API版)"""

    def __init__(self, config: dict, db_handler):
        super().__init__(config, db_handler)
        self.source_name = "参考消息"
        self.source_code = "cankaoxiaoxi"
        self.seed_url = "https://www.cankaoxiaoxi.com/"

        self.user_agents = config.get('user_agents') or PLATFORM_USER_AGENTS
        
        self.proxy_pool = UCProxyPool(
            proxy_apis=config.get('proxy_apis', []),
            proxies=config.get('proxies', []),
            enable_rotation=config.get('enable_proxy_rotation', False),
            refresh_interval=config.get('proxy_refresh_interval', 300)
        )

        self.throttler = CankaoxiaoxiRequestThrottler(
            min_interval=config.get('min_request_interval', 0.2),
            enable_jitter=config.get('enable_random_jitter', True)
        )

        self.session = requests.Session()
        # API URL configuration
        self.site_config_url = "https://www.cankaoxiaoxi.com/json/config/site.sitejson"
        
        # Selenium Configuration
        self.driver_path = os.path.abspath("msedgedriver.exe")
        self.max_pages = 200
        self.target_count = 3000
        self.concurrency = 20 # Default
        
        cankao_conf = config.get("cankaoxiaoxi", {}) if isinstance(config.get("cankaoxiaoxi"), dict) else {}
        if cankao_conf.get("driver_path"):
            self.driver_path = str(cankao_conf.get("driver_path"))
        if cankao_conf.get("target_count"):
            self.target_count = int(cankao_conf.get("target_count"))
        if cankao_conf.get("concurrency"):
            self.concurrency = int(cankao_conf.get("concurrency"))

        # Track processed URLs to avoid duplication in current run
        self.processed_urls = set()
        self.stop_event = asyncio.Event() # For compatibility with async logic if needed

    def get_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "*/*",
            "Referer": "https://www.cankaoxiaoxi.com/",
        }

    def _get_proxy(self) -> Optional[str]:
        return self.proxy_pool.get_proxy()

    def _make_request(self, url: str, is_json: bool = False) -> Optional[requests.Response]:
        for i in range(3):
            proxy = self._get_proxy()
            try:
                # Randomize User-Agent for every request attempt
                headers = self.get_headers()
                
                kwargs = {
                    'headers': headers,
                    'timeout': 15,
                    'verify': False  # Reference News API uses invalid certs often
                }
                if proxy:
                    kwargs['proxies'] = {'http': proxy, 'https': proxy}
                
                response = requests.get(url, **kwargs)
                if response.status_code == 200:
                    if is_json:
                        # Validate JSON content
                        try:
                            response.json()
                        except ValueError:
                            continue
                    else:
                        response.encoding = 'utf-8'
                    return response
            except Exception as e:
                # Only log error if it's not a common proxy/network issue to reduce noise in high concurrency
                if i == 2: # Log on last retry
                    self.logger.warning(f"请求失败 {url}: {e}")
                time.sleep(random.uniform(0.5, 1.5)) # Random backoff
        return None

    def run(self) -> int:
        self.logger.info(f"开始爬取 {self.source_name} (混合模式: API + Web)")
        total_count = 0
        
        try:
            # 1. API Crawl (Latest items)
            self.logger.info("阶段1: API 采集 (最新数据)...")
            api_urls = self._run_api_crawl()
            total_count += self._download_batch(api_urls, max_workers=self.concurrency)
            
            # 2. Web Crawl (Historical items via Selenium)
            if total_count < self.target_count:
                self.logger.info(f"阶段2: Web 采集 (历史回溯)... 当前: {total_count}, 目标: {self.target_count}")
                web_urls = self._run_web_crawl(existing_count=total_count)
                total_count += self._download_batch(web_urls, max_workers=self.concurrency)

            self.logger.info(f"{self.source_name} 爬取完成，共保存 {total_count} 条")
            return total_count

        except Exception as e:
            self.logger.error(f"爬取出错: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return total_count

    def _run_api_crawl(self) -> List[str]:
        """Original API crawling logic"""
        all_article_urls = []
        try:
            # 1. Fetch Site Config
            self.logger.info("获取站点配置...")
            resp = self._make_request(self.site_config_url, is_json=True)
            if not resp:
                self.logger.error("无法获取站点配置")
                return []
            
            site_config = resp.json()
            channels = site_config.get('channelsJson', [])
            self.logger.info(f"获取到 {len(channels)} 个一级频道")
            
            # 2. Process Channels
            for channel in channels:
                json_path = channel.get('jsonPath')
                if json_path:
                    urls = self.process_channel_config(json_path)
                    all_article_urls.extend(urls)
            
            # 3. Deduplicate
            unique_urls = list(set(all_article_urls))
            new_urls = [url for url in unique_urls if not self.url_exists(url) and url not in self.processed_urls]
            self.logger.info(f"API 模式发现 {len(unique_urls)} 篇文章，其中 {len(new_urls)} 篇为新文章")
            return new_urls
        except Exception as e:
            self.logger.error(f"API 采集失败: {e}")
            return []

    def _run_web_crawl(self, existing_count: int) -> List[str]:
        """Selenium based crawling for historical data"""
        found_urls = []
        
        # Define Web Channels
        web_channels = [
            {"name": "首页", "url": "https://www.cankaoxiaoxi.com/"},
            {"name": "中国", "url": "https://china.cankaoxiaoxi.com/"},
            {"name": "国际", "url": "https://world.cankaoxiaoxi.com/"},
            {"name": "军事", "url": "https://mil.cankaoxiaoxi.com/"},
            {"name": "台海", "url": "https://tw.cankaoxiaoxi.com/"},
            {"name": "锐评", "url": "https://comment.cankaoxiaoxi.com/"},
            {"name": "视觉", "url": "https://photo.cankaoxiaoxi.com/"},
        ]
        
        if not os.path.exists(self.driver_path):
            self.logger.error(f"EdgeDriver 未找到: {self.driver_path}，跳过 Web 采集")
            return []

        options = EdgeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument(f"user-agent={random.choice(self.user_agents)}")
        
        service = EdgeService(executable_path=self.driver_path)
        driver = None
        
        try:
            driver = webdriver.Edge(service=service, options=options)
            
            for channel in web_channels:
                if existing_count + len(found_urls) >= self.target_count:
                    break
                    
                self.logger.info(f"正在抓取 Web 频道: {channel['name']} ({channel['url']})")
                channel_urls = self._crawl_dynamic_channel(driver, channel['url'])
                
                new_urls = [u for u in channel_urls if not self.url_exists(u) and u not in self.processed_urls and u not in found_urls]
                found_urls.extend(new_urls)
                self.logger.info(f"频道 {channel['name']} 新增 {len(new_urls)} 条链接")
                
        except Exception as e:
            self.logger.error(f"Web 采集异常: {e}")
        finally:
            if driver:
                driver.quit()
                
        return found_urls

    def _crawl_dynamic_channel(self, driver, url: str) -> List[str]:
        """Scroll and extract URLs from SPA"""
        extracted_urls = set()
        try:
            driver.get(url)
            # Wait for any content container to load
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "a"))
                )
            except:
                pass
            
            time.sleep(3) # Wait for JS to render
            
            last_link_count = 0
            no_change_count = 0
            
            # Scroll loop
            for _ in range(self.max_pages):
                # Extract links
                links = driver.find_elements(By.TAG_NAME, "a")
                current_links = []
                for link in links:
                    try:
                        href = link.get_attribute("href")
                        if href and self._is_valid_url(href):
                            extracted_urls.add(href)
                            current_links.append(href)
                    except:
                        continue
                
                if len(extracted_urls) >= 3500:
                    break
                
                # Check if we found new links
                if len(current_links) <= last_link_count:
                    no_change_count += 1
                else:
                    no_change_count = 0
                    last_link_count = len(current_links)
                
                if no_change_count >= 5: # Stop if no new links found after 5 scrolls
                    break
                
                # Scroll down - Try both body and window
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                # Try scrolling potential list containers
                driver.execute_script("""
                    var containers = document.querySelectorAll('div[class*="list"], div[class*="content"], main');
                    containers.forEach(function(c) {
                        if (c.scrollHeight > c.clientHeight) {
                            c.scrollTop = c.scrollHeight;
                        }
                    });
                """)
                time.sleep(2)
                    
        except Exception as e:
            self.logger.warning(f"动态抓取中断 {url}: {e}")
            
        return list(extracted_urls)


    def process_channel_config(self, config_url: str, depth: int = 0) -> List[str]:
        """递归处理频道配置，发现文章列表和子频道"""
        if depth > 5:  # 防止无限递归
            return []
            
        found_urls = []
        try:
            resp = self._make_request(config_url, is_json=True)
            if not resp:
                return []
            
            data = resp.json()
            
            # 1. 如果当前 JSON 本身就是一个列表容器
            # 尝试直接从中提取文章链接
            items = data.get('list', [])
            for item in items:
                url = item.get('url')
                if not url and 'data' in item:
                    url = item['data'].get('url')
                
                if url and self._is_valid_url(url):
                    found_urls.append(url)
            
            # 2. 处理嵌套的子频道
            # 在参考消息的结构中，'list' 既可能包含文章，也可能包含子频道定义
            for sub in items:
                sub_json_path = sub.get('jsonPath')
                if sub_json_path and sub_json_path != config_url:
                    # 如果子项有 jsonPath，且不是当前 URL，则递归探索
                    # 优先尝试作为频道配置处理
                    sub_urls = self.process_channel_config(sub_json_path, depth + 1)
                    found_urls.extend(sub_urls)
            
            # 3. 显式处理顶层 jsonPath (如果存在)
            top_json_path = data.get('jsonPath')
            if top_json_path and top_json_path != config_url:
                found_urls.extend(self.process_channel_config(top_json_path, depth + 1))
                
        except Exception as e:
            self.logger.warning(f"处理频道配置失败 {config_url}: {e}")
            
        return list(set(found_urls))

    def fetch_news_list(self, list_url: str) -> List[str]:
        """Fetch a news list JSON and extract article URLs"""
        urls = []
        try:
            resp = self._make_request(list_url, is_json=True)
            if not resp:
                return []
            
            data = resp.json()
            items = data.get('list', [])
            
            for item in items:
                # Structure might be item['url'] or item['data']['url']
                url = item.get('url')
                if not url and 'data' in item:
                    url = item['data'].get('url')
                
                if url and self._is_valid_url(url):
                    urls.append(url)
                    
        except Exception as e:
            self.logger.warning(f"获取新闻列表失败 {list_url}: {e}")
            
        return urls

    def _is_valid_url(self, url: str) -> bool:
        return 'cankaoxiaoxi.com' in url or 'ckxx.net' in url

    def _download_batch(self, urls: List[str], max_workers: int) -> int:
        count = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(self.fetch_article_and_save, url): url for url in urls}
            for future in as_completed(future_to_url):
                try:
                    if future.result():
                        count += 1
                except Exception:
                    pass
        return count

    def fetch_article_and_save(self, url: str) -> bool:
        try:
            self.throttler.wait()
            article = self.fetch_article(url)
            if article:
                return self.save_article(article)
            return False
        except Exception as e:
            self.logger.error(f"抓取任务失败 {url}: {e}")
            return False

    def fetch_article(self, url: str) -> Optional[Dict]:
        try:
            response = self._make_request(url)
            if not response:
                self.logger.warning(f"无法获取文章页面: {url}")
                return None

            soup = BeautifulSoup(response.content, 'lxml')

            # 提取标题
            title = ""
            # 参考消息标题常见选择器
            title_node = soup.select_one('h1, .article-title, .biaoti, .title, #title')
            if title_node:
                title = title_node.get_text(strip=True)
            
            # 兜底：尝试从 meta 标签提取
            if not title:
                meta_title = soup.select_one('meta[property="og:title"], meta[name="title"]')
                if meta_title:
                    title = meta_title.get('content', '').strip()
            
            if not title:
                self.logger.warning(f"无法解析标题: {url}")
                return None

            # 提取正文
            content = ""
            # 参考消息网常见的正文容器
            content_node = soup.select_one('.article-content, #articleContent, .article-text, .inner, .content, #content')
            if content_node:
                for tag in content_node(['script', 'style', 'iframe', 'div.qrcode', '.video-box', '.ad', '.footer']):
                    tag.decompose()
                content = content_node.get_text(separator='\n', strip=True)

            if not content:
                # 尝试备用选择器
                content_node = soup.select_one('.text, .article-body, #article_body')
                if content_node:
                    content = content_node.get_text(separator='\n', strip=True)

            if not content:
                self.logger.warning(f"无法解析正文内容: {url}")
                # 即使没正文，如果标题在也可以考虑保存，但通常爬虫要求有内容
                # return None 

            # 提取发布时间
            publish_date = None
            date_node = soup.select_one('.time, .article-time, #pubtime_baidu, .info span, meta[property="article:published_time"], .date')
            if date_node:
                date_str = date_node.get('content') if date_node.name == 'meta' else date_node.get_text(strip=True)
                publish_date = self.try_parse_date(date_str)

            # 提取作者/来源
            author = "参考消息"
            source_node = soup.select_one('.source, #source_baidu, .info .source, meta[name="source"]')
            if source_node:
                author = source_node.get('content') if source_node.name == 'meta' else source_node.get_text(strip=True).replace("来源：", "")

            return {
                'url': url,
                'title': title,
                'author': author,
                'content': content,
                'publish_date': publish_date,
                'keywords': [],
                'description': content[:200] if content else ""
            }

        except Exception as e:
            self.logger.error(f"解析文章详情失败 {url}: {e}")
            return None

    def save_article(self, article: Dict) -> bool:
        url = article.get('url', '')
        if self.url_exists(url):
            # self.logger.debug(f"文章已存在: {url}")
            return False

        try:
            item = DomesticNewsItem(
                source_name=self.source_name,
                source_code=self.source_code,
                url=url,
                title=article.get('title', ''),
                author=article.get('author', ''),
                content=article.get('content', ''),
                publish_date=article.get('publish_date'),
                keywords=','.join(article.get('keywords', [])),
                description=article.get('description', '')
            )

            raw_item = RawArticleItem.from_domestic(item, self.source_code)
            success = self.db.insert_raw_article(raw_item, self._get_source_id())
            if not success:
                self.logger.warning(f"保存文章到数据库失败: {url}")
            return success
        except Exception as e:
            self.logger.error(f"保存文章异常 {url}: {e}")
            return False

    def _get_source_id(self) -> int:
        source = self.db.get_source_by_code(self.source_code)
        return source["id"] if source else 0

    def get_source_config(self) -> Dict[str, Any]:
        """获取源配置"""
        return {
            "source_code": self.source_code,
            "source_name": self.source_name,
            "source_type": "domestic",
            "seed_url": self.seed_url,
            "enabled": True
        }
