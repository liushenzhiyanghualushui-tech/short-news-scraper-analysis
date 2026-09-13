import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .data_cleaner import DataCleaner
from .llm_client import LLMUnavailableError, chat_json
from .vectorizers import to_dense_distance_matrix, vectorize_texts


def _article_text(title: str, content: str, limit_chars: int = 1200) -> str:
    title = (title or '').strip()
    content = (content or '').strip()
    text = f"{title} {content}"
    return text[:limit_chars] if len(text) > limit_chars else text


def cluster_articles(
    *,
    articles: List[Dict[str, Any]],
    embedding_max_length: int,
    embedding_batch_size: int,
    vector_model_path: str,
    similarity_threshold: float,
    min_cluster_size: int
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    texts = [_article_text(a.get('title', ''), a.get('content', '')) for a in articles]
    min_cluster_size = max(2, int(min_cluster_size))
    similarity_threshold = float(similarity_threshold)

    vectors, meta = vectorize_texts(
        texts=texts,
        model_path=vector_model_path,
        embedding_max_length=embedding_max_length,
        embedding_batch_size=embedding_batch_size,
    )

    from sklearn.cluster import AgglomerativeClustering

    dist_matrix, distance_threshold = to_dense_distance_matrix(vectors, similarity_threshold=similarity_threshold)
    if dist_matrix is not None:
        clustering = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=distance_threshold,
            metric='precomputed',
            linkage='average',
        )
        labels = clustering.fit_predict(dist_matrix)
    else:
        clustering = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=distance_threshold,
            metric='cosine',
            linkage='average',
        )
        labels = clustering.fit_predict(vectors)

    clusters_map: Dict[int, List[int]] = {}
    for idx, label in enumerate(labels):
        clusters_map.setdefault(int(label), []).append(idx)

    clusters = []
    cluster_id = 0
    for _, indices in sorted(clusters_map.items(), key=lambda item: len(item[1]), reverse=True):
        if len(indices) < min_cluster_size:
            continue
        cluster_articles = [articles[i] for i in indices]
        article_ids = [int(a['id']) for a in cluster_articles if 'id' in a]
        clusters.append({
            'cluster_id': cluster_id,
            'indices': indices,
            'article_ids': article_ids,
            'size': len(indices),
        })
        cluster_id += 1

    return clusters, meta


def build_event_frame(
    *,
    cluster_articles: List[Dict[str, Any]],
    use_llm: bool
) -> Dict[str, Any]:
    if not cluster_articles:
        return {'title': '', 'summary': '', 'key_points': [], 'keywords': [], 'time_span': {'start': None, 'end': None}}

    titles = [str(a.get('title') or '').strip() for a in cluster_articles if str(a.get('title') or '').strip()]
    contents = [str(a.get('content') or '').strip() for a in cluster_articles]
    publish_times = [a.get('publish_time') for a in cluster_articles]

    start_time, end_time = _get_time_span(publish_times)

    if use_llm:
        schema_hint = '{"title":"...","summary":"...","key_points":["..."],"keywords":["..."],"time_span":{"start":"...","end":"..."},"timeline":[{"time":"...","fact":"..."}],"key_entities":[{"name":"...","role":"..."}],"differences":["..."]}'
        system_prompt = "你是中文新闻编辑，负责从同一事件的多篇新闻中提炼事件框架。"
        sample_items = []
        for a in cluster_articles[:20]:
            sample_items.append({
                'title': str(a.get('title') or '')[:120],
                'publish_time': str(a.get('publish_time') or ''),
                'snippet': str(a.get('content') or '')[:200],
                'source_name': str(a.get('source_name') or ''),
            })
        user_content = (
            "以下是同一事件的一组新闻，请输出事件框架 JSON。\n"
            "要求：key_points 不超过 6 条；timeline 不超过 6 条；keywords 不超过 10 个。\n"
            f"新闻列表：{json.dumps(sample_items, ensure_ascii=False)}"
        )
        try:
            data = chat_json(
                system_prompt=system_prompt,
                user_content=user_content,
                schema_hint=schema_hint,
                temperature=0.1,
                max_tokens=900,
            )
            if isinstance(data, dict):
                data.setdefault('time_span', {'start': start_time, 'end': end_time})
                return data
        except LLMUnavailableError:
            pass
        except Exception:
            pass

    cleaner = DataCleaner()
    merged_text = ' '.join(titles[:50]) + ' ' + ' '.join(c[:300] for c in contents[:50])
    try:
        keywords = cleaner.extract_keywords(merged_text, top_k=10)
    except Exception:
        keywords = []

    title = titles[0] if titles else (keywords[0] if keywords else '热点事件')
    key_points = titles[:6] if titles else []
    summary = (titles[0] if titles else '')[:200]

    return {
        'title': title,
        'summary': summary,
        'key_points': key_points,
        'keywords': keywords,
        'time_span': {'start': start_time, 'end': end_time},
    }


def _get_time_span(publish_times: List[Any]) -> Tuple[Optional[str], Optional[str]]:
    parsed = []
    for t in publish_times:
        if t is None:
            continue
        if isinstance(t, datetime):
            parsed.append(t)
            continue
        try:
            parsed.append(datetime.fromisoformat(str(t)))
        except Exception:
            continue
    if not parsed:
        return None, None
    start = min(parsed).isoformat(sep=' ')
    end = max(parsed).isoformat(sep=' ')
    return start, end
