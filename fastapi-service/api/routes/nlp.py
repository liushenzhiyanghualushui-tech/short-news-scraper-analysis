"""
NLP分析 API 路由
===============
情感分析、事件聚合、实体提取
"""

import logging
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/sentiment/analyze")
async def analyze_sentiment(
    article_id: int = Query(..., description="文章ID"),
    method: str = Query("classifier", description="方式: classifier/llm")
):
    """对指定文章进行情感分析"""
    try:
        from services.nlp_service import NLPService
        service = NLPService()
        result = service.analyze_sentiment(article_id, method=method)
        return {"status": "success", "article_id": article_id, "result": result}
    except Exception as e:
        logger.error(f"情感分析失败: {e}")
        raise HTTPException(500, str(e))


@router.post("/sentiment/batch")
async def batch_sentiment_analysis(
    limit: int = Query(100, description="分析文章数量"),
    source_codes: str = Query("", description="来源编码过滤")
):
    """批量情感分析"""
    try:
        from services.nlp_service import NLPService
        service = NLPService()
        codes = [c.strip() for c in source_codes.split(",") if c.strip()] if source_codes else None
        result = service.batch_sentiment_analysis(limit=limit, source_codes=codes)
        return {"status": "success", "count": len(result), "results": result}
    except Exception as e:
        logger.error(f"批量情感分析失败: {e}")
        raise HTTPException(500, str(e))


@router.post("/events/aggregate")
async def aggregate_events(
    limit: int = Query(500, description="聚合文章数"),
    cluster_threshold: float = Query(0.5, description="聚类阈值 (0-1)")
):
    """事件聚合 - 将相关文章聚类为事件"""
    try:
        from services.nlp_service import NLPService
        service = NLPService()
        events = service.aggregate_events(limit=limit, threshold=cluster_threshold)
        return {"status": "success", "events_count": len(events), "events": events}
    except Exception as e:
        logger.error(f"事件聚合失败: {e}")
        raise HTTPException(500, str(e))


@router.get("/events")
async def list_events(
    limit: int = Query(20),
    offset: int = Query(0)
):
    """获取已聚合的事件列表"""
    try:
        from services.nlp_service import NLPService
        service = NLPService()
        events = service.list_events(limit=limit, offset=offset)
        return {"status": "success", "events": events}
    except Exception as e:
        logger.error(f"获取事件列表失败: {e}")
        raise HTTPException(500, str(e))


@router.get("/events/{event_id}/articles")
async def get_event_articles(event_id: int):
    """获取事件关联的文章"""
    try:
        from services.nlp_service import NLPService
        service = NLPService()
        articles = service.get_event_articles(event_id)
        return {"status": "success", "event_id": event_id, "articles": articles}
    except Exception as e:
        logger.error(f"获取事件文章失败: {e}")
        raise HTTPException(500, str(e))


@router.post("/entities/extract")
async def extract_entities(
    article_id: int = Query(..., description="文章ID"),
    method: str = Query("classifier", description="方式: classifier/llm")
):
    """提取文章中的关键实体和立场"""
    try:
        from services.nlp_service import NLPService
        service = NLPService()
        result = service.extract_entities_and_stances(article_id, method=method)
        return {"status": "success", "article_id": article_id, "result": result}
    except Exception as e:
        logger.error(f"实体提取失败: {e}")
        raise HTTPException(500, str(e))
