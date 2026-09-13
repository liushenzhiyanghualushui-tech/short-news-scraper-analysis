"""
FastAPI 主应用入口
===============
短新闻爬取与分析系统 - AI服务层

职责:
- 复杂爬虫执行 (Selenium/异步混合类)
- 数据清洗与预处理
- ML模型训练/评估/预测
- NLP分析 (情感分析/事件聚合)
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import scraping, data, model, nlp

# ---- 日志配置 ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("🚀 FastAPI 服务启动中...")
    logger.info(f"   HF 镜像: {os.getenv('HF_ENDPOINT', 'https://hf-mirror.com')}")
    logger.info(f"   模型ID: {os.getenv('HF_MODEL_ID', 'bert-base-chinese')}")
    yield
    logger.info("🛑 FastAPI 服务关闭")


app = FastAPI(
    title="短新闻爬取与分析 - AI服务",
    description="提供爬虫执行、数据清洗、模型训练、NLP分析等能力",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(scraping.router, prefix="/api/scraping", tags=["爬虫管理"])
app.include_router(data.router, prefix="/api/data", tags=["数据处理"])
app.include_router(model.router, prefix="/api/model", tags=["模型管理"])
app.include_router(nlp.router, prefix="/api/nlp", tags=["NLP分析"])


@app.get("/api/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "service": "fastapi-ai",
        "version": "2.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
