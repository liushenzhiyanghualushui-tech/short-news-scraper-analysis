import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .data_cleaner import DataCleaner
from .model_registry import load_classifier

_CLASSIFIER_CACHE: Dict[str, Any] = {}


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve_model_path(model_path: str) -> str:
    if not model_path:
        raise ValueError('缺少模型路径')
    model_path = str(model_path).strip()
    if not model_path:
        raise ValueError('缺少模型路径')
    if os.path.isabs(model_path):
        return model_path
    return os.path.normpath(os.path.join(_project_root(), model_path))


def _get_classifier(model_path: str):
    resolved = _resolve_model_path(model_path)
    cached = _CLASSIFIER_CACHE.get(resolved)
    if cached is not None:
        return cached
    classifier = load_classifier(resolved)
    _CLASSIFIER_CACHE[resolved] = classifier
    return classifier


def _candidate_entities(*, title: str, content: str, top_k: int = 12) -> List[str]:
    text = f"标题：{(title or '').strip()}\n正文：{(content or '').strip()}"
    text = text[:2000]

    candidates: List[str] = []
    for pattern in [r'《([^》]{2,30})》', r'“([^”]{2,30})”', r'"([^"]{2,30})"', r'（([^）]{2,30})）', r'\(([^)]{2,30})\)']:
        for match in re.findall(pattern, text):
            s = str(match).strip()
            if s and s not in candidates:
                candidates.append(s)

    cleaner = DataCleaner()
    try:
        keywords = cleaner.extract_keywords(text.replace('\n', ' '), top_k=max(1, int(top_k)))
    except Exception:
        keywords = []
    for kw in keywords:
        kw = str(kw).strip()
        if kw and kw not in candidates:
            candidates.append(kw)

    return candidates[:max(1, int(top_k))]


def extract_entities(*, title: str, content: str, max_entities: int = 3, entity_model_path: str) -> Dict[str, Any]:
    max_entities = max(1, int(max_entities))
    classifier = _get_classifier(entity_model_path)
    candidates = _candidate_entities(title=title, content=content, top_k=max(12, max_entities * 4))
    if not candidates:
        return {'provider': 'model', 'model': os.path.basename(str(entity_model_path)), 'entities': []}

    inputs = []
    for cand in candidates:
        inputs.append(f"标题：{title}\n正文：{content}\n候选主体：{cand}")

    results = classifier.predict(inputs)
    scored: List[Tuple[str, float]] = []
    for cand, pred in zip(candidates, results):
        category = str(pred.get('category') or '').strip()
        confidence = float(pred.get('confidence') or 0.0)
        if category == 'keep':
            scored.append((cand, confidence))

    scored.sort(key=lambda item: item[1], reverse=True)
    entities = [{'name': name, 'type': 'other', 'aliases': []} for name, _ in scored[:max_entities]]
    return {'provider': 'model', 'model': os.path.basename(str(entity_model_path)), 'entities': entities}


def extract_stances(
    *,
    title: str,
    content: str,
    entities: List[Dict[str, Any]],
    stance_model_path: str,
    sentiment_model_path: str
) -> Dict[str, Any]:
    entity_names = [str(e.get('name') or '').strip() for e in entities if isinstance(e, dict)]
    entity_names = [n for n in entity_names if n]
    if not entity_names:
        return {'provider': 'model', 'model': os.path.basename(str(stance_model_path)), 'stances': []}

    stance_classifier = _get_classifier(stance_model_path)
    sentiment_classifier = _get_classifier(sentiment_model_path)

    inputs = [f"标题：{title}\n正文：{content}\n主体：{name}" for name in entity_names]
    stance_results = stance_classifier.predict(inputs)
    sentiment_results = sentiment_classifier.predict(inputs)

    stances = []
    for name, stance_pred, sent_pred in zip(entity_names, stance_results, sentiment_results):
        stance = str(stance_pred.get('category') or 'unclear').strip()
        sentiment = str(sent_pred.get('category') or 'neu').strip()
        try:
            stance_conf = float(stance_pred.get('confidence') or 0.0)
        except Exception:
            stance_conf = 0.0
        try:
            sent_conf = float(sent_pred.get('confidence') or 0.0)
        except Exception:
            sent_conf = 0.0
        stances.append({
            'entity': name,
            'stance': stance,
            'sentiment': sentiment,
            'confidence': max(0.0, min(1.0, min(stance_conf, sent_conf))),
            'evidence': [],
        })

    return {
        'provider': 'model',
        'model': os.path.basename(str(stance_model_path)),
        'stances': stances,
    }
