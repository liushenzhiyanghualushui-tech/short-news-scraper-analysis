"""
数据服务层
=======
数据清洗、统计分析、词频分析
适配自原 scrapers/data_cleaner.py
"""

import os
import sys
import logging

logger = logging.getLogger(__name__)

# 路径设置
SCRAPERS_DIR = os.path.join(os.path.dirname(__file__), "..", "scrapers")
if SCRAPERS_DIR not in sys.path:
    sys.path.insert(0, SCRAPERS_DIR)


class DataService:
    """数据清洗与分析服务"""

    def __init__(self):
        self._cleaner = None

    def _get_cleaner(self):
        """延迟加载 DataCleaner"""
        if self._cleaner is None:
            from scrapers.data_cleaner import DataCleaner
            self._cleaner = DataCleaner()
        return self._cleaner

    def _get_db(self):
        from scrapers.db import DBHandler
        from scrapers.config import load_config
        config = load_config()
        return DBHandler(config.get("database", {}))

    def clean_articles(self, limit: int = 1000, source_codes: list = None):
        """
        执行数据清洗

        步骤:
        1. 从数据库获取文章
        2. 去重、缺失值处理
        3. 文本预处理 (分词、去停用词)
        4. LLM格式筛选 (如启用)
        5. 自动分类打标
        """
        db = self._get_db()
        cleaner = self._get_cleaner()

        # 获取文章数据
        articles = db.get_recent_articles(limit=limit, source_code=source_codes[0] if source_codes and len(source_codes) == 1 else None)

        if not articles:
            return {"cleaned": 0, "message": "没有待清洗数据"}

        # 转换为DataFrame
        import pandas as pd
        df = pd.DataFrame(articles)

        # 执行清洗
        cleaned_df = cleaner.clean_dataframe(df)

        # 自动打标
        labeled_count = 0
        if not cleaned_df.empty:
            labeled_df = cleaner.auto_label(cleaned_df)
            labeled_count = len(labeled_df)

        stats = cleaner.get_statistics(cleaned_df)

        return {
            "total_input": len(articles),
            "cleaned": len(cleaned_df),
            "labeled": labeled_count,
            "statistics": stats
        }

    def analyze_word_frequency(self, limit: int = 500, top_n: int = 100, source_codes: list = None):
        """词频分析"""
        db = self._get_db()
        cleaner = self._get_cleaner()

        articles = db.get_recent_articles(limit=limit, source_code=source_codes[0] if source_codes and len(source_codes) == 1 else None)

        if not articles:
            return []

        import pandas as pd
        df = pd.DataFrame(articles)
        result = cleaner.analyze_word_frequency(df, top_n=top_n)
        return result

    def get_statistics(self):
        """获取数据概览统计"""
        db = self._get_db()

        # 总文章数
        sources = db.get_all_sources("domestic")
        stats = {"total_sources": len(sources), "by_source": {}}

        for source in sources:
            code = source.get("code", "")
            articles = db.get_recent_articles(limit=10000, source_code=code)
            stats["by_source"][code] = {
                "name": source.get("name", ""),
                "count": len(articles),
                "is_active": bool(source.get("is_active", 1))
            }

        stats["total_articles"] = sum(s["count"] for s in stats["by_source"].values())
        return stats
