"""
爬虫管理 API 路由
===============
负责接收 Spring Boot 的爬虫执行请求，调用 Python 爬虫引擎
"""

import sys
import os
import logging
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

# 添加scrapers路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

router = APIRouter()
logger = logging.getLogger(__name__)

# 全局爬虫运行状态
_running_spiders: dict = {}


@router.get("/list")
async def list_spiders():
    """获取所有爬虫列表及运行状态"""
    from services.scraper_service import get_scraper_registry
    registry = get_scraper_registry()
    return {
        "spiders": registry,
        "running": list(_running_spiders.keys())
    }


@router.post("/start")
async def start_spider(
    spider_name: str = Query(..., description="爬虫名称 (如 xinhua, ifeng, cankaoxiaoxi)"),
    background_tasks: BackgroundTasks = None
):
    """
    启动指定的 Python 爬虫 (由 Spring Boot 并发调度)
    
    支持的爬虫:
    - xinhua: 新华网 (异步混合抓取)
    - ifeng: 凤凰新闻 (多阶段抓取)
    - cankaoxiaoxi: 参考消息 (Selenium)
    - netease_selenium: 网易Selenium版
    """
    from services.scraper_service import run_python_scraper
    
    # 只检查是否正在运行或启动中，不检查已完成或失败的
    current_status = _running_spiders.get(spider_name)
    if current_status in ("running", "starting"):
        raise HTTPException(400, f"爬虫 {spider_name} 正在运行中")
    
    _running_spiders[spider_name] = "starting"
    
    if background_tasks:
        background_tasks.add_task(_execute_scraper, spider_name)
        return {"status": "started", "spider": spider_name}
    else:
        result = await _execute_scraper(spider_name)
        return result


async def _execute_scraper(spider_name: str):
    """后台执行爬虫"""
    from services.scraper_service import run_python_scraper
    try:
        _running_spiders[spider_name] = "running"
        result = run_python_scraper(spider_name)
        _running_spiders[spider_name] = "completed"
        return {"status": "completed", "spider": spider_name, "result": result}
    except Exception as e:
        _running_spiders[spider_name] = "failed"
        logger.error(f"爬虫 {spider_name} 执行失败: {e}")
        return {"status": "failed", "spider": spider_name, "error": str(e)}


@router.post("/stop")
async def stop_spider(spider_name: str = Query(...)):
    """停止正在运行的爬虫"""
    if spider_name not in _running_spiders:
        raise HTTPException(404, f"爬虫 {spider_name} 未在运行")
    _running_spiders[spider_name] = "stopping"
    return {"status": "stopping", "spider": spider_name}


@router.get("/status/{spider_name}")
async def get_spider_status(spider_name: str):
    """查询爬虫运行状态"""
    status = _running_spiders.get(spider_name, "idle")
    return {"spider": spider_name, "status": status}
