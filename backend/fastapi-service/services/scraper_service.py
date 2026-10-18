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

# 确保domain目录在路径中 (scrapers 模块在 domain/ 下)
DOMAIN_DIR = os.path.join(os.path.dirname(__file__), "..", "domain")
if DOMAIN_DIR not in sys.path:
    sys.path.insert(0, DOMAIN_DIR)


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
    from domain.scrapers.db import DBHandler
    from domain.scrapers.config import load_config, update_config

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

    # 加载配置，并使用环境变量覆盖
    config = load_config()
    
    # 使用环境变量覆盖数据库配置
    db_config = {
        "host": os.getenv("DB_HOST", config.get("database", {}).get("host", "localhost")),
        "port": int(os.getenv("DB_PORT", config.get("database", {}).get("port", 3306))),
        "username": os.getenv("DB_USER", config.get("database", {}).get("username", "root")),
        "password": os.getenv("DB_PASSWORD", config.get("database", {}).get("password", "")),
        "name": os.getenv("DB_NAME", config.get("database", {}).get("name", "news_scraper")),
        "charset": "utf8mb4"
    }
    
    # 更新配置中的数据库设置
    config["database"] = db_config
    db = DBHandler(db_config)

    # 记录日志
    log_id = db.log_spider_start(spider_name)

    try:
        # 动态导入并实例化爬虫
        from domain.scrapers import create_spider
        spider = create_spider(spider_name, config, db)

        if spider is None:
            # 回退：尝试直接实例化
            module_path = f"domain.scrapers.{scraper_info['module']}"
            class_name = scraper_info["class_name"]
            import importlib
            mod = importlib.import_module(module_path)
            spider_cls = getattr(mod, class_name)
            # 回退方式也需要传入参数
            try:
                spider = spider_cls(config, db)
            except TypeError:
                # 部分爬虫可能不需要参数
                spider = spider_cls()

        # 执行爬虫
        import asyncio
        try:
            # 检查爬虫是否有异步方法
            if hasattr(spider, '_async_run'):
                # 使用现有事件循环运行异步爬虫
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果已经有运行中的事件循环，创建新任务
                    items = asyncio.create_task(spider._async_run())
                    # 暂时不支持这种方式，使用线程
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        items = executor.submit(asyncio.run, spider._async_run()).result()
                else:
                    items = loop.run_until_complete(spider._async_run())
            else:
                items = spider.run()
        except TypeError as e:
            # 可能是同步方法但传递了错误参数
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
