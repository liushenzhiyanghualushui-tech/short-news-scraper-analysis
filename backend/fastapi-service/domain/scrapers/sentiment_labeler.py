import json
from typing import Any, Dict, List

from .llm_client import chat_json


def _build_article_text(title: str, content: str, limit_chars: int = 2500) -> str:
    title = (title or '').strip()
    content = (content or '').strip()
    text = f"标题：{title}\n正文：{content}"
    if len(text) > limit_chars:
        return text[:limit_chars]
    return text


def llm_extract_entities(*, title: str, content: str, max_entities: int = 3) -> List[Dict[str, Any]]:
    article_text = _build_article_text(title, content)
    max_entities = max(1, int(max_entities))

    schema_hint = '{"entities":[{"name":"...","type":"person|org|country|gov|other","aliases":["..."]}]}'
    system_prompt = "你是中文新闻分析助手，负责从新闻中识别关键主体。"
    user_content = (
        f"请从以下新闻中抽取最多 {max_entities} 个最重要的主体（人物/机构/国家/政府/其他）。\n"
        "要求：主体要具体、不要返回空泛词（如“相关部门”“网友”）。\n"
        "只返回 JSON。\n\n"
        f"{article_text}"
    )

    data = chat_json(
        system_prompt=system_prompt,
        user_content=user_content,
        schema_hint=schema_hint,
        temperature=0.1,
        max_tokens=400,
    )

    entities = data.get('entities') if isinstance(data, dict) else None
    if not isinstance(entities, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for item in entities[:max_entities]:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '').strip()
        if not name:
            continue
        aliases = item.get('aliases') if isinstance(item.get('aliases'), list) else []
        normalized.append({
            'name': name,
            'type': str(item.get('type') or 'other'),
            'aliases': [str(x).strip() for x in aliases if str(x).strip()],
        })
    return normalized


def llm_extract_stances(*, title: str, content: str, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    article_text = _build_article_text(title, content)
    entity_names = [str(e.get('name') or '').strip() for e in entities if isinstance(e, dict)]
    entity_names = [n for n in entity_names if n]
    if not entity_names:
        return []

    schema_hint = '{"stances":[{"entity":"...","stance":"support|oppose|neutral|unclear","sentiment":"pos|neg|neu","confidence":0.0,"evidence":["..."]}]}'
    system_prompt = "你是中文新闻分析助手，负责判断新闻对指定主体的态度与证据。"
    user_content = (
        "请基于新闻原文，判断新闻对每个主体的态度。\n"
        "stance 仅允许：support/oppose/neutral/unclear。\n"
        "sentiment 仅允许：pos/neg/neu。\n"
        "evidence 必须是原文中可直接引用的短片段（最多 2 条，每条不超过 40 字）。\n"
        "如果原文无法判断，stance=unclear，confidence 取较低值。\n"
        f"主体列表：{json.dumps(entity_names, ensure_ascii=False)}\n\n"
        f"{article_text}"
    )

    data = chat_json(
        system_prompt=system_prompt,
        user_content=user_content,
        schema_hint=schema_hint,
        temperature=0.1,
        max_tokens=800,
    )

    stances = data.get('stances') if isinstance(data, dict) else None
    if not isinstance(stances, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for item in stances:
        if not isinstance(item, dict):
            continue
        entity = str(item.get('entity') or '').strip()
        if entity not in entity_names:
            continue
        stance = str(item.get('stance') or 'unclear').strip()
        sentiment = str(item.get('sentiment') or 'neu').strip()
        try:
            confidence = float(item.get('confidence') or 0.0)
        except Exception:
            confidence = 0.0
        evidence = item.get('evidence')
        if not isinstance(evidence, list):
            evidence = []
        evidence = [str(x)[:40] for x in evidence if str(x).strip()][:2]
        normalized.append({
            'entity': entity,
            'stance': stance,
            'sentiment': sentiment,
            'confidence': max(0.0, min(1.0, confidence)),
            'evidence': evidence,
        })

    return normalized

