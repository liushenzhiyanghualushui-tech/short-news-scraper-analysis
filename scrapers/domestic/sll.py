"""360 新闻爬虫 - 适配 short_new 的 MySQL"""

import logging
import random
import time
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse
import re

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.microsoft import EdgeChromiumDriverManager

from ..base import BaseScraper
from ..models import DomesticNewsItem, RawArticleItem


class SllScraper(BaseScraper):
    """360 新闻爬虫"""

    def __init__(self, config: dict, db_handler):
        super().__init__(config, db_handler)
        self.source_name = "360 新闻"
        self.source_code = "sll"
        self.seed_url = "https://news.so.com/"
        self.driver = None

    def __del__(self):
        """析构函数确保关闭 WebDriver"""
        self.close_driver()

    def _get_driver(self):
        """获取 Selenium WebDriver (Edge) - 支持本地驱动"""
        if self.driver is None:
            edge_options = EdgeOptions()
            edge_options.add_argument("--headless")  # 无头模式
            edge_options.add_argument("--no-sandbox")
            edge_options.add_argument("--disable-dev-shm-usage")
            edge_options.add_argument("--disable-gpu")
            edge_options.add_argument("--window-size=1920,1080")
            edge_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0")
            edge_options.add_argument("--disable-blink-features=AutomationControlled")
            edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            edge_options.add_experimental_option("useAutomationExtension", False)

            # 禁用 WebDriver 检测
            edge_options.add_argument("--disable-blink-features")
            edge_options.add_experimental_option("prefs", {
                "profile.managed_default_content_settings.images": 2,  # 不加载图片
                "profile.managed_default_content_settings.stylesheets": 2,
            })

            try:
                # 尝试使用本地 EdgeDriver (优先)
                import os
                # 使用绝对路径指向项目根目录下的 msedgedriver.exe
                local_driver_path = os.path.abspath("msedgedriver.exe")
                
                if os.path.exists(local_driver_path):
                    self.logger.info(f"使用本地 EdgeDriver: {local_driver_path}")
                    service = EdgeService(local_driver_path)
                else:
                    self.logger.warning(f"本地驱动未找到: {local_driver_path}，尝试其他路径")
                    # 尝试从系统 PATH 查找
                    service = None
                    for path in os.environ.get('PATH', '').split(';'):
                        driver_path = os.path.join(path, 'msedgedriver.exe')
                        if os.path.exists(driver_path):
                            self.logger.info(f"使用系统 EdgeDriver: {driver_path}")
                            service = EdgeService(driver_path)
                            break

                    # 如果都没找到，尝试使用 webdriver_manager
                    if service is None:
                        self.logger.info("尝试下载 EdgeDriver...")
                        service = EdgeService(EdgeChromiumDriverManager().install())

                self.driver = webdriver.Edge(service=service, options=edge_options)

                # 执行反检测脚本 - 增强版
                self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                    "source": """
                        // 隐藏 webdriver 属性
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined
                        });

                        // 模拟真实浏览器插件
                        Object.defineProperty(navigator, 'plugins', {
                            get: () => [1, 2, 3, 4, 5]
                        });

                        // 模拟真实语言设置
                        Object.defineProperty(navigator, 'languages', {
                            get: () => ['zh-CN', 'zh', 'en']
                        });

                        // 隐藏自动化特征
                        delete navigator.__proto__.webdriver;

                        // 模拟 Chrome 对象
                        window.navigator.chrome = {
                            runtime: {},
                            app: {},
                            identity: {}
                        };

                        // 模拟真实的屏幕分辨率
                        Object.defineProperty(window, 'screen', {
                            get: () => ({
                                width: 1920,
                                height: 1080,
                                availWidth: 1920,
                                availHeight: 1040,
                                colorDepth: 24,
                                pixelDepth: 24
                            })
                        });

                        // 模拟硬件并发数
                        Object.defineProperty(navigator, 'hardwareConcurrency', {
                            get: () => 8
                        });

                        // 模拟设备内存
                        Object.defineProperty(navigator, 'deviceMemory', {
                            get: () => 8
                        });

                        // 禁用自动化提示
                        window.cdc_abc = undefined;
                        window.cdc_asdf = undefined;
                    """
                })

                self.logger.info("Edge WebDriver 初始化成功")
            except Exception as e:
                self.logger.error(f"Edge WebDriver 初始化失败: {e}")
                # 降级使用 requests
                self.driver = None

        return self.driver

    def close_driver(self):
        """关闭 WebDriver - 确保资源释放"""
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("Edge WebDriver 已关闭")
            except Exception as e:
                self.logger.error(f"关闭 Edge WebDriver 时出错: {e}")
            finally:
                self.driver = None

    def _safe_close_driver(self):
        """安全关闭 WebDriver（用于 run 方法）"""
        """确保 WebDriver 关闭"""
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("Edge WebDriver 已关闭")
            except Exception as e:
                self.logger.error(f"关闭 Edge WebDriver 时出错: {e}")
            finally:
                self.driver = None

    def get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Referer": "https://www.360.com/"
        }

    def get_source_config(self) -> Dict:
        return {
            "name": self.source_name,
            "code": self.source_code,
            "type": "domestic",
            "seed_url": self.seed_url
        }

    def run(self) -> int:
        """执行爬取 - 增强版"""
        self.logger.info(f"开始爬取 {self.source_name}")

        try:
            article_urls = self.fetch_article_list()
            self.logger.info(f"获取到 {len(article_urls)} 篇文章URL")

            count = 0
            for url in article_urls:
                article = self.fetch_article(url)
                if article and self.save_article(article):
                    count += 1
                self.random_delay()

            self.logger.info(f"{self.source_name} 爬取完成，共保存 {count} 条")
            return count
        except Exception as e:
            self.logger.error(f"{self.source_name} 爬取出错: {e}")
            import traceback
            traceback.print_exc()
            return 0
        finally:
            # 确保 WebDriver 关闭
            if self.driver:
                self._safe_close_driver()

    def fetch_article_list(self) -> List[str]:
        """获取文章列表页"""
        urls = []
        driver = None

        try:
            driver = self._get_driver()

            if driver is None:
                # 降级使用 requests
                self.logger.warning("WebDriver 不可用，降级使用 requests")
                return self._fetch_with_requests()

            self.logger.info("使用 Selenium 获取页面...")
            driver.get(self.seed_url)

            # 等待页面加载 - 增强版等待策略
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                self.logger.debug("页面 body 已加载")
            except Exception as e:
                self.logger.warning(f"等待页面 body 超时: {e}")

            # 动态内容加载等待 - 使用多个备用选择器
            wait_selectors = [
                (By.CSS_SELECTOR, "a[href*='360kuai.com']"),
                (By.CSS_SELECTOR, "[class*='news-list'], [class*='article-list'], [class*='feed']"),
                (By.CSS_SELECTOR, ".layout, .container, main"),
                (By.TAG_NAME, "article"),
            ]

            for selector in wait_selectors:
                try:
                    WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located(selector)
                    )
                    self.logger.debug(f"检测到选择器: {selector}")
                    break
                except Exception:
                    continue

            # 随机滚动页面模拟人类行为，触发懒加载
            try:
                for i in range(3):
                    driver.execute_script(f"window.scrollTo(0, {i * 500});")
                    time.sleep(random.uniform(0.5, 1.0))
                # 滚动回顶部
                driver.execute_script("window.scrollTo(0, 0);")
            except Exception:
                pass

            # 获取页面源码
            page_source = driver.page_source
            final_url = driver.current_url
            self.logger.debug(f"最终请求URL: {final_url}")

            soup = BeautifulSoup(page_source, 'lxml')

            # 方法1: 查找所有链接，筛选新闻文章
            found_urls = []
            for link in soup.find_all('a', href=True):
                href = link.get('href', '').strip()
                full_url = self._normalize_url(href, final_url)

                if full_url and self._is_news_url(full_url):
                    if full_url not in found_urls:
                        found_urls.append(full_url)

            self.logger.debug(f"找到 {len(found_urls)} 个候选链接")

            # 方法2: 查找包含新闻链接的区域 - 增强版选择器
            news_selectors = [
                'div[class*="news"]', 'div[class*="article"]', 'div[class*="list"]',
                'section', 'main', '.container', '.layout', '.feed',
                '[class*="news-list"]', '[class*="article-list"]', '[class*="content-list"]',
                '.wrap', '.bd', '.main-content', '[data-component*="news"]',
                '.info-list', '.news-wrap', '.article-wrap', '.news-box'
            ]
            news_sections = soup.select(', '.join(news_selectors))

            for section in news_sections:
                for link in section.find_all('a', href=True):
                    href = link.get('href', '').strip()
                    full_url = self._normalize_url(href, final_url)

                    if full_url and self._is_news_url(full_url):
                        if full_url not in found_urls:
                            found_urls.append(full_url)

            self.logger.debug(f"从新闻区域找到 {len(found_urls)} 个链接")

            # 方法3: 使用 Selenium 直接查找链接元素
            all_links = driver.find_elements(By.TAG_NAME, "a")
            for link_elem in all_links:
                try:
                    href = link_elem.get_attribute("href")
                    if href and self._is_news_url(href):
                        if href not in found_urls:
                            found_urls.append(href)
                except Exception:
                    continue

            self.logger.debug(f"Selenium 直接找到 {len(found_urls)} 个链接")

            # 方法4: 查找特定模式的 JSON-LD 数据
            for script in soup.find_all('script', type='application/ld+json'):
                if script.string:
                    # 提取所有 URL
                    urls_in_json = re.findall(r'https?://[^\s<>"]+', script.string)
                    for url in urls_in_json:
                        if self._is_news_url(url):
                            if url not in found_urls:
                                found_urls.append(url)

            # 去重并限制数量
            urls = list(dict.fromkeys(found_urls))[:1000]

            self.logger.info(f"最终提取到 {len(urls)} 篇文章URL")

        except Exception as e:
            self.logger.error(f"获取文章列表失败: {e}")
            import traceback
            traceback.print_exc()
            # 尝试降级
            try:
                urls = self._fetch_with_requests()
            except Exception as fallback_error:
                self.logger.error(f"降级方案也失败: {fallback_error}")

        finally:
            pass  # driver 在 finally 中由 run 方法关闭

        return urls

    def _fetch_with_requests(self) -> List[str]:
        """使用 requests 获取文章列表（降级方案）- 增强版"""
        urls = []
        try:
            session = requests.Session()

            # 增强请求头，模拟真实浏览器
            enhanced_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Cache-Control": "max-age=0",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Referer": "https://news.so.com/",
            }

            # 设置重试适配器
            adapter = requests.adapters.HTTPAdapter(max_retries=3)
            session.mount('http://', adapter)
            session.mount('https://', adapter)

            self.logger.info("使用 requests 获取页面...")
            
            # 直接访问 360快讯主页（更容易获取文章列表）
            try:
                response = session.get(
                    "https://www.360kuai.com/pc/",
                    headers=enhanced_headers,
                    timeout=self.timeout,
                    allow_redirects=True
                )
                final_url = response.url
            except Exception:
                # 备用：访问原始种子URL
                response = session.get(
                    self.seed_url,
                    headers=enhanced_headers,
                    timeout=self.timeout,
                    allow_redirects=True
                )
                final_url = response.url

            if response.status_code != 200:
                self.logger.error(f"请求失败: 状态码 {response.status_code}")
                return []

            self.logger.debug(f"最终请求URL: {final_url}")
            self.logger.debug(f"响应内容长度: {len(response.content)} bytes")

            soup = BeautifulSoup(response.content, 'lxml')

            # 打印页面 title 用于调试
            if soup.title:
                self.logger.debug(f"页面标题: {soup.title.string}")

            # 查找所有链接，筛选新闻文章
            found_urls = []
            for link in soup.find_all('a', href=True):
                href = link.get('href', '').strip()
                full_url = self._normalize_url(href, final_url)

                if full_url and self._is_news_url(full_url):
                    if full_url not in found_urls:
                        found_urls.append(full_url)

            self.logger.debug(f"找到 {len(found_urls)} 个候选链接")

            # 如果没找到，尝试从 script 标签中提取 URL（可能是 JSON 数据）
            if len(found_urls) == 0:
                self.logger.debug("尝试从 script 标签中提取 URL...")
                for script in soup.find_all('script'):
                    script_text = script.get_text()
                    if script_text:
                        # 提取所有 URL
                        urls_in_script = re.findall(r'https?://[^\s<>"\']+', script_text)
                        for url in urls_in_script:
                            if self._is_news_url(url) and url not in found_urls:
                                found_urls.append(url)
                self.logger.debug(f"从 script 中找到 {len(found_urls)} 个链接")

            # 去重并限制数量
            urls = list(dict.fromkeys(found_urls))[:1000]
            self.logger.info(f"最终提取到 {len(urls)} 篇文章URL")

        except requests.Timeout:
            self.logger.error("requests 请求超时")
        except requests.ConnectionError as e:
            self.logger.error(f"requests 连接失败: {e}")
        except Exception as e:
            self.logger.error(f"requests 获取文章列表失败: {e}")

        return urls

    def _normalize_url(self, href: str, base_url: str) -> Optional[str]:
        """标准化 URL"""
        if not href:
            return None

        # 跳过空链接和锚点
        if href.startswith('#') or href == 'javascript:;':
            return None

        # 处理相对路径
        if href.startswith('/'):
            parsed_base = urlparse(base_url)
            full_url = f"{parsed_base.scheme}://{parsed_base.netloc}{href}"
        elif href.startswith('./'):
            parsed_base = urlparse(base_url)
            base_dir = '/'.join(base_url.rstrip('/').split('/')[:-1])
            full_url = base_dir + href[1:]
        elif href.startswith('../'):
            full_url = urljoin(base_url, href)
        elif href.startswith('http://') or href.startswith('https://'):
            full_url = href
        else:
            # 其他情况，使用 urljoin
            full_url = urljoin(base_url, href)

        return full_url

    def _is_news_url(self, url: str) -> bool:
        """判断是否为新闻文章 URL - 增强版"""
        if not url:
            return False

        # 排除非新闻链接
        exclude_patterns = [
            'news.so.com/tuijian',  # 推荐页
            'news.so.com/p',       # 分页
            '360.com/help',        # 帮助页
            '360.com/about',       # 关于页
            'javascript:',         # JS 链接
            '#',                   # 锚点
            'login',               # 登录页
            'register',            # 注册页
            'search',              # 搜索页
            'sitemap',             # 站点地图
        ]

        for pattern in exclude_patterns:
            if pattern in url.lower():
                return False

        # 新闻文章 URL 模式 - 增强版，新增更多匹配模式
        news_patterns = [
            r'360kuai\.com/p/\d+',           # /p/数字
            r'360kuai\.com/c/\d+',           # /c/数字
            r'360kuai\.com/a/\d+',           # /a/数字
            r'360kuai\.com/pc/',             # /pc/ 任意参数 (PC端主页)
            r'360kuai\.com/m/',              # /m/ 任意参数 (移动端)
            r'360kuai\.com/',                # 360kuai.com 任意页面（可能包含文章）
            r'news\.so\.com/\w+\.shtml',     # /xxx.shtml
            r'news\.so\.com/\?a=\w+',        # /?a=xxx (参数化)
            r'minfo\.hk\.360\.com',          # 财经信息
            r'www\.360kuai\.com/web/',       # web 子站
            r'360\.com/\w+/\d+\.shtml',      # 360.com 文章
            r'inews\.360\.com',              # iNews
            r'inews\.360\.com/\d+',          # iNews 文章页
            r'www\.360kuai\.com/detail/\d+', # 详情页
            r'm\.360kuai\.com/\w+/\d+\.shtml',  # 移动端文章
        ]

        for pattern in news_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return True

        # 检查域名
        domain = urlparse(url).netloc.lower()
        if '360kuai.com' in domain or '360.com' in domain or 'news.so.com' in domain:
            # 检查路径是否像文章
            path = urlparse(url).path
            if re.search(r'/\w+\d+\.shtml|/a/\d+|/c/\d+|/p/\d+|/pc/\d+|/m/\w+', path):
                return True
            # 对于 360kuai.com 域名，如果路径很短/为空，也可能是文章页
            if '360kuai.com' in domain and (path == '/' or len(path) <= 5):
                return True

        return False

    def fetch_article(self, url: str) -> Optional[Dict]:
        """获取单篇文章详情 - 增强版"""
        try:
            response = requests.get(
                url,
                headers=self.get_headers(),
                timeout=self.timeout
            )

            if response.status_code != 200:
                self.logger.error(f"请求失败: {url} 状态码: {response.status_code}")
                return None

            soup = BeautifulSoup(response.content, 'lxml')

            # 提取标题 - 多种选择器增强版
            title = ""
            title_selectors = [
                'h1', '.title', '.article-title', '.headline', '.news-title',
                'h2.title', '.post-title', '.entry-title', '[class*="title"]',
                '.article-h1', '.news-h1', 'article h1', '.content h1',
                'meta[property="og:title"]', 'meta[name="twitter:title"]'
            ]
            for selector in title_selectors:
                title_node = soup.select_one(selector)
                if title_node:
                    if title_node.name == 'meta':
                        title = self.clean_text(title_node.get('content', ''))
                    else:
                        title = self.clean_text(title_node.get_text())
                    if title and len(title) >= 5:
                        break

            # 如果没找到，尝试从 meta og:title 获取
            if not title or len(title) < 5:
                og_title = soup.select_one('meta[property="og:title"]')
                if og_title:
                    title = og_title.get('content', '').strip()

            # 如果还没找到，使用页面 title
            if not title or len(title) < 5:
                if soup.title:
                    title = soup.title.string.strip() if soup.title.string else ""
                    # 移除网站名称后缀
                    title = re.sub(r'[-_|].*(360|快新闻|新闻).*$', '', title, flags=re.IGNORECASE)

            if not title or len(title) < 5:
                self.logger.debug(f"标题为空或过短，跳过: {url[:50]}...")
                return None

            # 提取作者 - 增强版
            author = ""
            author_selectors = [
                '.author', '.source', '.editor', '[class*="author"]',
                '[class*="source"]', '.publish-source', '.post-meta [class*="author"]',
                '.meta-item [class*="author"]', '.article-meta span', '.news-source',
                'meta[property="og:article:author"]', '[itemprop="author"]'
            ]
            for selector in author_selectors:
                author_node = soup.select_one(selector)
                if author_node:
                    if author_node.name == 'meta':
                        author = self.clean_text(author_node.get('content', ''))
                    else:
                        author = self.clean_text(author_node.get_text())
                    if author:
                        break

            # 从 meta 获取来源
            if not author:
                meta_source = soup.select_one('meta[property="og:site_name"]')
                if meta_source:
                    author = meta_source.get('content', '').strip()

            # 提取正文 - 增强版
            content = ""
            content_selectors = [
                '.article-content', '.content', '.text', '#content', 'article',
                '.detail-content', '.news-content', '[class*="article"]',
                '.post-content', '.entry-content', '[class*="content"]',
                '.article-body', '.news-body', '.article-text', '.news-text',
                '[itemprop="articleBody"]', '.article-detail', '.news-detail'
            ]
            for selector in content_selectors:
                content_node = soup.select_one(selector)
                if content_node:
                    # 移除脚本和样式
                    for script in content_node(['script', 'style', 'nav', 'footer', 'iframe', 'aside', 'form']):
                        script.decompose()
                    # 移除广告和推荐内容
                    for ad in content_node.find_all(['div', 'section'], class_=re.compile(r'ad|ads|advert|recommend|related', re.I)):
                        ad.decompose()
                    content = self.clean_text(content_node.get_text(separator='\n'))
                    if content and len(content) >= 50:  # 降低阈值，确保内容不是太短
                        break

            # 提取发布时间 - 增强版
            publish_date = None
            date_selectors = [
                'meta[property="article:published_time"]',
                'meta[name="publishdate"]',
                'meta[name="date"]',
                '.time', '.publish-time', '[class*="time"]',
                '[class*="date"]', '.pub-time', 'time', '[datetime]',
                '[itemprop="datePublished"]', '.article-time', '.news-time',
                '.create-time', '.publishDate', '.pubDate'
            ]
            for selector in date_selectors:
                date_node = soup.select_one(selector)
                if date_node:
                    if date_node.name == 'meta':
                        pub_raw = date_node.get("content", "")
                    else:
                        pub_raw = date_node.get("datetime", "") or date_node.get_text(strip=True)
                    if pub_raw:
                        publish_date = self.try_parse_date(pub_raw)
                        if publish_date:
                            break

            # 提取描述
            description = ""
            desc_node = soup.select_one('meta[name="description"], meta[property="og:description"]')
            if desc_node:
                description = desc_node.get("content", "")

            return {
                'url': url,
                'title': title.strip(),
                'author': author or "360新闻",
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
            import traceback
            traceback.print_exc()

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
