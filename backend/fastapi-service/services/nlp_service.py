"""
NLP服务层
=======
情感分析、事件聚合、实体提取
"""

import os
import sys
import logging

logger = logging.getLogger(__name__)

SCRAPERS_DIR = os.path.join(os.path.dirname(__file__), "..", "scrapers")
if SCRAPERS_DIR not in sys.path:
    sys.path.insert(0, SCRAPERS_DIR)


class NLPService:
    """NLP分析服务"""

    def _get_db(self):
        from scrapers.db import DBHandler
        from scrapers.config import load_config
        config = load_config()
        return DBHandler(config.get("database", {}))

    def analyze_sentiment(self, article_id: int, method: str = "classifier"):
        """对单篇文章进行情感分析"""
        db = self._get_db()
        article = db.get_recent_articles(limit=1, offset=0)

        # 简化实现：查找目标文章
        target = None
        for a in article:
            if a.get("id") == article_id:
                target = a
                break

        if not target:
            raise ValueError(f"文章不存在: {article_id}")

        content = target.get("content", "") or target.get("title", "")

        if method == "llm":
            from scrapers.sentiment_labeler import llm_extract_entities, llm_extract_stances
            from scrapers.sentiment_extractor import extract_entities, extract_stances

            entities = llm_extract_entities(content)
            stances = llm_extract_stances(content, entities)
        else:
            from scrapers.sentiment_extractor import extract_entities, extract_stances
            entities = extract_entities(content)
            stances = extract_stances(content, entities)

        return {
            "entities": entities,
            "stances": stances,
            "method": method
        }

    def batch_sentiment_analysis(self, limit: int = 100, source_codes: list = None):
        """批量情感分析"""
        db = self._get_db()
        articles = db.get_recent_articles(limit=limit)

        results = []
        for article in articles:
            content = article.get("content", "") or article.get("title", "")
            if not content:
                continue

            try:
                from scrapers.sentiment_extractor import extract_entities, extract_stances
                entities = extract_entities(content)
                stances = extract_stances(content, entities)
                results.append({
                    "article_id": article["id"],
                    "title": article.get("title", ""),
                    "entities": entities,
                    "stances": stances
                })
            except Exception as e:
                logger.warning(f"分析文章 {article.get('id')} 失败: {e}")

        return results

    def aggregate_events(self, limit: int = 500, threshold: float = 0.5):
        """事件聚合"""
        db = self._get_db()
        articles = db.get_recent_articles(limit=limit)

        if not articles:
            return []

        from scrapers.embeddings import LocalTransformerEmbedder
        from scrapers.vectorizers import vectorize_texts
        from scrapers.event_aggregator import cluster_articles, build_event_frame

        texts = [a.get("content", "") or a.get("title", "") for a in articles]
        ids = [a["id"] for a in articles]

        # 向量化
        embedder = LocalTransformerEmbedder()
        embeddings = embedder.encode(texts)

        # 聚类
        clusters = cluster_articles(
            embeddings=embeddings,
            article_ids=ids,
            threshold=threshold
        )

        # 构建事件
        events = []
        for cluster_id, cluster_data in clusters.items():
            event = build_event_frame(cluster_data, articles)
            events.append(event)

        return events

    def list_events(self, limit: int = 20, offset: int = 0):
        """获取事件列表"""
        db = self._get_db()
        try:
            with db.get_connection_ctx() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"SELECT * FROM {db.get_table_name('events')} ORDER BY created_at DESC LIMIT %s OFFSET %s",
                        (limit, offset)
                    )
                    return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取事件列表失败: {e}")
            return []

    def get_event_articles(self, event_id: int):
        """获取事件关联文章"""
        db = self._get_db()
        try:
            with db.get_connection_ctx() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"""SELECT a.* FROM {db.get_table_name('raw_articles')} a
                        INNER JOIN {db.get_table_name('event_articles')} ea ON a.id = ea.article_id
                        WHERE ea.event_id = %s ORDER BY a.publish_time DESC""",
                        (event_id,)
                    )
                    return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取事件文章失败: {e}")
            return []

    def extract_entities_and_stances(self, article_id: int, method: str = "classifier"):
        """提取文章实体和立场"""
        return self.analyze_sentiment(article_id, method)
