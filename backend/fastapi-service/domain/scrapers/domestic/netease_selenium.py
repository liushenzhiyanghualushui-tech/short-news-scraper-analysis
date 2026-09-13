"""
网易新闻爬虫专用 Selenium 工具类
用于处理网易新闻页面的动态渲染和反爬虫机制
"""
import re
import time
import random
import logging
import hashlib
from typing import Optional, List, Dict
from urllib.parse import urljoin

import os
from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

logger = logging.getLogger("NeteaseSelenium")


# 网易新闻专用的User-Agent列表
NETEASE_USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
]


def generate_random_fingerprint():
    """生成随机的浏览器指纹数据"""
    return {
        'screen_resolution': f"{random.randint(1920, 2560)}x{random.randint(1080, 1440)}",
        'avail_screen': f"{random.randint(1920, 2560)}x{random.randint(900, 1200)}",
        'color_depth': random.choice([24, 32]),
        'pixel_ratio': random.choice([1, 1.25, 1.5, 2, 2.5, 3]),
        'timezone_offset': random.choice([-480, -420, -360, -300, -240, -180, -120, -60, 0, 60, 120, 180, 240, 300, 360, 420, 480]),
        'language': random.choice(['zh-CN', 'zh', 'en-US', 'en']),
        'hardware_concurrency': random.choice([2, 4, 8, 12, 16]),
        'device_memory': random.choice([2, 4, 8, 16]),
        'platform': random.choice(['Win32', 'MacIntel', 'Linux armv8l']),
    }


def get_antidetect_script(fingerprint=None):
    """生成反检测JavaScript脚本"""
    if fingerprint is None:
        fingerprint = generate_random_fingerprint()

    webgl_vendors = [
        'Google Inc. (NVIDIA)',
        'Google Inc. (AMD)',
        'Google Inc. (Intel)',
    ]
    webgl_renderers = [
        'ANGLE (NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0)',
        'ANGLE (AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0)',
        'ANGLE (Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0)',
    ]
    canvas_noise = hashlib.md5(str(random.random()).encode()).hexdigest()[:16]

    script = f"""
    const FINGERPRINT = {{
        screen_resolution: "{fingerprint['screen_resolution']}",
        avail_screen: "{fingerprint['avail_screen']}",
        color_depth: {fingerprint['color_depth']},
        pixel_ratio: {fingerprint['pixel_ratio']},
        timezone_offset: {fingerprint['timezone_offset']},
        language: "{fingerprint['language']}",
        hardware_concurrency: {fingerprint['hardware_concurrency']},
        device_memory: {fingerprint['device_memory']},
        platform: "{fingerprint['platform']}"
    }};

    // 覆盖 navigator 属性
    Object.defineProperty(navigator, 'language', {{
        get: () => FINGERPRINT.language,
        configurable: true
    }});
    Object.defineProperty(navigator, 'languages', {{
        get: () => [FINGERPRINT.language, 'en'],
        configurable: true
    }});
    Object.defineProperty(navigator, 'hardwareConcurrency', {{
        get: () => FINGERPRINT.hardware_concurrency,
        configurable: true
    }});
    Object.defineProperty(navigator, 'deviceMemory', {{
        get: () => FINGERPRINT.device_memory,
        configurable: true
    }});
    Object.defineProperty(navigator, 'platform', {{
        get: () => FINGERPRINT.platform,
        configurable: true
    }});
    Object.defineProperty(navigator, 'maxTouchPoints', {{
        get: () => 0,
        configurable: true
    }});

    // 时区偏移
    Date.prototype.getTimezoneOffset = function() {{
        return FINGERPRINT.timezone_offset;
    }};

    // 窗口尺寸
    Object.defineProperty(window, 'innerWidth', {{
        get: () => parseInt(FINGERPRINT.screen_resolution.split('x')[0]),
        configurable: true
    }});
    Object.defineProperty(window, 'innerHeight', {{
        get: () => parseInt(FINGERPRINT.avail_screen.split('x')[1]),
        configurable: true
    }});

    // WebGL 指纹
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {{
        if (parameter === 37445) return '{random.choice(webgl_vendors)}';
        if (parameter === 37446) return '{random.choice(webgl_renderers)}';
        return getParameter.call(this, parameter);
    }};

    // Canvas 噪声
    const originalGetImageData = CanvasRenderingContext2D.prototype.getImageData;
    CanvasRenderingContext2D.prototype.getImageData = function() {{
        const imageData = originalGetImageData.apply(this, arguments);
        const noise = '{canvas_noise}';
        for (let i = 0; i < imageData.data.length; i += 4) {{
            const hash = (i * parseInt(noise.charAt(i % 16), 16)) % 3;
            imageData.data[i + hash] = (imageData.data[i + hash] + hash) % 256;
        }}
        return imageData;
    }};

    // 覆盖 navigator.webdriver
    Object.defineProperty(navigator, 'webdriver', {{
        get: () => false,
        configurable: true
    }});

    // console.log 伪装
    const originalConsoleLog = console.log;
    console.log = function() {{}};
    const originalConsoleDebug = console.debug;
    console.debug = function() {{}};
    const originalConsoleInfo = console.info;
    console.info = function() {{}};
    """
    return script


class NeteaseSelenium:
    """网易新闻 Selenium 爬虫"""

    def __init__(self, driver_path: str = None, headless: bool = True):
        """
        初始化网易新闻爬虫

        Args:
            driver_path: WebDriver路径，如果为None则自动查找
            headless: 是否使用无头模式
        """
        self.driver_path = driver_path
        self.headless = headless
        self.driver = None
        self.fingerprint = generate_random_fingerprint()

    def create_driver(self):
        """创建浏览器实例"""
        # 如果未指定 driver_path，默认使用项目根目录下的 msedgedriver.exe
        if not self.driver_path:
            self.driver_path = os.path.abspath("msedgedriver.exe")

        try:
            # 尝试使用Edge
            options = EdgeOptions()
        except:
            logger.error("无法创建浏览器选项")
            return False

        # 基础配置
        options.add_argument('--headless' if self.headless else '')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument(f'--user-agent={random.choice(NETEASE_USER_AGENTS)}')
        options.add_argument('--disable-blink-features=AutomationControlled')
        
        # 屏蔽 SSL 错误和日志
        options.add_argument('--log-level=3')
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--ignore-ssl-errors')
        options.add_argument('--silent')
        
        options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
        options.add_experimental_option('useAutomationExtension', False)

        try:
            # 尝试Edge
            if self.driver_path and os.path.exists(self.driver_path):
                service = EdgeService(executable_path=self.driver_path)
                self.driver = webdriver.Edge(service=service, options=options)
            else:
                self.driver = webdriver.Edge(options=options)

            self._apply_antidetect()
            logger.info("浏览器初始化成功 (Edge)")
            return True

        except WebDriverException as e:
            logger.error(f"Edge初始化失败: {e}")
            return False

    def _apply_antidetect(self):
        """应用反检测措施"""
        if not self.driver:
            return

        try:
            # 执行反检测脚本
            script = get_antidetect_script(self.fingerprint)
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': script
            })

            # 移除webdriver标记
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

        except Exception as e:
            logger.debug(f"反检测应用失败: {e}")

    def close(self):
        """关闭浏览器"""
        if self.driver:
            try:
                self.driver.quit()
                logger.debug("浏览器已关闭")
            except Exception as e:
                logger.debug(f"关闭浏览器时出错: {e}")
            self.driver = None

    def _check_driver_health(self) -> bool:
        """检查浏览器连接是否正常"""
        if not self.driver:
            return False
        try:
            # 尝试执行简单命令检测连接状态
            self.driver.execute_script("return document.readyState")
            return True
        except Exception as e:
            logger.warning(f"浏览器连接异常: {e}")
            return False

    def _recreate_driver(self) -> bool:
        """重新创建浏览器实例"""
        try:
            # 先尝试关闭旧浏览器
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
                self.driver = None

            # 重新创建
            logger.info("正在重新初始化浏览器...")
            time.sleep(2)  # 等待浏览器完全关闭
            return self.create_driver()
        except Exception as e:
            logger.error(f"重新创建浏览器失败: {e}")
            return False

    def fetch_page(self, url: str, wait_time: float = 8.0, scroll_count: int = 3, pause_time: float = 5.0) -> Optional[str]:
        """
        获取页面HTML，增加等待时间和稳定性

        Args:
            url: 目标URL
            wait_time: 初始等待时间（增加默认值）
            scroll_count: 滚动次数（减少默认值以提高稳定性）
            pause_time: 每次滚动后的等待时间

        Returns:
            页面HTML字符串，失败返回None
        """
        # 检查浏览器连接
        if not self._check_driver_health():
            if not self._recreate_driver():
                return None

        try:
            logger.debug(f"正在访问: {url}")

            # 访问页面
            self.driver.get(url)

            # 等待页面加载
            time.sleep(wait_time)

            # 页面滚动
            self._scroll_page(scroll_count, pause_time=pause_time)

            # 随机滚动一点，模拟人类行为
            self._simulate_human_behavior()

            return self.driver.page_source

        except TimeoutException:
            logger.warning(f"页面加载超时: {url}")
        except WebDriverException as e:
            logger.error(f"WebDriver错误: {e}")
            # 尝试重新创建浏览器
            self._recreate_driver()
        except Exception as e:
            logger.error(f"获取页面失败: {e}")

        return None

    def _scroll_page(self, scroll_count: int = 5, pause_time: float = 5.0):
        """
        滚动页面加载更多内容 - 优化版本，增加延迟和稳定性

        Args:
            scroll_count: 最大滚动次数
            pause_time: 每次滚动后的等待时间（增加默认值以提高稳定性）
        """
        if not self.driver:
            return

        try:
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            consecutive_no_change = 0  # 连续无变化次数
            max_no_change = 3  # 增加容错，连续3次无变化才停止

            for i in range(scroll_count):
                # 滚动前先随机停留，模拟人类思考
                time.sleep(random.uniform(1.0, 2.0))

                # 渐进式滚动，每次滚动不同的距离，模拟人类行为
                scroll_step = random.randint(600, 1000) # 增加单次滚动距离
                self.driver.execute_script(f"window.scrollBy(0, {scroll_step});")

                # 滚动后等待页面加载
                time.sleep(pause_time)

                new_height = self.driver.execute_script("return document.body.scrollHeight")

                if new_height == last_height:
                    consecutive_no_change += 1
                    # 尝试强制滚动到底部一次，看看能否触发加载
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(pause_time)
                    new_height = self.driver.execute_script("return document.body.scrollHeight")
                    
                    if new_height == last_height:
                        if consecutive_no_change >= max_no_change:
                            logger.info(f"滚动停止，已达到页面底部 (连续 {max_no_change} 次无变化)")
                            break
                        else:
                            logger.debug(f"页面高度无变化 ({consecutive_no_change}/{max_no_change})，继续尝试...")
                    else:
                         consecutive_no_change = 0 # 恢复
                         last_height = new_height
                else:
                    consecutive_no_change = 0  # 重置计数器
                    last_height = new_height
                    
                    # 每5次滚动输出一次INFO日志，避免日志过多但又能看到进度
                    if (i + 1) % 5 == 0:
                        logger.info(f"页面滚动进度: {i + 1}/{scroll_count}, 当前高度: {new_height}")
                    else:
                        logger.debug(f"滚动页面 {i + 1}/{scroll_count}, 页面高度: {new_height}")

                # 每次滚动后随机微调，模拟人类行为
                if i < scroll_count - 1:
                    self._mini_scroll()

        except Exception as e:
            logger.warning(f"页面滚动失败: {e}")

    def _mini_scroll(self):
        """微滚动 - 模拟人类行为，增加延迟"""
        if not self.driver:
            return
        try:
            # 随机向前或向后微滚动
            direction = random.choice([-1, 1])
            offset = random.randint(30, 100)
            self.driver.execute_script(f"window.scrollBy(0, {direction * offset});")
            # 增加延迟，让动作更自然
            time.sleep(random.uniform(0.3, 0.6))
        except:
            pass

    def _simulate_human_behavior(self):
        """模拟人类行为，增加延迟以提高稳定性"""
        if not self.driver:
            return

        try:
            # 模拟人类阅读时的随机停留
            time.sleep(random.uniform(1.0, 2.0))

            # 随机滚动一点点，模拟人类浏览
            scroll_x = random.randint(0, 300)
            scroll_y = random.randint(100, 500)
            self.driver.execute_script(f"window.scrollBy({scroll_x}, {scroll_y});")

            # 滚动后再停留一段时间
            time.sleep(random.uniform(0.8, 1.5))

        except Exception as e:
            logger.debug(f"模拟人类行为失败: {e}")

    def extract_article_urls(self, html: str, base_url: str = None) -> List[str]:
        """
        从HTML中提取网易新闻文章URL

        Args:
            html: 页面HTML
            base_url: 基础URL

        Returns:
            文章URL列表
        """
        from bs4 import BeautifulSoup

        if not html:
            return []

        soup = BeautifulSoup(html, 'lxml')
        article_urls = []
        seen_urls = set()

        # 网易新闻文章URL正则 - 支持多种格式
        # 格式1: https://www.163.com/news/article/KKOGO36S000189FH.html (新闻文章)
        # 格式2: https://www.163.com/news/video/VVJQTGAD7.html (视频)
        # 格式3: https://news.163.com/24/0106/07/GT0S1VCR001098KT.html (旧格式)
        # 格式4: https://news.163.com/domestic/ (分类页面 - 也需要爬取)
        url_pattern = re.compile(r'''
            (?:^|/)                                   # 开头或斜杠
            (?:                                       # 非捕获组
                news/(?:article|video)/[A-Z0-9]+      # news/article/xxx 或 news/video/xxx
                (?:\.html?)?                           # 可选的 .html 或 .htm
                |                                       # 或
                \d{2}/\d{4}/\d{2}/[A-Z0-9]{14,20}     # 旧格式 /yy/MM/dd/xxxxxxxxxxxx.html
                (?:\.html?)?
            )
        ''', re.IGNORECASE | re.VERBOSE)

        # 只允许的域名模式 - 只爬取主站新闻
        allowed_domains = [
            'www.163.com/news/',
            'www.163.com/article/',
            'www.163.com/special/',
        ]
        
        # 排除的模式 - 非新闻页面
        exclude_patterns = [
            'javascript:', '#', 'mailto:',
            'gov.163.com',       # 政府网
            'hz.163.com',        # 杭州网
            'exam.163.com',      # 考试
            'daxue.163.com',     # 大学
            'zhuanti', 'special',    # 专题
            '/download', '/app', '/login', '/register',  # 功能页面
            'v.163.com',         # 视频
            'music.163.com',     # 音乐
            'game.163.com',      # 游戏
            'mail.163.com',      # 邮箱
            'blog.163.com',      # 博客
            'photo.163.com',     # 摄影
            'lady.163.com',      # 女人
            'baby.163.com',      # 育儿
            'home.163.com',      # 家居
            'diy.163.com',       # DIY
            'http://www.163.com/diy',  # 家居装修
            'http://www.163.com/home', # 家居
            'http://www.163.com/lady',  # 女人
        ]

        for link in soup.find_all('a', href=True):
            href = link.get('href', '')

            # 排除无效链接
            if not href:
                continue
            
            # 排除包含排除模式的链接
            if any(ex in href for ex in exclude_patterns):
                continue

            # 匹配网易新闻文章URL
            if not url_pattern.search(href):
                continue
            
            # 构建完整URL
            if href.startswith('http'):
                full_url = href
            elif href.startswith('/news/article/') or href.startswith('/news/video/'):
                full_url = f'https://www.163.com{href}'
            elif href.startswith('/'):
                full_url = f'https://www.163.com{href}'
            else:
                full_url = f'https://www.163.com/{href}'

            # 标准化URL（去除锚点和查询参数）
            full_url = full_url.split('#')[0].split('?')[0]
            
            # 只保留主站新闻URL，排除外部链接和非新闻页面
            excluded_domains = ['baidu.com', 'sina.com', 'qq.com', 'sohu.com', 'ifeng.com',
                               'douban.com', 'weibo.com', 'zhihu.com', 'toutiao.com', 'hao.163.com']
            if any(ex in full_url for ex in excluded_domains):
                continue
            
            # 严格检查URL必须是 www.163.com/news/ 或 www.163.com/article/ 开头
            # 或者以 /domestic、/world、/society、/air 等分类路径开头
            # 或者来自 tech.sports.ent.money.game 等子域名
            if not re.search(r'''
                (?:www\.163\.com/(?:news|article)/)    # www.163.com/news/ 或 article/
                |(?:news\.163\.com/(?:domestic|world|society|air|guonei|guoji|shehui|war|tech|sports|ent|money))
                |(?:163\.com/news/)
                |(?:m\.163\.com/news/)                 # 移动端
                |(?:(?:tech|sports|ent|money|game|edu|travel|auto|house|food|health|baby)\.163\.com/news/)  # 垂直频道
            ''', full_url, re.IGNORECASE | re.VERBOSE):
                continue

            if full_url not in seen_urls:
                seen_urls.add(full_url)
                article_urls.append(full_url)

        return article_urls

    def fetch_article_list(self, url: str) -> List[str]:
        """
        获取文章列表页中所有文章链接

        Args:
            url: 列表页URL

        Returns:
            文章URL列表
        """
        # 使用增强的滚动深度（从默认3次增加到5次）
        html = self.fetch_page(url, wait_time=3.0, scroll_count=5)
        if not html:
            logger.error(f"无法获取页面: {url}")
            return []

        article_urls = self.extract_article_urls(html, url)

        if not article_urls:
            # 调试：打印页面中的一些链接
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')
            all_links = [link.get('href', '') for link in soup.find_all('a', href=True) if link.get('href')]
            logger.warning(f"未能从 {url} 提取到文章链接。页面中前 20 个链接如下:")
            for i, link in enumerate(all_links[:20]):
                logger.warning(f"  [{i+1}] {link}")

        logger.info(f"从 {url} 提取到 {len(article_urls)} 篇文章URL")
        return article_urls

    def fetch_article_content(self, url: str) -> Optional[Dict]:
        """
        获取单篇文章详情

        Args:
            url: 文章URL

        Returns:
            文章信息字典
        """
        # 使用Selenium获取详情页
        html = self.fetch_page(url, wait_time=2.0, scroll_count=1)
        if not html:
            return None

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'lxml')

        # 检测404页面
        page_title = soup.title.string.strip() if soup.title else ""
        if '404' in page_title or '页面未找到' in page_title:
            logger.warning(f"页面返回404: {url}")
            return None

        # 提取标题
        title = ""
        if soup.title:
            title = soup.title.string.strip()
        else:
            h1 = soup.select_one('h1')
            if h1:
                title = h1.get_text(strip=True)

        # 清理标题中的特殊字符
        if title:
            title = re.sub(r'[|_网易]', '', title).strip()
            # 如果标题变成空或太短，可能不是有效文章
            if len(title) < 5:
                logger.warning(f"标题太短，可能是无效页面: {url}, title={title}")
                return None

        # 提取正文 - 尝试多种选择器
        content = ""
        
        # 正文选择器列表（按优先级排序）
        content_selectors = [
            '#endText',           # 网易新闻标准正文容器
            '.endText',           # 类名选择器
            '.post_text',         # 另一种正文容器
            '.article-content',   # 通用文章内容
            '.news-content',      # 新闻内容
            '.post-body',         # 文章正文
            '.content-body',      # 内容主体
            '[class*=endText]',   # 包含endText的类
            '[class*=article-content]', # 包含article-content的类
            '[class*=post_text]',     # 包含post_text的类
            '.tie-content',       # 跟帖内容区域
            '.js-article-content',    # JS动态加载的内容
        ]
        
        for selector in content_selectors:
            content_node = soup.select_one(selector)
            if content_node:
                # 清理脚本和样式
                for script in content_node(['script', 'style', 'nav', 'footer', 'iframe']):
                    script.decompose()
                # 提取文本
                content = content_node.get_text(separator='\n').strip()
                # 清理多余空白
                content = re.sub(r'\n{3,}', '\n\n', content)
                if content and len(content) > 50:
                    logger.debug(f"使用选择器 '{selector}' 成功提取正文，长度: {len(content)}")
                    break
        
        # 如果仍然没有找到正文，尝试从整个页面提取
        if not content or len(content) < 50:
            # 查找主内容区域
            main_content = soup.select_one('main, #main, .main, article, .article, .content, #content, .post')
            if main_content:
                for script in main_content(['script', 'style', 'nav', 'footer', 'iframe', 'aside', 'header']):
                    script.decompose()
                content = main_content.get_text(separator='\n').strip()
                content = re.sub(r'\n{3,}', '\n\n', content)
                logger.debug(f"从主内容区域提取正文，长度: {len(content)}")

        # 如果正文太短，记录警告
        if content and len(content) < 100:
            logger.debug(f"正文较短: {url}, content_length={len(content)}")
        elif not content:
            logger.warning(f"未能提取到正文: {url}")

        # 提取发布时间
        publish_date = None
        date_node = soup.select_one('html#ne_wrap')
        if date_node:
            pub_raw = date_node.get("data-publishtime")
            if pub_raw:
                publish_date = pub_raw

        # 如果没有找到发布日期，尝试其他方式
        if not publish_date:
            # 尝试从meta标签获取
            time_node = soup.select_one('meta[property="article:published_time"]')
            if time_node:
                publish_date = time_node.get("content")
        
        # 尝试从其他元素获取时间
        if not publish_date:
            time_patterns = [
                'meta[name="publishdate"]',
                'meta[property="og:published_time"]',
                '.publish-time',
                '.post-time',
                '.article-time',
                '[class*=time]',
            ]
            for selector in time_patterns:
                time_node = soup.select_one(selector)
                if time_node:
                    pub_raw = time_node.get("content") or time_node.get_text(strip=True)
                    if pub_raw:
                        publish_date = pub_raw
                        break

        # 提取作者
        author = ""
        author_selectors = ['.ep-editor', '.author', '.editor', '[class*=author]', '.post-author']
        for selector in author_selectors:
            author_node = soup.select_one(selector)
            if author_node:
                author = author_node.get_text(strip=True)
                if author:
                    break

        # 提取关键词
        keywords = []
        keywords_node = soup.select_one('meta[name="keywords"]')
        if keywords_node:
            keywords_str = keywords_node.get("content", "")
            keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]

        return {
            'url': url,
            'title': title,
            'content': content,
            'publish_date': publish_date,
            'author': author,
            'keywords': keywords
        }

