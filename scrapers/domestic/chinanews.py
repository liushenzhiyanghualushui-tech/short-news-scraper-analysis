"""中新网新闻爬虫 - 适配 short_new 的 MySQL"""

import re
import logging
import random
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin
from typing import List, Dict, Optional
import concurrent.futures
from .uc_proxy import UCProxyPool

import requests
from bs4 import BeautifulSoup

from ..base import BaseScraper
from ..models import DomesticNewsItem, RawArticleItem


class ChinaNewsScraper(BaseScraper):
    """中新网新闻爬虫"""

    def __init__(self, config: dict, db_handler):
        super().__init__(config, db_handler)
        self.source_name = "中新网"
        self.source_code = "chinanews"
        self.seed_url = "https://www.chinanews.com.cn/"
        self.keywords = config.get("keywords", [])
        # 新闻URL正则匹配: /2024/01-28/1234567.shtml 或 /12345678.shtml
        self.url_pattern = re.compile(r'/(\d{4})/(\d{2})-(\d{2})/(\d+).shtml')
        
        # 代理配置
        self.proxy_pool = None
        if config.get("enable_proxy_rotation", False):
            self.proxy_pool = UCProxyPool(
                proxy_apis=config.get("proxy_apis", []),
                proxies=config.get("proxies", []),
                enable_rotation=True,
                refresh_interval=config.get("proxy_refresh_interval", 300)
            )

    def get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.8,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Referer": "https://www.chinanews.com.cn/"
        }

    def get_source_config(self) -> Dict:
        return {
            "name": self.source_name,
            "code": self.source_code,
            "type": "domestic",
            "seed_url": self.seed_url
        }

    def run(self) -> int:
        """执行爬取"""
        self.logger.info(f"开始爬取 {self.source_name}")

        try:
            self.logger.info(f"正在获取文章列表: {self.seed_url}")
            article_urls = self.fetch_article_list()
            self.logger.info(f"获取到 {len(article_urls)} 篇文章URL")

            count = 0
            # 使用线程池并发抓取
            max_workers = 10  # 设置并发线程数
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任务
                future_to_url = {executor.submit(self.process_single_article, url): url for url in article_urls}
                
                # 获取结果
                for i, future in enumerate(concurrent.futures.as_completed(future_to_url)):
                    url = future_to_url[future]
                    try:
                        if future.result():
                            count += 1
                        if (i + 1) % 50 == 0:
                            self.logger.info(f"进度: {i + 1}/{len(article_urls)}，成功: {count}")
                    except Exception as exc:
                        self.logger.error(f'{url} generated an exception: {exc}')

            self.logger.info(f"{self.source_name} 爬取完成，共保存 {count} 条")
            return count
        except Exception as e:
            self.logger.error(f"{self.source_name} 爬取出错: {e}")
            import traceback
            traceback.print_exc()
            return 0

    def process_single_article(self, url: str) -> bool:
        """处理单篇文章（用于线程池）"""
        try:
            # 随机延时，避免并发过高触发反爬
            time.sleep(random.uniform(0.1, 0.5))
            
            article = self.fetch_article(url)
            if article and self.save_article(article):
                return True
        except Exception as e:
            self.logger.debug(f"处理文章失败 {url}: {e}")
        return False

    def _get_request_kwargs(self) -> dict:
        """获取请求参数（包含代理配置）"""
        kwargs = {
            "headers": self.get_headers(),
            "timeout": self.timeout
        }
        
        if self.proxy_pool:
            proxy = self.proxy_pool.get_proxy()
            if proxy:
                kwargs["proxies"] = {
                    "http": proxy,
                    "https": proxy
                }
        
        return kwargs

    def fetch_article_list(self) -> List[str]:
        """获取文章列表页（支持多频道滚动抓取）"""
        urls = []
        target_count = 3000
        
        # 定义要抓取的频道配置
        # scroll-news: 滚动新闻 (news{page}.html)
        # 2026-02-08: 其他频道 (gn, gj 等) 的 more/{page}.html 翻页已失效 (404)，
        # 且 scroll-news 包含了所有频道的最新新闻，故仅保留 scroll-news。
        channels = [
            {'code': 'scroll-news', 'fmt': 'https://www.chinanews.com.cn/scroll-news/news{page}.html'},
        ]
        
        try:
            self.logger.info(f"开始抓取多频道新闻列表，目标数量: {target_count}")
            
            for channel in channels:
                if len(urls) >= target_count:
                    break
                    
                channel_code = channel['code']
                url_fmt = channel['fmt']
                max_pages = 20  # 每个频道尝试抓取前20页
                
                self.logger.info(f"正在抓取频道: {channel_code}")
                
                for page in range(1, max_pages + 1):
                    if len(urls) >= target_count:
                        break
                    
                    # 构造页面 URL
                    list_url = url_fmt.format(page=page)
                    
                    self.logger.info(f"[{channel_code}] 请求第 {page} 页: {list_url}")
                    
                    try:
                        response = requests.get(list_url, **self._get_request_kwargs())
                        
                        if response.status_code != 200:
                            if response.status_code == 404:
                                self.logger.info(f"[{channel_code}] 页面不存在 (404)，停止该频道翻页")
                                break
                            self.logger.error(f"请求失败: {list_url} 状态码: {response.status_code}")
                            continue
                        
                        soup = BeautifulSoup(response.content, 'lxml')

                        # 提取所有链接
                        new_count = 0
                        for link in soup.find_all('a', href=True):
                            href = link.get('href', '')
                            if self.url_pattern.search(href):
                                full_url = urljoin(list_url, href)
                                if full_url not in urls:
                                    urls.append(full_url)
                                    new_count += 1
                        
                        self.logger.debug(f"[{channel_code}] 第 {page} 页新增 {new_count} 条，当前总数: {len(urls)}")
                        
                        # 如果这一页没有找到任何有效链接，可能已经到底了或者页面结构变了
                        if new_count == 0:
                            self.logger.warning(f"[{channel_code}] 第 {page} 页未找到有效链接，可能已达末尾")
                            # break 

                        # 礼貌性延时
                        time.sleep(random.uniform(0.5, 1.5))

                    except requests.Timeout:
                        self.logger.error(f"请求超时: {list_url}")
                    except requests.ConnectionError as e:
                        self.logger.error(f"连接失败: {list_url} - {e}")
                    except Exception as e:
                        self.logger.error(f"解析页面失败 {list_url}: {e}")

            # 限制数量
            urls = urls[:target_count]
            
            # 如果数量还不够，尝试按日期遍历历史数据 (Format: scroll-news/YYYY/MMDD/news.shtml)
            if len(urls) < target_count:
                self.logger.info(f"当前获取 {len(urls)} 条，未达到目标 {target_count}，开始按日期遍历历史归档...")
                
                # 从昨天开始向前推
                current_date = datetime.now() - timedelta(days=1)
                max_days_back = 60  # 最多回溯60天
                days_checked = 0
                
                while len(urls) < target_count and days_checked < max_days_back:
                    date_str_url = current_date.strftime("%Y/%m%d")
                    list_url = f"https://www.chinanews.com.cn/scroll-news/{date_str_url}/news.shtml"
                    
                    self.logger.info(f"[历史归档] 请求日期: {current_date.strftime('%Y-%m-%d')} ({list_url})")
                    
                    try:
                        response = requests.get(list_url, **self._get_request_kwargs())
                        
                        if response.status_code == 200:
                            soup = BeautifulSoup(response.content, 'lxml')
                            new_count = 0
                            
                            for link in soup.find_all('a', href=True):
                                href = link.get('href', '')
                                if self.url_pattern.search(href):
                                    full_url = urljoin(list_url, href)
                                    if full_url not in urls:
                                        urls.append(full_url)
                                        new_count += 1
                                        if len(urls) >= target_count:
                                            break
                            
                            self.logger.info(f"[历史归档] {current_date.strftime('%Y-%m-%d')} 新增 {new_count} 条，当前总数: {len(urls)}")
                            time.sleep(random.uniform(0.5, 1.0))
                            
                        elif response.status_code == 404:
                            self.logger.debug(f"[历史归档] 日期页面不存在: {list_url}")
                        else:
                            self.logger.warning(f"[历史归档] 请求失败: {list_url} code={response.status_code}")
                            
                    except Exception as e:
                        self.logger.error(f"[历史归档] 处理失败 {list_url}: {e}")
                    
                    # 前一天
                    current_date -= timedelta(days=1)
                    days_checked += 1

            self.logger.info(f"最终获取到 {len(urls)} 篇文章URL")

        except Exception as e:
            self.logger.error(f"获取文章列表失败: {e}")

        return urls

    def fetch_article(self, url: str) -> Optional[Dict]:
        """获取单篇文章详情"""
        try:
            response = requests.get(url, **self._get_request_kwargs())
            
            if response.status_code != 200:
                self.logger.error(f"请求失败: {url} 状态码: {response.status_code}")
                return None
                
            soup = BeautifulSoup(response.content, 'lxml')

            # 提取标题
            title = ""
            if soup.title:
                title = soup.title.string.strip()
            else:
                h1 = soup.select_one('h1')
                if h1:
                    title = h1.get_text(strip=True)

            # 验证标题
            if not title or len(title) <= 5:
                self.logger.debug(f"标题为空或过短，跳过: {url}")
                return None

            # 提取作者
            author = ""
            author_node = soup.select_one('#editor_baidu')
            if author_node:
                author = author_node.get_text(strip=True)

            # 提取正文
            content = ""
            content_node = soup.select_one('.left_zw')
            if content_node:
                # 清理脚本和样式
                for script in content_node(['script', 'style', 'nav', 'footer']):
                    script.decompose()
                content = self.clean_text(content_node.get_text(separator='\n'))

            # 提取发布时间
            publish_date = None
            date_node = soup.select_one('#pubtime_baidu')
            if date_node:
                pub_raw = date_node.get_text(strip=True)
                if pub_raw:
                    parsed = self.try_parse_date(pub_raw)
                    if parsed:
                        publish_date = parsed

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
                'publish_date': publish_date,
                'keywords': keywords,
                'description': description
            }

        except requests.Timeout:
            self.logger.error(f"获取文章详情超时: {url}")
        except requests.ConnectionError as e:
            self.logger.error(f"获取文章详情连接失败: {url} - {e}")
        except Exception as e:
            self.logger.error(f"获取文章详情失败 {url}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def save_article(self, article: Dict) -> bool:
        """保存文章到 MySQL 数据库"""
        # 检查 URL 是否已存在
        url = article.get('url', '')
        if self.url_exists(url):
            self.logger.debug(f"URL已存在，跳过: {url[:50]}...")
            return False

        from ..models import RawArticleItem

        item = DomesticNewsItem(
            source_name=self.source_name,
            url=url,
            title=article.get('title', ''),
            author=article.get('author', ''),
            content=article.get('content', ''),
            publish_date=article.get('publish_date'),
            keywords=','.join(article.get('keywords', [])),
            description=article.get('description', '')
        )

        raw_item = RawArticleItem.from_domestic(item, self.source_code)
        return self.db.insert_raw_article(raw_item, self._get_source_id())

    def _get_source_id(self) -> int:
        """获取来源ID"""
        source = self.db.get_source_by_code(self.source_code)
        return source["id"] if source else 0

