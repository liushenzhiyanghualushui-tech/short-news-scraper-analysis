"""
模型服务层
=======
模型训练、评估、预测
适配自原 scrapers/model_builder.py
"""

import os
import sys
import logging

logger = logging.getLogger(__name__)

SCRAPERS_DIR = os.path.join(os.path.dirname(__file__), "..", "scrapers")
if SCRAPERS_DIR not in sys.path:
    sys.path.insert(0, SCRAPERS_DIR)


class ModelService:
    """模型训练与预测服务"""

    def __init__(self):
        self._trainer = None
        self._classifier = None
        self._current_model_type = None

    def _get_db(self):
        from scrapers.db import DBHandler
        from scrapers.config import load_config
        config = load_config()
        return DBHandler(config.get("database", {}))

    def train(self, model_type: str = "svm", feature_type: str = "tfidf",
              test_size: float = 0.2, limit: int = 10000, progress_callback=None):
        """
        训练模型

        Args:
            model_type: 模型类型 (svm/rf/nb/lr/bert/bert_textcnn)
            feature_type: 特征类型 (tfidf/bow/bert)
            test_size: 测试集比例
            limit: 数据量上限
            progress_callback: 进度回调 (pct, message)
        """
        from scrapers.model_builder import ModelTrainer

        if progress_callback:
            progress_callback(0.1, "正在加载训练数据...")

        self._trainer = ModelTrainer()
        self._current_model_type = model_type

        if progress_callback:
            progress_callback(0.3, "正在特征工程...")

        result = self._trainer.train(
            model_type=model_type,
            feature_type=feature_type,
            test_size=test_size,
            limit=limit
        )

        if progress_callback:
            progress_callback(0.9, "训练完成，保存结果...")

        # 保存模型
        save_dir = os.path.join(os.path.dirname(__file__), "..", "saved_models", f"latest_{model_type}")
        os.makedirs(save_dir, exist_ok=True)
        self._trainer.save(save_dir)

        if progress_callback:
            progress_callback(1.0, "完成")

        return result

    def evaluate(self, model_type: str = "svm", limit: int = 5000):
        """评估模型"""
        from scrapers.model_builder import ModelTrainer

        trainer = ModelTrainer()
        save_dir = os.path.join(os.path.dirname(__file__), "..", "saved_models", f"latest_{model_type}")

        if os.path.exists(save_dir):
            trainer.load(save_dir)
        else:
            # 没有已保存模型，直接训练评估
            trainer.train(model_type=model_type, limit=limit)

        return trainer.evaluate(limit=limit)

    def predict_single(self, text: str):
        """单条文本预测"""
        if self._trainer is None:
            self._load_latest_model()
        
        if self._trainer:
            return self._trainer.predict(text)
        else:
            from scrapers.model_builder import TextClassifier
            clf = TextClassifier(model_type="svm")
            # 尝试加载预训练模型
            save_dir = os.path.join(os.path.dirname(__file__), "..", "saved_models", "latest_svm")
            if os.path.exists(save_dir):
                clf.load(save_dir)
            return clf.predict(text)

    def apply_model_batch(self, limit: int = 1000, model_type: str = "svm"):
        """批量应用模型预测"""
        db = self._get_db()
        articles = db.get_recent_articles(limit=limit, source_code=None)

        if not articles:
            return 0

        if self._trainer is None:
            self._load_latest_model()

        count = 0
        for article in articles:
            content = article.get("content", "") or article.get("title", "")
            if content and self._trainer:
                try:
                    prediction = self._trainer.predict(content[:500])
                    # 更新分类结果到数据库
                    # db.update_article_category(article["id"], prediction)
                    count += 1
                except Exception as e:
                    logger.warning(f"预测文章 {article['id']} 失败: {e}")

        return count

    def _load_latest_model(self):
        """加载最新保存的模型"""
        save_dir = os.path.join(os.path.dirname(__file__), "..", "saved_models", "latest_svm")
        if os.path.exists(save_dir):
            try:
                from scrapers.model_builder import TextClassifier
                self._trainer = TextClassifier(model_type="svm")
                self._trainer.load(save_dir)
                self._current_model_type = "svm"
                logger.info(f"已加载模型: {save_dir}")
            except Exception as e:
                logger.warning(f"加载模型失败: {e}")

    def save_model(self, name: str):
        """保存模型到指定名称"""
        if self._trainer is None:
            raise ValueError("没有已训练的模型")

        save_dir = os.path.join(os.path.dirname(__file__), "..", "saved_models", name)
        os.makedirs(save_dir, exist_ok=True)
        self._trainer.save(save_dir)
        return save_dir

    def load_model(self, name: str):
        """加载指定模型"""
        from scrapers.model_builder import ModelTrainer
        from scrapers.model_registry import detect_saved_model_type, build_classifier_by_type

        save_dir = os.path.join(os.path.dirname(__file__), "..", "saved_models", name)
        if not os.path.exists(save_dir):
            raise FileNotFoundError(f"模型不存在: {save_dir}")

        model_type = detect_saved_model_type(save_dir)
        self._current_model_type = model_type
        self._trainer = build_classifier_by_type(model_type)
        self._trainer.load(save_dir)
        logger.info(f"已加载模型 {name} (类型: {model_type})")
