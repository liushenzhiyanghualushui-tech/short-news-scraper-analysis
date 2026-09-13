"""UC新闻 代理IP池管理"""
import logging
import random
import time
from typing import List, Optional
import requests
import re

logger = logging.getLogger(__name__)


class UCProxyPool:
    """UC新闻 代理IP池管理"""

    def __init__(self, proxy_apis: List[str] = None, proxies: List[str] = None,
                 enable_rotation: bool = True, refresh_interval: int = 300):
        """
        初始化代理池

        Args:
            proxy_apis: 代理API列表
            proxies: 固定代理列表
            enable_rotation: 是否启用代理轮换
            refresh_interval: 代理刷新间隔（秒）
        """
        self.proxy_apis = proxy_apis or []
        self.fixed_proxies = proxies or []
        self.enable_rotation = enable_rotation
        self.refresh_interval = refresh_interval
        self.current_proxy_index = 0
        self.last_refresh_time = 0
        self.failed_proxies = set()

        # 初始化时尝试获取代理
        if self.enable_rotation and self.proxy_apis:
            self._refresh_proxies()

    def get_proxy(self) -> Optional[str]:
        """获取可用代理"""
        # 检查是否需要刷新代理列表
        current_time = time.time()
        if (self.enable_rotation and
            current_time - self.last_refresh_time > self.refresh_interval):
            self._refresh_proxies()
            self.last_refresh_time = current_time

        # 获取可用代理列表
        available_proxies = self._get_available_proxies()

        if not available_proxies:
            return None

        # 轮换选择代理
        proxy = available_proxies[self.current_proxy_index % len(available_proxies)]
        self.current_proxy_index += 1

        return proxy

    def _get_available_proxies(self) -> List[str]:
        """获取可用代理列表"""
        all_proxies = self.fixed_proxies.copy()
        # 排除失败的代理
        return [p for p in all_proxies if p not in self.failed_proxies]

    def mark_failed(self, proxy: str):
        """标记代理失败"""
        self.failed_proxies.add(proxy)
        logger.warning(f"代理 {proxy} 已标记为不可用")

        # 如果某个代理连续失败太多次，从列表中移除
        if len(self.failed_proxies) > len(self.fixed_proxies) * 0.5:
            logger.warning("超过50%的代理失败，尝试刷新代理列表")
            self._refresh_proxies()

    def _refresh_proxies(self):
        """从API刷新代理列表"""
        if not self.proxy_apis:
            return

        for api_url in self.proxy_apis:
            try:
                logger.info(f"从API获取代理: {api_url}")
                response = requests.get(api_url, timeout=10)

                if response.status_code == 200:
                    # 解析代理列表（根据不同API格式）
                    content = response.text.strip()

                    # 尝试解析为一行一个代理的格式
                    if '\n' in content:
                        new_proxies = [line.strip() for line in content.split('\n') if line.strip()]
                        # 只保留有效的代理格式
                        new_proxies = [p for p in new_proxies if self._is_valid_proxy(p)]

                        if new_proxies:
                            # 只保留最新的50个代理
                            self.fixed_proxies = new_proxies[:50]
                            self.failed_proxies.clear()  # 清除失败记录
                            logger.info(f"从 {api_url} 获取到 {len(new_proxies)} 个代理")
                            return  # 成功获取后退出

            except Exception as e:
                logger.warning(f"从API获取代理失败 {api_url}: {e}")

    def _is_valid_proxy(self, proxy: str) -> bool:
        """验证代理格式是否有效"""
        # 匹配 http://ip:port 或 ip:port 格式
        pattern = r'^https?://[\d.]+:\d+$'
        return bool(re.match(pattern, proxy))

    def get_random_proxy(self) -> Optional[str]:
        """随机获取一个可用代理（备用方法）"""
        available = self._get_available_proxies()
        if not available:
            return None
        return random.choice(available)

    def get_all_proxies(self) -> List[str]:
        """获取所有可用代理"""
        return self._get_available_proxies()

    def add_proxy(self, proxy: str):
        """添加新的代理到池中"""
        if self._is_valid_proxy(proxy) and proxy not in self.fixed_proxies:
            self.fixed_proxies.append(proxy)
            logger.info(f"添加新代理: {proxy}")

    def clear_failed(self):
        """清空失败的代理记录"""
        self.failed_proxies.clear()
        logger.info("已清空失败的代理记录")

