"""
爬虫服务层
=======
封装对现有 scrapers/ 模块的调用
支持 Python 重型爬虫: xinhua, ifeng, cankaoxiaoxi, netease_selenium, sll
"""

import os
import sys
import logging

logger = logging.getLogger(__name__)

# 确保scrapers目录在路径中
SCRAPERS_DIR = os.path.join(os.path.dirname(__file__), "..", "scrapers")
if SCRAPERS_DIR not in sys.path:
    sys.path.insert(0, SCRAPERS_DIR)


# 爬虫注册表: 定义哪些爬虫由Python执行（重型/浏览器爬虫）
PYTHON_SCRAPER_REGISTRY = [
    {
        "name": "xinhua",
        "label": "新华网",
        "description": "高并发异步混合采集 (aiohttp + Selenium)",
        "module": "domestic.xinhua",
        "class_name": "XinhuaSpider",
        "features": ["async", "selenium", "channel_discovery", "cookie_pool"],
        "estimated_duration": "3-8分钟",
        "concurrency": 20
    },
    {
        "name": "ifeng",
        "label": "凤凰新闻",
        "description": "多阶段抓取 + 域名节流器 + 代理轮换",
        "module": "domestic.ifeng",
        "class_name": "IfengSpider",
        "features": ["multi_stage", "domain_throttle", "proxy_rotation"],
        "estimated_duration": "2-6分钟",
        "concurrency": 15
    },
    {
        "name": "cankaoxiaoxi",
        "label": "参考消息",
        "description": "Selenium + 代理轮换",
        "module": "domestic.cankaoxiaoxi",
        "class_name": "CankaoxiaoxiSpider",
        "features": ["selenium", "proxy_rotation"],
        "estimated_duration": "2-5分钟",
        "concurrency": 15
    },
    {
        "name": "netease_selenium",
        "label": "网易新闻(Selenium)",
        "description": "Edge WebDriver 动态渲染页面",
        "module": "domestic.netease_selenium",
        "class_name": "NeteaseSeleniumSpider",
        "features": ["selenium", "edge_webdriver"],
        "estimated_duration": "1-3分钟",
        "concurrency": 10
    },
    {
        "name": "sll",
        "label": "SLL新闻",
        "description": "SLL专用爬虫",
        "module": "domestic.sll",
        "class_name": "SLLSpider",
        "features": ["custom_parser"],
        "estimated_duration": "1-3分钟",
        "concurrency": 20
    }
]


def get_scraper_registry():
    """获取爬虫注册表"""
    return PYTHON_SCRAPER_REGISTRY


def run_python_scraper(spider_name: str):
    """
    执行指定的 Python 爬虫

    Args:
        spider_name: 爬虫名称 (如 xinhua, ifeng, cankaoxiaoxi)

    Returns:
        dict: 执行结果 {success, items_count, duration, error}
    """
    import time
    from scrapers.db import DBHandler
    from scrapers.config import load_config

    start_time = time.time()

    # 查找爬虫配置
    scraper_info = None
    for s in PYTHON_SCRAPER_REGISTRY:
        if s["name"] == spider_name:
            scraper_info = s
            break

    if not scraper_info:
        raise ValueError(f"未知爬虫: {spider_name}。可用: {[s['name'] for s in PYTHON_SCRAPER_REGISTRY]}")

    logger.info(f"🚀 启动爬虫: {scraper_info['label']} ({spider_name})")

    # 加载配置
    config = load_config()
    db_config = config.get("database", {})
    db = DBHandler(db_config)

    # 记录日志
    log_id = db.log_spider_start(spider_name)

    try:
        # 动态导入并实例化爬虫
        from scrapers import create_spider
        spider = create_spider(spider_name)

        if spider is None:
            # 回退：尝试直接实例化
            module_path = f"scrapers.{scraper_info['module']}"
            class_name = scraper_info["class_name"]
            import importlib
            mod = importlib.import_module(module_path)
            spider_cls = getattr(mod, class_name)
            spider = spider_cls()

        # 执行爬虫
        items = spider.run()

        duration = int(time.time() - start_time)
        db.log_spider_end(log_id, "success", len(items) if items else 0)

        logger.info(f"✅ 爬虫 {spider_name} 完成: {len(items) if items else 0} 条, 耗时 {duration}s")

        return {
            "success": True,
            "items_count": len(items) if items else 0,
            "duration_seconds": duration
        }

    except Exception as e:
        duration = int(time.time() - start_time)
        error_msg = str(e)
        db.log_spider_end(log_id, "failed", 0, error_msg)
        logger.error(f"❌ 爬虫 {spider_name} 失败 (耗时 {duration}s): {error_msg}")
        raise


def run_multiple_scrapers(spider_names: list):
    """并发执行多个爬虫（在Python内部异步）"""
    import asyncio

    async def _run():
        tasks = []
        for name in spider_names:
            tasks.append(asyncio.to_thread(run_python_scraper, name))
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = []
        for name, result in zip(spider_names, results):
            if isinstance(result, Exception):
                output.append({"name": name, "success": False, "error": str(result)})
            else:
                output.append({"name": name, **result})
        return output

    return asyncio.run(_run())
