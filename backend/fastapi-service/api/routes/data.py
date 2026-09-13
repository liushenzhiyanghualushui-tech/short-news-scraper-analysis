"""
数据处理 API 路由
===============
数据清洗、词频统计、数据统计
"""

import logging
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/clean")
async def clean_data(
    limit: int = Query(1000, description="处理条数上限"),
    source_codes: str = Query("", description="来源编码，逗号分隔，空=全部")
):
    """
    对原始文章执行数据清洗
    包括: 去重、缺失值处理、文本预处理、LLM筛选
    """
    try:
        from services.data_service import DataService
        service = DataService()
        codes = [c.strip() for c in source_codes.split(",") if c.strip()] if source_codes else None
        result = service.clean_articles(limit=limit, source_codes=codes)
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"数据清洗失败: {e}")
        raise HTTPException(500, str(e))


@router.get("/word-frequency")
async def word_frequency(
    limit: int = Query(500, description="分析文章数"),
    top_n: int = Query(100, description="返回Top N高频词"),
    source_codes: str = Query("", description="来源编码过滤")
):
    """词频统计分析"""
    try:
        from services.data_service import DataService
        service = DataService()
        codes = [c.strip() for c in source_codes.split(",") if c.strip()] if source_codes else None
        result = service.analyze_word_frequency(limit=limit, top_n=top_n, source_codes=codes)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"词频分析失败: {e}")
        raise HTTPException(500, str(e))


@router.get("/stats")
async def data_statistics():
    """获取数据概览统计"""
    try:
        from services.data_service import DataService
        service = DataService()
        stats = service.get_statistics()
        return {"status": "success", "data": stats}
    except Exception as e:
        logger.error(f"获取统计失败: {e}")
        raise HTTPException(500, str(e))
