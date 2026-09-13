"""凤凰新闻爬虫 - 适配 short_new 的 MySQL"""

import json
import logging
import random
import re
import threading
import time
from collections import Counter
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import SSLError
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

from ..base import BaseScraper
from ..models import DomesticNewsItem, RawArticleItem


class _DomainThrottler:
    def __init__(self, min_interval: float = 0.5, enable_jitter: bool = True, jitter_range: tuple = (0.7, 1.3)):
        self.min_interval = float(min_interval)
        self.enable_jitter = bool(enable_jitter)
        self.jitter_range = jitter_range
        self._last_request_time: Dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, domain: str):
        if not domain:
            domain = "default"
        with self._lock:
            now = time.time()
            last = self._last_request_time.get(domain, 0.0)
            interval = self.min_interval
            if self.enable_jitter:
                interval *= random.uniform(*self.jitter_range)
            next_allowed = max(now, last) + interval
            sleep_s = max(0.0, next_allowed - now)
            self._last_request_time[domain] = next_allowed
        if sleep_s > 0:
            time.sleep(sleep_s)


class IfengScraper(BaseScraper):
    """凤凰新闻爬虫"""

    def __init__(self, config: dict, db_handler):
        super().__init__(config, db_handler)
        self.source_name = "凤凰新闻"
        self.source_code = "ifeng"
        self.seed_url = "https://news.ifeng.com/"

        self.source_settings = self._resolve_source_settings(config)
        self.concurrency = int(self.source_settings.get("concurrency", 10))
        self.max_items = int(self.source_settings.get("max_items", 3000))
        self.exclude_domains = set(self.source_settings.get("exclude_domains", []) or [])
        # 默认排除的非新闻子域名
        default_exclude = {"biz", "mall", "shop", "yc", "phtv", "a", "auto", "car", "live", "v"}
        self.exclude_domains.update(default_exclude)
        
        self.deny_url_keywords = list(self.source_settings.get("deny_url_keywords", []) or [])
        if not self.deny_url_keywords:
            self.deny_url_keywords = [
                "listpage",
                "/search/",
                "/special/",
                "/c/special/",
                "/homedetail/",
                "/daogou/",
                "/video/",
                "/live/",
                "ulive.",
                "zhibo.",
                "v.ifeng.com",
                "view.html",
                "/ask/",
                "/topic/",
                "/subject/",
            ]
        self.min_request_interval = float(self.source_settings.get("min_request_interval", 0.2))
        self.max_failures_per_domain = int(self.source_settings.get("max_failures_per_domain", 10))
        self.listpage_enabled = bool(self.source_settings.get("listpage_enabled", True))
        self.listpage_max_pages = int(self.source_settings.get("listpage_max_pages", 200))
        self.listpage_seed_limit = int(self.source_settings.get("listpage_seed_limit", 50))
        self.shanklist_enabled = bool(self.source_settings.get("shanklist_enabled", True))
        self.shanklist_seed_limit = int(self.source_settings.get("shanklist_seed_limit", 300))
        self.discovery_enabled = bool(self.source_settings.get("discovery_enabled", True))
        self.discovery_max_pages = int(self.source_settings.get("discovery_max_pages", 200))
        self.discovery_queue_limit = int(self.source_settings.get("discovery_queue_limit", 500))
        self._domain_failures = Counter()
        self._disabled_domains = set()
        self._domain_throttler = _DomainThrottler(min_interval=self.min_request_interval, enable_jitter=True)
        self._domain_state_lock = threading.Lock()
        
        # 初始化 Session 并配置重试策略
        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=frozenset(['GET', 'POST']),
            raise_on_status=False,
            respect_retry_after_header=True
        )
        # 适配器
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)
        
        # 设置通用 Headers
        self.session.headers.update({
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
            "Referer": "https://news.ifeng.com/"
        })

    def _resolve_source_settings(self, config: dict) -> Dict:
        domestic_conf = config.get("domestic_news", {})
        if isinstance(domestic_conf, dict):
            sources = domestic_conf.get("sources", [])
            if isinstance(sources, list):
                for s in sources:
                    if isinstance(s, dict) and s.get("name") == self.source_code:
                        return dict(s)
        return {}

    def get_headers(self) -> Dict[str, str]:
        """获取请求头（保留方法以兼容基类或其他调用，但主要使用 session）"""
        return dict(self.session.headers)

    def _normalize_url(self, href: str, base_url: str) -> Optional[str]:
        if not href:
            return None
        href = href.strip()
        if href.startswith("//"):
            href = "https:" + href
        if href.startswith("/"):
            href = urljoin(base_url, href)
        if not href.startswith("http://") and not href.startswith("https://"):
            return None

        parsed = urlparse(href)
        if parsed.scheme == "http" and parsed.netloc.endswith("ifeng.com"):
            parsed = parsed._replace(scheme="https")

        if parsed.path.endswith("/view.html"):
            qs = parse_qs(parsed.query or "")
            pc_urls = qs.get("pcUrl") or qs.get("pcurl") or []
            if pc_urls:
                return self._normalize_url(pc_urls[0], base_url)

        normalized = parsed._replace(fragment="")
        return normalized.geturl()

    def _is_candidate_article_url(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
        except Exception:
            return False
        if not parsed.netloc or not parsed.netloc.endswith("ifeng.com"):
            return False
        netloc = parsed.netloc.lower()
        if netloc in self.exclude_domains or any(netloc.endswith("." + d.lower()) for d in self.exclude_domains):
            return False
        if netloc in self._disabled_domains:
            return False

        raw = url.lower()
        for kw in self.deny_url_keywords:
            if kw and kw.lower() in raw:
                return False

        path = (parsed.path or "").lower()
        if "/mediashare/" in path:
            return True
        if "/c/" in path:
            return True
        if path.endswith(".shtml"):
            return True
        return False

    def _is_listpage_url(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
        except Exception:
            return False
        if not parsed.netloc or not parsed.netloc.endswith("ifeng.com"):
            return False
        if "/listpage/" not in (parsed.path or "").lower():
            return False
        if not parsed.path.lower().endswith(("list.shtml", "spelist.shtml")):
            return False
        netloc = parsed.netloc.lower()
        if netloc in self.exclude_domains or any(netloc.endswith("." + d.lower()) for d in self.exclude_domains):
            return False
        return True

    def _is_shanklist_url(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
        except Exception:
            return False
        if not parsed.netloc or not parsed.netloc.endswith("ifeng.com"):
            return False
        netloc = parsed.netloc.lower()
        if netloc in self.exclude_domains or any(netloc.endswith("." + d.lower()) for d in self.exclude_domains):
            return False
        path = (parsed.path or "").lower()
        if "/shanklist/" not in path:
            return False
        return True

    def _is_discovery_url(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
        except Exception:
            return False
        if not parsed.netloc or not parsed.netloc.endswith("ifeng.com"):
            return False
        netloc = parsed.netloc.lower()
        if netloc in self.exclude_domains or any(netloc.endswith("." + d.lower()) for d in self.exclude_domains):
            return False
        if netloc in self._disabled_domains:
            return False
        raw = url.lower()
        for kw in self.deny_url_keywords:
            if kw and kw.lower() in raw:
                return False
        path = (parsed.path or "").lower()
        if path.endswith((".jpg", ".png", ".gif", ".jpeg", ".webp", ".svg", ".css", ".js", ".pdf", ".zip", ".rar")):
            return False
        if self._is_candidate_article_url(url):
            return False
        return True

    def _iter_listpage(self, seed_url: str, max_pages: int) -> List[str]:
        with_page_pattern = re.compile(
            r"^(https?://[^/]+/listpage/.+?)/(\d+)/(list\\.shtml|spelist\\.shtml)$", re.IGNORECASE
        )
        without_page_pattern = re.compile(
            r"^(https?://[^/]+/listpage/.+?)/(list\\.shtml|spelist\\.shtml)$", re.IGNORECASE
        )
        m = with_page_pattern.match(seed_url)
        if m:
            prefix = m.group(1)
            tail = m.group(3)
        else:
            m2 = without_page_pattern.match(seed_url)
            if not m2:
                return []
            prefix = m2.group(1)
            tail = m2.group(2)
        urls: List[str] = []
        for page in range(1, max_pages + 1):
            urls.append(f"{prefix}/{page}/{tail}")
        return urls

    def _fetch_listpage_articles(self, seed_url: str, target_count: int) -> List[str]:
        collected: List[str] = []
        for page_url in self._iter_listpage(seed_url, self.listpage_max_pages):
            resp = self._request(page_url, timeout=self.timeout)
            if resp is None:
                page_netloc = (urlparse(page_url).netloc or "").lower()
                if page_netloc in self._disabled_domains:
                    break
                continue
            if resp.status_code == 404:
                break
            if resp.status_code != 200:
                page_netloc = (urlparse(page_url).netloc or "").lower()
                if page_netloc in self._disabled_domains:
                    break
                continue

            soup = BeautifulSoup(resp.text, "lxml")
            page_new: List[str] = []
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                normalized = self._normalize_url(href, page_url)
                if not normalized:
                    continue
                if self._is_candidate_article_url(normalized):
                    if normalized not in collected and normalized not in page_new:
                        page_new.append(normalized)
            if page_new:
                collected.extend(page_new)
            if len(collected) >= target_count:
                break
        return collected

    def _fetch_shanklist(self, seed_url: str, target_count: int) -> tuple[List[str], List[str]]:
        resp = self._request(seed_url, timeout=self.timeout)
        if resp is None or resp.status_code != 200:
            return ([], [])
        soup = BeautifulSoup(resp.text, "lxml")

        articles: List[str] = []
        shank_seeds: List[str] = []

        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            normalized = self._normalize_url(href, seed_url)
            if not normalized:
                continue
            if self.shanklist_enabled and self._is_shanklist_url(normalized):
                if len(shank_seeds) < self.shanklist_seed_limit and normalized not in shank_seeds:
                    shank_seeds.append(normalized)
                continue
            if self._is_candidate_article_url(normalized):
                if normalized not in articles:
                    articles.append(normalized)
                    if len(articles) >= target_count:
                        break

        return (articles, shank_seeds)

    def _request(self, url: str, timeout: Optional[float] = None) -> Optional[requests.Response]:
        parsed = urlparse(url)
        netloc = (parsed.netloc or "").lower()
        if not netloc:
            return None
        if netloc in self.exclude_domains or any(netloc.endswith("." + d.lower()) for d in self.exclude_domains):
            return None
        if netloc in self._disabled_domains:
            return None

        self._domain_throttler.wait(netloc)

        headers = dict(self.session.headers)
        headers["User-Agent"] = random.choice(self.user_agents)
        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

        try:
            resp = self.session.get(url, timeout=timeout or self.timeout, headers=headers, allow_redirects=True)
        except (requests.Timeout, requests.ConnectionError, SSLError) as e:
            self._record_domain_failure(netloc)
            self.logger.warning(f"请求异常: {url} - {e}")
            return None
        except Exception as e:
            self._record_domain_failure(netloc)
            self.logger.warning(f"请求异常: {url} - {e}")
            return None

        if resp.status_code == 200:
            self._reset_domain_failures(netloc)
            return resp

        if resp.status_code in (429, 500, 502, 503, 504, 520, 521, 522, 524):
            failures = self._record_domain_failure(netloc)
            if failures >= self.max_failures_per_domain:
                self.logger.warning(f"域名失败次数过多，已跳过本轮剩余请求: {netloc}")
            if resp.status_code == 429:
                time.sleep(min(60.0, 2.0 ** min(failures, 6)))
        return resp

    def _record_domain_failure(self, netloc: str) -> int:
        with self._domain_state_lock:
            self._domain_failures[netloc] += 1
            failures = int(self._domain_failures[netloc])
            if failures >= self.max_failures_per_domain:
                self._disabled_domains.add(netloc)
        return failures

    def _reset_domain_failures(self, netloc: str):
        with self._domain_state_lock:
            if netloc in self._domain_failures:
                self._domain_failures[netloc] = 0

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
            article_urls = self.fetch_article_list()
            self.logger.info(f"获取到 {len(article_urls)} 篇文章URL")

            count = 0
            max_workers = self.concurrency
            self.logger.info(f"使用并发数: {max_workers}")
            
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任务
                future_to_url = {executor.submit(self.process_article, url): url for url in article_urls}
                
                # 处理完成的任务
                for future in concurrent.futures.as_completed(future_to_url):
                    url = future_to_url[future]
                    try:
                        success = future.result()
                        if success:
                            count += 1
                    except Exception as e:
                        self.logger.error(f"处理文章失败 {url}: {e}")

            if self._disabled_domains:
                disabled_preview = ", ".join(sorted(self._disabled_domains)[:10])
                self.logger.info(f"本轮已熔断域名: {disabled_preview}")
            failure_items = [(d, c) for d, c in self._domain_failures.items() if int(c) > 0]
            if failure_items:
                top = sorted(failure_items, key=lambda x: x[1], reverse=True)[:10]
                top_text = ", ".join([f"{d}={c}" for d, c in top])
                self.logger.info(f"本轮域名失败统计(Top10): {top_text}")

            self.logger.info(f"{self.source_name} 爬取完成，共保存 {count} 条")
            return count
        except Exception as e:
            self.logger.error(f"{self.source_name} 爬取出错: {e}")
            import traceback
            traceback.print_exc()
            return 0

    def process_article(self, url: str) -> bool:
        """处理单篇文章：抓取、保存、延时"""
        try:
            # 随机延时，减轻服务器压力
            self.random_delay()
            
            article = self.fetch_article(url)
            if article and self.save_article(article):
                return True
            return False
        except Exception as e:
            self.logger.error(f"处理文章异常 {url}: {e}")
            return False

    def fetch_article_list(self) -> List[str]:
        """获取文章列表页（支持多页面分页爬取）"""
        urls = []
        listpage_seeds: List[str] = []
        shanklist_seeds: List[str] = []
        # 定义要爬取的分页URL列表 - 扩充更多频道以增加覆盖面
        page_urls = [
            "https://news.ifeng.com/",  # 首页
            "https://finance.ifeng.com/",  # 财经
            "https://ent.ifeng.com/",  # 娱乐
            "https://tech.ifeng.com/",  # 科技
            "https://sports.ifeng.com/",  # 体育
            "https://auto.ifeng.com/",  # 汽车
            "https://house.ifeng.com/",  # 房产
            "https://mil.ifeng.com/",  # 军事
            "https://fashion.ifeng.com/", # 时尚
            "https://travel.ifeng.com/", # 旅游
            "https://culture.ifeng.com/", # 文化
            "https://gongyi.ifeng.com/", # 公益
            "https://health.ifeng.com/", # 健康
            "https://food.ifeng.com/", # 美食
            "https://home.ifeng.com/", # 家居
            "https://edu.ifeng.com/",  # 教育
            "https://fo.ifeng.com/",  # 佛教
            "https://guoxue.ifeng.com/",  # 国学
            "https://jiu.ifeng.com/",  # 酒业
            "https://ishare.ifeng.com/",  # 凤凰号/媒体号聚合
        ]

        try:
            for page_url in page_urls:
                # 检查最大数量限制
                if len(urls) >= self.max_items + 200:
                    break

                try:
                    page_netloc = (urlparse(page_url).netloc or "").lower()
                    if page_netloc and (page_netloc in self.exclude_domains or any(page_netloc.endswith("." + d.lower()) for d in self.exclude_domains)):
                        self.logger.info(f"跳过频道（已排除域名）: {page_url}")
                        continue
                    response = self._request(page_url, timeout=self.timeout)
                    if response is None:
                        continue
                    if response.status_code != 200:
                        self.logger.debug(f"请求失败: 状态码 {response.status_code} - {page_url}")
                        continue

                    soup = BeautifulSoup(response.content, 'lxml')

                    if self.listpage_enabled and len(listpage_seeds) < self.listpage_seed_limit:
                        for m in re.findall(
                            r"(?:https?:)?//[a-zA-Z0-9\\.-]+\\.ifeng\\.com/listpage/[^\\s\"']+?(?:list\\.shtml|spelist\\.shtml)",
                            response.text,
                        ):
                            if len(listpage_seeds) >= self.listpage_seed_limit:
                                break
                            normalized_seed = self._normalize_url(m, page_url)
                            if normalized_seed and self._is_listpage_url(normalized_seed) and normalized_seed not in listpage_seeds:
                                listpage_seeds.append(normalized_seed)

                    if self.shanklist_enabled and len(shanklist_seeds) < self.shanklist_seed_limit:
                        for m in re.findall(
                            r"(?:https?:)?//[a-zA-Z0-9\\.-]+\\.ifeng\\.com/shanklist/[^\\s\"']+",
                            response.text,
                        ):
                            if len(shanklist_seeds) >= self.shanklist_seed_limit:
                                break
                            normalized_seed = self._normalize_url(m, page_url)
                            if normalized_seed and self._is_shanklist_url(normalized_seed) and normalized_seed not in shanklist_seeds:
                                shanklist_seeds.append(normalized_seed)

                    # 提取文章链接
                    new_urls: List[str] = []
                    for link in soup.find_all('a', href=True):
                        href = link.get("href", "")
                        normalized = self._normalize_url(href, page_url)
                        if not normalized:
                            continue
                        if self.listpage_enabled and self._is_listpage_url(normalized):
                            if len(listpage_seeds) < self.listpage_seed_limit and normalized not in listpage_seeds:
                                listpage_seeds.append(normalized)
                            continue
                        if self.shanklist_enabled and self._is_shanklist_url(normalized):
                            if len(shanklist_seeds) < self.shanklist_seed_limit and normalized not in shanklist_seeds:
                                shanklist_seeds.append(normalized)
                            continue
                        if not self._is_candidate_article_url(normalized):
                            continue
                        if normalized not in urls and normalized not in new_urls:
                            new_urls.append(normalized)

                    self.logger.info(f"从 {page_url} 获取到 {len(new_urls)} 篇文章URL")
                    urls.extend(new_urls)

                    # 请求间隔
                    time.sleep(random.uniform(1.0, 2.0))

                except requests.Timeout:
                    self.logger.error(f"获取文章列表超时: {page_url}")
                except requests.ConnectionError as e:
                    self.logger.error(f"获取文章列表连接失败: {e}")
                except Exception as e:
                    self.logger.error(f"获取文章列表失败 {page_url}: {e}")

            # 去重并限制数量
            urls = list(dict.fromkeys(urls))
            if self.listpage_enabled and len(urls) < self.max_items and listpage_seeds:
                seed_preview = ", ".join(listpage_seeds[:5])
                self.logger.info(f"发现 {len(listpage_seeds)} 个 listpage 种子，开始翻页扩量: {seed_preview}")
                for seed in listpage_seeds:
                    if len(urls) >= self.max_items + 200:
                        break
                    seed_netloc = (urlparse(seed).netloc or "").lower()
                    if seed_netloc in self._disabled_domains:
                        continue
                    fetched = self._fetch_listpage_articles(seed, target_count=max(50, self.max_items + 200 - len(urls)))
                    for u in fetched:
                        if u not in urls:
                            urls.append(u)
                            if len(urls) >= self.max_items + 200:
                                break

            urls = list(dict.fromkeys(urls))
            if self.shanklist_enabled and len(urls) < self.max_items:
                seed_queue = list(dict.fromkeys(shanklist_seeds))
                seen_seed = set(seed_queue)
                if seed_queue:
                    seed_preview = ", ".join(seed_queue[:5])
                    self.logger.info(f"发现 {len(seed_queue)} 个 shanklist 种子，开始扩量: {seed_preview}")

                while seed_queue and len(urls) < self.max_items + 200 and len(seen_seed) <= self.shanklist_seed_limit:
                    seed = seed_queue.pop(0)
                    seed_netloc = (urlparse(seed).netloc or "").lower()
                    if seed_netloc in self._disabled_domains:
                        continue
                    articles, new_seeds = self._fetch_shanklist(seed, target_count=max(50, self.max_items + 200 - len(urls)))
                    for u in articles:
                        if u not in urls:
                            urls.append(u)
                            if len(urls) >= self.max_items + 200:
                                break
                    for s in new_seeds:
                        if len(seen_seed) >= self.shanklist_seed_limit:
                            break
                        if s not in seen_seed:
                            seen_seed.add(s)
                            seed_queue.append(s)

            urls = list(dict.fromkeys(urls))
            if self.discovery_enabled and len(urls) < self.max_items:
                discovery_queue: List[str] = []
                discovery_seen = set()
                for u in page_urls:
                    discovery_queue.append(u)
                    discovery_seen.add(u)
                for u in shanklist_seeds:
                    if u not in discovery_seen:
                        discovery_queue.append(u)
                        discovery_seen.add(u)

                fetched_pages = 0
                while discovery_queue and len(urls) < self.max_items + 200 and fetched_pages < self.discovery_max_pages:
                    current = discovery_queue.pop(0)
                    cur_netloc = (urlparse(current).netloc or "").lower()
                    if cur_netloc in self._disabled_domains:
                        continue
                    resp = self._request(current, timeout=self.timeout)
                    fetched_pages += 1
                    if resp is None or resp.status_code != 200:
                        continue
                    soup = BeautifulSoup(resp.text, "lxml")
                    for link in soup.find_all("a", href=True):
                        href = link.get("href", "")
                        normalized = self._normalize_url(href, current)
                        if not normalized:
                            continue
                        if self._is_candidate_article_url(normalized):
                            if normalized not in urls:
                                urls.append(normalized)
                                if len(urls) >= self.max_items + 200:
                                    break
                        elif len(discovery_seen) < self.discovery_queue_limit and self._is_discovery_url(normalized):
                            if normalized not in discovery_seen:
                                discovery_seen.add(normalized)
                                discovery_queue.append(normalized)
                    if fetched_pages % 20 == 0:
                        self.logger.info(f"发现式扩量进度: 已抓页面 {fetched_pages}/{self.discovery_max_pages}, 候选URL {len(urls)}")

            urls = list(dict.fromkeys(urls))
            if len(urls) > self.max_items:
                urls = urls[:self.max_items]
                
            self.logger.info(f"去重后共获取到 {len(urls)} 篇文章URL")

        except Exception as e:
            self.logger.error(f"获取文章列表过程中发生错误: {e}")

        return urls

    def fetch_article(self, url: str) -> Optional[Dict]:
        """获取单篇文章详情"""
        try:
            response = self._request(url, timeout=self.timeout)
            if response is None:
                return None

            if response.status_code != 200:
                self.logger.error(f"请求失败: {url} 状态码: {response.status_code}")
                return None
                
            # 处理编码问题，凤凰网部分老页面可能是 gbk
            head = response.content[:4096].decode("latin1", errors="ignore").lower()
            if 'charset=gb2312' in head or 'charset=gbk' in head:
                response.encoding = 'gbk'
            else:
                response.encoding = response.encoding or 'utf-8'

            soup = BeautifulSoup(response.text, 'lxml')

            # 提取标题
            title = ""
            title_node = soup.select_one('h1, .title-article, .ph_hd h1, .essay-title, .headline, #title, .news-title, h2.tit')
            if title_node:
                title = self.clean_text(title_node.get_text())
            if not title and soup.title:
                title = soup.title.string.strip() if soup.title.string else ""

            # 增强标题提取：针对移动端页面或特殊模板
            if not title:
                meta_title = soup.select_one('meta[property="og:title"]')
                if meta_title:
                    title = meta_title.get("content", "")

            # 提取作者
            author = ""
            author_node = soup.select_one('.author, .source, .editor, .writer, [class*="author"]')
            if author_node:
                author = author_node.get_text(strip=True)

            # 提取正文
            content = ""
            content_node = soup.select_one('.article-content, .text, .essay-box, #content, article, [class*="detail_text"], .js_selection_area')
            if content_node:
                for script in content_node(['script', 'style', 'nav', 'footer', 'iframe']):
                    script.decompose()
                content = self.clean_text(content_node.get_text(separator='\n'))
            
            # 如果没找到正文，尝试更通用的查找
            if not content or len(content) < 50:
                paragraphs = soup.find_all('p')
                # 找出包含长文本的段落
                text_content = []
                for p in paragraphs:
                    if p.get_text(strip=True):
                        text_content.append(p.get_text(strip=True))
                if len(text_content) > 5: # 至少有5段
                    content = "\n".join(text_content)

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
            
            # 尝试从 script 中提取时间 (凤凰网常用)
            if not publish_date:
                scripts = soup.find_all('script')
                for script in scripts:
                    if script.string and '"pubDate":' in script.string:
                        import re
                        match = re.search(r'"pubDate":\s*"([^"]+)"', script.string)
                        if match:
                            publish_date = self.try_parse_date(match.group(1))
                            break

            # 提取描述
            description = ""
            desc_node = soup.select_one('meta[name="description"]')
            if desc_node:
                description = desc_node.get("content", "")

            return {
                'url': url,
                'title': title,
                'author': author or "凤凰新闻",
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
