"""国内新闻爬虫模块

支持 py_scrapers 的爬虫运行，数据统一存储到 MySQL
"""

import logging

from .sina import SinaScraper
from .netease import NeteaseScraper
from .chinanews import ChinaNewsScraper
from .tencent import TencentScraper
from .ifeng import IfengScraper
from .pengpai import PengpaiScraper
from .cankaoxiaoxi import CankaoxiaoxiScraper
from .xinhua import XinhuaScraper, XinhuaChannelDiscoverScraper


# 爬虫类映射
logger = logging.getLogger(__name__)

SCRAPER_CLASSES = {
    'sina': SinaScraper,
    'netease': NeteaseScraper,
    'chinanews': ChinaNewsScraper,
    # 新增新闻门户爬虫
    'tencent': TencentScraper,
    'ifeng': IfengScraper,
    'pengpai': PengpaiScraper,
    'cankaoxiaoxi': CankaoxiaoxiScraper,
    'xinhua': XinhuaScraper,
    'xinhua_discover': XinhuaChannelDiscoverScraper,
}


def create_spider(name: str, config: dict, db) -> object:
    """
    创建指定名称的爬虫实例

    Args:
        name: 爬虫名称 (sina, netease)
        config: 爬虫配置
        db: 数据库处理器

    Returns:
        对应爬虫实例
    """
    name = name.lower()

    logger.info("创建国内爬虫: %s", name)
    logger.debug("可用爬虫: %s", list(SCRAPER_CLASSES.keys()))

    if name not in SCRAPER_CLASSES:
        logger.error("未知爬虫: %s", name)
        return None

    scraper_class = SCRAPER_CLASSES[name]
    logger.info("创建 %s 实例", scraper_class.__name__)
    return scraper_class(config, db)
