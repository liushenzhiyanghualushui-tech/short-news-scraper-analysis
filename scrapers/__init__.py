"""
爬虫模块初始化

提供各类爬虫的创建和获取功能：
- 国内新闻爬虫
"""

from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)


def get_domestic_scrapers() -> List[Dict[str, Any]]:
    """
    获取所有可用的国内新闻爬虫配置

    Returns:
        List[Dict]: 爬虫配置列表
    """
    return [
        {"name": "sina", "description": "新浪新闻"},
        {"name": "netease", "description": "网易新闻"},
        {"name": "chinanews", "description": "中新网"},
        # 新闻门户爬虫（归类为国内新闻）
        {"name": "tencent", "description": "腾讯新闻"},
        {"name": "ifeng", "description": "凤凰新闻"},
        {"name": "pengpai", "description": "澎湃新闻"},
        {"name": "cankaoxiaoxi", "description": "参考消息"},
        {"name": "xinhua", "description": "新华网"},
    ]


def create_spider(name: str, config: dict, db_handler) -> object:
    """
    创建指定名称的爬虫实例

    Args:
        name: 爬虫名称
        config: 配置字典
        db_handler: 数据库处理器

    Returns:
        爬虫实例，如果未找到返回 None
    """
    # 国内新闻爬虫
    domestic_spiders = {
        'sina': ('scrapers.domestic', 'SinaSpider'),
        'netease': ('scrapers.domestic', 'NeteaseSpider'),
        'chinanews': ('scrapers.domestic', 'ChinaNewsScraper'),
        # 新闻门户爬虫（归类为国内新闻）
        'tencent': ('scrapers.domestic', 'TencentScraper'),
        'ifeng': ('scrapers.domestic', 'IfengScraper'),
        'pengpai': ('scrapers.domestic', 'PengpaiScraper'),
        'cankaoxiaoxi': ('scrapers.domestic', 'CankaoxiaoxiScraper'),
        'xinhua': ('scrapers.domestic', 'XinhuaScraper'),
    }

    if name not in domestic_spiders:
        logger.error(f"未知爬虫: {name}")
        return None

    try:
        module_path, class_name = domestic_spiders[name]
        # 动态导入模块和类
        import importlib
        module = importlib.import_module(module_path)
        spider_class = getattr(module, class_name)
        return spider_class(config, db_handler)
    except Exception as e:
        logger.error(f"创建爬虫 {name} 失败: {e}")
        return None


def run_spider(name: str, config: dict, db_handler) -> int:
    """
    运行指定名称的爬虫

    Args:
        name: 爬虫名称
        config: 配置字典
        db_handler: 数据库处理器

    Returns:
        int: 采集的数据条数
    """
    spider = create_spider(name, config, db_handler)
    if spider is None:
        return 0

    try:
        return spider.run()
    except Exception as e:
        logger.error(f"运行爬虫 {name} 失败: {e}")
        return 0
