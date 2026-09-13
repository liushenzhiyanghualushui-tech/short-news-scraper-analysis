"""
模型管理 API 路由
===============
模型训练、评估、预测、保存/加载
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks

router = APIRouter()
logger = logging.getLogger(__name__)

# 训练状态
_training_state: dict = {"status": "idle", "progress": 0, "message": ""}


@router.post("/train")
async def train_model(
    background_tasks: BackgroundTasks,
    model_type: str = Query("svm", description="模型类型: svm/rf/nb/lr/bert/bert_textcnn"),
    feature_type: str = Query("tfidf", description="特征类型: tfidf/bow/bert"),
    test_size: float = Query(0.2, description="测试集比例"),
    limit: int = Query(10000, description="训练数据上限")
):
    """
    启动模型训练任务 (后台执行)

    模型类型说明:
    - svm: 支持向量机 (快速，适合小样本)
    - rf: 随机森林 (鲁棒性好)
    - nb: 朴素贝叶斯
    - lr: 逻辑回归
    - bert: BERT微调 (精度高，需GPU)
    - bert_textcnn: BERT+TextCNN混合模型
    """
    if _training_state["status"] == "running":
        raise HTTPException(400, "已有训练任务在运行中")

    _training_state.update(status="running", progress=0, message="初始化...")

    background_tasks.add_task(
        _run_training, model_type, feature_type, test_size, limit
    )
    return {"status": "started", "model_type": model_type}


async def _run_training(model_type: str, feature_type: str, test_size: float, limit: int):
    """后台训练任务"""
    try:
        from services.model_service import ModelService
        service = ModelService()

        def progress_callback(pct: float, msg: str):
            _training_state.update(progress=pct, message=msg)

        _training_state.update(message="加载数据...")
        result = service.train(
            model_type=model_type,
            feature_type=feature_type,
            test_size=test_size,
            limit=limit,
            progress_callback=progress_callback
        )
        _training_state.update(status="completed", progress=100, message="训练完成")
    except Exception as e:
        logger.error(f"模型训练失败: {e}")
        _training_state.update(status="failed", progress=0, message=str(e))


@router.get("/train/status")
async def training_status():
    """获取训练进度"""
    return _training_state


@router.post("/evaluate")
async def evaluate_model(
    model_type: str = Query("svm"),
    limit: int = Query(5000)
):
    """评估已训练的模型"""
    try:
        from services.model_service import ModelService
        service = ModelService()
        result = service.evaluate(model_type=model_type, limit=limit)
        return {"status": "success", "metrics": result}
    except Exception as e:
        logger.error(f"模型评估失败: {e}")
        raise HTTPException(500, str(e))


@router.post("/predict")
async def predict_text(text: str = Query(..., description="待分类文本")):
    """对单条文本进行分类预测"""
    try:
        from services.model_service import ModelService
        service = ModelService()
        result = service.predict_single(text)
        return {"status": "success", "prediction": result}
    except Exception as e:
        logger.error(f"预测失败: {e}")
        raise HTTPException(500, str(e))


@router.post("/apply")
async def apply_model_batch(
    background_tasks: BackgroundTasks,
    limit: int = Query(1000, description="批量处理数量"),
    model_type: str = Query("svm")
):
    """批量应用模型对未分类文章进行预测"""
    if _training_state.get("applying"):
        raise HTTPException(400, "已有批量应用任务在运行中")
    
    _training_state["applying"] = True
    
    background_tasks.add_task(_run_batch_apply, limit, model_type)
    return {"status": "started", "limit": limit}


async def _run_batch_apply(limit: int, model_type: str):
    try:
        from services.model_service import ModelService
        service = ModelService()
        count = service.apply_model_batch(limit=limit, model_type=model_type)
        _training_state["applying"] = False
        _training_state["applied_count"] = count
    except Exception as e:
        logger.error(f"批量应用失败: {e}")
        _training_state["applying"] = False
        _training_state["apply_error"] = str(e)


@router.post("/save")
async def save_model(name: str = Query(..., description="模型保存名称")):
    """保存当前模型"""
    try:
        from services.model_service import ModelService
        service = ModelService()
        path = service.save_model(name)
        return {"status": "success", "path": path}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/load")
async def load_model(name: str = Query(..., description="模型名称")):
    """加载已保存的模型"""
    try:
        from services.model_service import ModelService
        service = ModelService()
        service.load_model(name)
        return {"status": "success", "model": name}
    except Exception as e:
        raise HTTPException(500, str(e))
