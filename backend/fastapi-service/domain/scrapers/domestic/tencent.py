"""腾讯新闻爬虫 - 适配 short_new 的 MySQL"""

import re
import hashlib
import json
import logging
import random
import time
import os
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

from ..base import BaseScraper
from ..models import DomesticNewsItem, RawArticleItem
from .netease_selenium import NeteaseSelenium

class TencentSignature:
    """
    腾讯新闻签名生成器 (保留用于热点新闻 API)
    """

    # 腾讯新闻API基础URL
    API_BASE_URL = "https://r.inews.qq.com"

    # 可用的频道ID列表
    CHANNELS = {
        'news_recommend_hot': 'news_recommend_hot',      # 热点要闻 (API可用)
    }
    
    # 网页版频道映射
    WEB_CHANNELS = {
        'news_ent': 'https://new.qq.com/ch/ent/',           # 娱乐
        'news_sports': 'https://new.qq.com/ch/sports/',     # 体育
        'news_finance': 'https://new.qq.com/ch/finance/',   # 财经
        'news_tech': 'https://new.qq.com/ch/tech/',         # 科技
        'news_game': 'https://new.qq.com/ch/games/',        # 游戏
        'news_auto': 'https://new.qq.com/ch/auto/',         # 汽车
        'news_house': 'https://new.qq.com/ch/house/',       # 房产
        'news_edu': 'https://new.qq.com/ch/edu/',           # 教育
        'news_fashion': 'https://new.qq.com/ch/fashion/',   # 时尚
        'news_cul': 'https://new.qq.com/ch/cul/',           # 文化
        'news_history': 'https://new.qq.com/ch/history/',   # 历史
        'news_mil': 'https://new.qq.com/ch/milite/',        # 军事
        'news_world': 'https://new.qq.com/ch/world/',       # 国际
        'news_rain': 'https://new.qq.com/ch/rain/',         # 较真(辟谣)
    }

    # 签名算法中使用的固定盐值(示例值，需根据实际情况调整)
    SALT = "tencent_news_salt_key"

    @staticmethod
    def _generate_devid() -> str:
        """生成设备ID"""
        return f"Device{random.randint(10000000, 99999999)}"

    @staticmethod
    def _get_timestamp() -> str:
        """获取13位时间戳(毫秒)"""
        return str(int(time.time() * 1000))

    @staticmethod
    def _get_random() -> str:
        """生成随机数"""
        return str(random.randint(100000, 999999))

    @classmethod
    def generate(cls, channel: str = "news_recommend_hot") -> str:
        """
        生成签名参数
        """
        timestamp = cls._get_timestamp()
        random_num = cls._get_random()

        # 构建签名字符串
        sig_string = f"{cls.API_BASE_URL}/getWeiboRankingList"
        sig_string += f"?chlid={channel}"
        sig_string += f"&appver=28_android_6.8.00"
        sig_string += f"&devid="
        sig_string += f"&ts={timestamp}"
        sig_string += f"&rnd={random_num}"
        sig_string += cls.SALT

        # 使用MD5生成签名
        signature = hashlib.md5(sig_string.encode('utf-8')).hexdigest()

        return signature

    @classmethod
    def generate_url(cls, channel: str = "news_recommend_hot") -> str:
        """
        生成完整的API请求URL
        """
        timestamp = cls._get_timestamp()
        random_num = cls._get_random()
        sig = cls.generate(channel)

        params = {
            'chlid': channel,
            'appver': '28_android_6.8.00',
            'devid': '',
            'qn-rid': '',
            'qn-sig': sig,
            'is_h5': '1',
            'ts': timestamp,
            'rnd': random_num
        }

        param_str = '&'.join([f"{k}={v}" for k, v in params.items()])

        return f"{cls.API_BASE_URL}/getWeiboRankingList?{param_str}"


class TencentScraper(BaseScraper):
    """腾讯新闻爬虫"""

    def __init__(self, config: dict, db_handler):
        super().__init__(config, db_handler)
        self.source_name = "腾讯新闻"
        self.source_code = "tencent"
        self.seed_url = "https://news.qq.com/"
        self.selenium_helper = None
        
        # 初始化 Session 和重试机制
        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retries, pool_connections=20, pool_maxsize=20)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        # 初始化 Selenium
        driver_path = os.path.abspath("msedgedriver.exe")
        if os.path.exists(driver_path):
            try:
                self.selenium_helper = NeteaseSelenium(driver_path=driver_path, headless=True)
                if self.selenium_helper.create_driver():
                    self.logger.info("Selenium 驱动初始化成功")
                else:
                    self.logger.error("Selenium 驱动初始化失败")
                    self.selenium_helper = None
            except Exception as e:
                self.logger.error(f"Selenium 初始化异常: {e}")
                self.selenium_helper = None
        else:
            self.logger.warning(f"Selenium 驱动未找到: {driver_path}，部分频道可能无法抓取")

    def __del__(self):
        """析构时关闭浏览器"""
        if self.selenium_helper:
            self.selenium_helper.close()

    def get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://news.qq.com/"
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
        target_count = 3000
        saved_count = 0
        all_urls = set()

        # 1. 获取热点要闻 (使用API)
        try:
            channel_name = "热点要闻"
            channel_id = "news_recommend_hot"
            self.logger.info(f"正在获取频道: {channel_name} (API)")
            urls = self.fetch_ranking_list(channel_id)
            new_urls = 0
            for url in urls:
                if url not in all_urls:
                    all_urls.add(url)
                    new_urls += 1
            self.logger.info(f"频道 {channel_name} 获取到 {len(urls)} 条，新增 {new_urls} 条")
            self.random_delay()
        except Exception as e:
            self.logger.error(f"频道 {channel_name} 获取失败: {e}")

        # 2. 遍历其他频道 (使用 Selenium)
        if self.selenium_helper:
            for channel_code, channel_url in TencentSignature.WEB_CHANNELS.items():
                if len(all_urls) >= target_count * 1.5:
                    break
                
                try:
                    self.logger.info(f"正在获取频道: {channel_code} (Selenium: {channel_url})")
                    # 使用深度滚动 (20次) 以获取更多历史文章
                    urls = self.fetch_urls_by_selenium(channel_url, scroll_count=20)
                    new_urls = 0
                    for url in urls:
                        if url not in all_urls:
                            all_urls.add(url)
                            new_urls += 1
                    self.logger.info(f"频道 {channel_code} 获取到 {len(urls)} 条，新增 {new_urls} 条，当前总URL数: {len(all_urls)}")
                    time.sleep(2) # 频道间稍作休息
                except Exception as e:
                    self.logger.error(f"频道 {channel_code} 获取失败: {e}")

        # 3. 首页补充 (使用 Selenium)
        if len(all_urls) < target_count and self.selenium_helper:
            self.logger.info(f"数量不足 ({len(all_urls)} < {target_count})，尝试从首页抓取补充...")
            try:
                # 首页也增加滚动深度
                homepage_urls = self.fetch_urls_by_selenium(self.seed_url, scroll_count=20)
                new_urls = 0
                for url in homepage_urls:
                    if url not in all_urls:
                        all_urls.add(url)
                        new_urls += 1
                self.logger.info(f"首页抓取获取到 {len(homepage_urls)} 条，新增 {new_urls} 条，当前总URL数: {len(all_urls)}")
            except Exception as e:
                self.logger.error(f"首页抓取失败: {e}")

        # 4. 抓取文章详情
        url_list = list(all_urls)
        self.logger.info(f"准备抓取 {len(url_list)} 篇文章详情，目标保存: {target_count}")

        import concurrent.futures

        # 使用线程池并发抓取
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            # 提交所有任务
            future_to_url = {executor.submit(self.process_single_url, url): url for url in url_list}
            
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    success = future.result()
                    if success:
                        saved_count += 1
                        if saved_count % 10 == 0:
                            self.logger.info(f"进度: 已保存 {saved_count}/{target_count} 篇文章")
                except Exception as e:
                    self.logger.error(f"处理URL异常 {url}: {e}")
                
                if saved_count >= target_count:
                    self.logger.info(f"已达到目标数量 {target_count}，停止抓取")
                    # 取消剩余任务
                    for f in future_to_url:
                        f.cancel()
                    break

        self.logger.info(f"{self.source_name} 爬取完成，共保存 {saved_count} 条")
        
        # 显式关闭 Selenium
        if self.selenium_helper:
            self.selenium_helper.close()
            self.selenium_helper = None
            
        return saved_count

    def process_single_url(self, url: str) -> bool:
        """处理单个URL：检查存在 -> 抓取 -> 保存"""
        try:
            # 随机延迟，避免并发过快被封
            time.sleep(random.uniform(0.5, 1.5))
            
            if self.url_exists(url):
                # self.logger.debug(f"URL已存在，跳过: {url}")
                return False

            article = self.fetch_article(url)
            if article and self.save_article(article):
                return True
            
        except Exception as e:
            self.logger.error(f"处理URL失败 {url}: {e}")
        
        return False

    def fetch_urls_by_selenium(self, url: str, scroll_count: int = 20) -> List[str]:
        """使用 Selenium 获取页面上的文章链接"""
        urls = []
        if not self.selenium_helper:
            return urls
            
        try:
            # 增加滚动次数以获取更多内容，优化等待时间
            html = self.selenium_helper.fetch_page(url, wait_time=2.0, scroll_count=scroll_count, pause_time=2.0)
            if not html:
                return []
                
            soup = BeautifulSoup(html, 'lxml')
            links = soup.find_all('a', href=True)
            
            # 匹配 YYYYMMDD 日期格式 (如 /20240101/) 或 8位以上字母数字ID
            id_pattern = re.compile(r'/\d{8}/|[A-Za-z0-9]{8,}')
            
            for link in links:
                href = link.get('href', '')
                # 匹配腾讯新闻文章 URL 模式 (放宽限制)
                if 'qq.com' in href:
                    # 排除非文章链接
                    if any(x in href for x in ['video', 'kbs', 'live', 'tv', 'show', 'signin', 'ad.']):
                        continue
                    
                    # 必须包含 /a/ 或 .htm 或 看起来像文章ID
                    if '/a/' in href or '.htm' in href or id_pattern.search(href):
                        if href.startswith('//'):
                            href = 'https:' + href
                        elif href.startswith('/'):
                            href = urljoin(url, href)
                            
                        if href not in urls:
                            urls.append(href)
            
            # 去重
            urls = list(dict.fromkeys(urls))
            return urls
            
        except Exception as e:
            self.logger.error(f"Selenium 获取 URL 失败 {url}: {e}")
            return []

    def fetch_article_list(self) -> List[str]:
        """获取文章列表页 (保留 requests 方式作为后备，但实际逻辑已移至 Selenium)"""
        # 兼容旧接口，实际上应该使用 fetch_urls_by_selenium
        if self.selenium_helper:
            return self.fetch_urls_by_selenium(self.seed_url)
        
        # 以下是旧的 requests 逻辑，保留以防 Selenium 初始化失败
        urls = []
        try:
            response = requests.get(
                self.seed_url,
                headers=self.get_headers(),
                timeout=self.timeout
            )

            if response.status_code != 200:
                return []

            soup = BeautifulSoup(response.content, 'lxml')
            links = soup.find_all('a', href=True)
            for link in links:
                href = link.get('href', '')
                if ('news.qq.com' in href or 'new.qq.com' in href) and '.shtml' in href:
                    if href not in urls:
                        urls.append(href)
            urls = list(dict.fromkeys(urls))
        except Exception:
            pass
        return urls

    def fetch_article(self, url: str) -> Optional[Dict]:
        """获取单篇文章详情"""
        try:
            response = self.session.get(
                url,
                headers=self.get_headers(),
                timeout=self.timeout
            )

            if response.status_code != 200:
                self.logger.error(f"请求失败: {url} 状态码: {response.status_code}")
                return None

            soup = BeautifulSoup(response.content, 'lxml')

            # 提取标题
            title = ""
            title_node = soup.select_one('h1, .title, .article-title')
            if title_node:
                title = self.clean_text(title_node.get_text())
            if not title and soup.title:
                title = soup.title.string.strip() if soup.title.string else ""

            if not title or len(title) < 5:
                # 尝试再次解析 (部分新版页面结构不同)
                title_node = soup.select_one('.content-article h1')
                if title_node:
                    title = self.clean_text(title_node.get_text())

            if not title or len(title) < 5:
                self.logger.debug(f"标题为空或过短，跳过: {url}")
                return None

            # 提取作者
            author = ""
            author_node = soup.select_one('.author, .source, .editor, [class*="author"]')
            if author_node:
                author = author_node.get_text(strip=True)

            # 提取正文
            content = ""
            content_node = soup.select_one('.article-content, .content, .text, article, .qq_article')
            if not content_node:
                 content_node = soup.select_one('.content-article .content-article') # 新版可能结构
            
            if content_node:
                for script in content_node(['script', 'style', 'nav', 'footer']):
                    script.decompose()
                content = self.clean_text(content_node.get_text(separator='\n'))

            # 提取发布时间
            publish_date = None
            date_node = soup.select_one('meta[property="article:published_time"], .time, .publish-time, [class*="time"]')
            if date_node:
                if date_node.name == 'meta':
                    pub_raw = date_node.get("content", "")
                else:
                    pub_raw = date_node.get_text(strip=True)
                if pub_raw:
                    publish_date = self.try_parse_date(pub_raw)

            # 提取描述
            description = ""
            desc_node = soup.select_one('meta[name="description"]')
            if desc_node:
                description = desc_node.get("content", "")

            return {
                'url': url,
                'title': title,
                'author': author or "腾讯新闻",
                'content': content,
                'publish_date': publish_date,
                'keywords': [],
                'description': description[:200] if description else ""
            }

        except requests.Timeout:
            self.logger.error(f"获取文章详情超时: {url}")
        except requests.ConnectionError as e:
            self.logger.error(f"获取文章详情连接失败: {url} - {e}")
        except Exception as e:
            self.logger.error(f"获取文章详情失败 {url}: {e}")

        return None

    def save_article(self, article: Dict) -> bool:
        """保存文章到 MySQL 数据库"""
        url = article.get('url', '')
        if self.url_exists(url):
            self.logger.debug(f"URL已存在，跳过: {url[:50]}...")
            return False

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
        return self.db.insert_raw_article(raw_item, self._get_source_id())

    def _get_source_id(self) -> int:
        """获取来源ID"""
        source = self.db.get_source_by_code(self.source_code)
        return source["id"] if source else 0

    # ========== 签名API相关方法 ==========

    def fetch_ranking_list(self, channel: str = "news_recommend_hot") -> List[str]:
        """
        使用签名API获取排行榜文章列表
        """
        urls = []
        try:
            api_url = TencentSignature.generate_url(channel)
            self.logger.debug(f"请求签名API: {api_url[:100]}...")

            response = self.session.get(
                api_url,
                headers={
                    "User-Agent": random.choice(self.user_agents),
                    "Accept": "application/json",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                    "Referer": "https://news.qq.com/"
                },
                timeout=self.timeout
            )

            if response.status_code != 200:
                self.logger.error(f"API请求失败: 状态码 {response.status_code}")
                return []

            data = response.json()

            if data.get('ret') != 0:
                self.logger.error(f"API返回错误: ret={data.get('ret')}, data={data}")
                return []

            # 解析返回数据
            news_list = data.get('idlist', [])
            if not news_list:
                return []

            news_group = news_list[0] if news_list else {}
            if not news_group:
                return []
                
            news_items = news_group.get('newslist', [])

            for news in news_items:
                url = news.get('url') or news.get('surl', '')
                if url and url not in urls:
                    urls.append(url)

            self.logger.info(f"从API获取到 {len(urls)} 篇文章URL")
            return urls

        except Exception as e:
            self.logger.error(f"获取排行榜失败: {e}")

        return []
