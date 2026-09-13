"""
API 路由模块

提供新闻数据采集系统的 RESTful API 接口
"""

from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
import logging
import sys
import os
import json
from collections import Counter
import pandas as pd
import numpy as np
import threading
import re

from scrapers.db import DBHandler
from scrapers.config import load_config, update_config
from scrapers.data_cleaner import DataCleaner
from scrapers.model_builder import TextClassifier, ModelTrainer, BertClassifier, BertTextCNNClassifier, DeepLearningClassifier
from scrapers.llm_client import get_llm_config
from scrapers.sentiment_extractor import extract_entities, extract_stances
from scrapers.sentiment_labeler import llm_extract_entities, llm_extract_stances
from scrapers.event_aggregator import cluster_articles as cluster_event_articles, build_event_frame

api_bp = Blueprint('api', __name__)
logger = logging.getLogger(__name__)

# 数据库处理器（懒加载）
_db_handler = None

# 数据清洗器（全局）
_cleaner = None

# 分类器（全局）
_classifier = None

# 训练状态（全局）
_training_state = {
    'status': 'idle',  # idle, training, stopping, stopped, success, failed
    'progress': 0,
    'message': '',
    'logs': [],
    'stop_requested': False
}
_training_thread = None

# 应用状态（全局）
_applying_state = {
    'status': 'idle',  # idle, processing, success, failed
    'progress': 0,
    'message': '',
    'total': 0,
    'current': 0
}

_nlp_sentiment_state = {
    'status': 'idle',
    'progress': 0,
    'message': '',
    'total': 0,
    'current': 0,
    'last_error': ''
}
_nlp_sentiment_thread = None

_nlp_events_state = {
    'status': 'idle',
    'progress': 0,
    'message': '',
    'total': 0,
    'current': 0,
    'last_error': ''
}
_nlp_events_thread = None

MODEL_EVAL_TEST_SIZE = 0.2
MODEL_EVAL_RANDOM_STATE = 42
MODEL_DATA_LIMIT = 5000

# 自动持久化模型目录
SAVED_MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'saved_models')


class TrainingCancelledError(Exception):
    """训练任务被用户主动停止。"""


def append_training_log(message: str):
    """向训练状态追加一条带时间戳的日志。"""
    global _training_state

    _training_state['logs'].append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
    if len(_training_state['logs']) > 50:
        _training_state['logs'] = _training_state['logs'][-50:]


def ensure_training_not_cancelled():
    """检测是否收到停止训练请求。"""
    if _training_state.get('stop_requested'):
        raise TrainingCancelledError('训练已停止')


def coerce_metric_value(value):
    """将指标值规范为浮点数，缺失值返回 None"""
    if value is None:
        return None

    if isinstance(value, str):
        value = value.strip()
        if value == '':
            return None

    if isinstance(value, np.ndarray):
        if value.size == 0:
            return None
        value = value.reshape(-1)[-1]
    elif isinstance(value, (list, tuple)):
        if not value:
            return None
        value = value[-1]

    if hasattr(value, 'item'):
        try:
            value = value.item()
        except (TypeError, ValueError):
            pass

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_model_history_record(record):
    """规范化模型历史记录中的数值字段"""
    normalized = dict(record)
    normalized['accuracy'] = coerce_metric_value(normalized.get('accuracy'))
    normalized['f1_score'] = coerce_metric_value(normalized.get('f1_score'))
    normalized['precision'] = coerce_metric_value(normalized.get('precision'))
    normalized['recall'] = coerce_metric_value(normalized.get('recall'))
    normalized['train_accuracy'] = coerce_metric_value(normalized.get('train_accuracy'))
    normalized['validation_accuracy'] = coerce_metric_value(normalized.get('validation_accuracy'))

    if not isinstance(normalized.get('params'), dict):
        normalized['params'] = {}

    record_type = normalized.get('type') or 'train'
    metric_scope = normalized.get('metric_scope')
    if not metric_scope:
        metric_scope = 'test' if record_type == 'evaluate' else 'train'

    if record_type == 'train' and normalized['f1_score'] == 0 and normalized['precision'] is None and normalized['recall'] is None:
        normalized['f1_score'] = None

    scope_label_map = {
        'train': '训练集',
        'validation': '验证集',
        'test': '测试集'
    }

    normalized['type'] = record_type
    normalized['metric_scope'] = metric_scope
    normalized['scope_label'] = normalized.get('scope_label') or scope_label_map.get(metric_scope, metric_scope)
    normalized['is_ranked'] = bool(normalized.get('is_ranked', record_type == 'evaluate' and metric_scope in {'validation', 'test'}))
    normalized['auto_labeled_samples'] = int(normalized.get('auto_labeled_samples') or 0)
    normalized['deduplicated_samples'] = int(normalized.get('deduplicated_samples') or 0)
    normalized['class_count'] = int(normalized.get('class_count') or 0)

    return normalized


def extract_training_accuracy(result):
    """兼容不同训练器返回的准确率字段"""
    for key in ('train_accuracy', 'accuracy'):
        metric = coerce_metric_value(result.get(key))
        if metric is not None:
            return metric

    return None


def extract_validation_accuracy(result):
    """兼容不同训练器返回的验证准确率字段"""
    for key in ('final_val_acc', 'val_accuracy', 'validation_accuracy'):
        metric = coerce_metric_value(result.get(key))
        if metric is not None:
            return metric

    return None


def build_classifier_by_type(model_type: str):
    """按模型类型创建分类器实例。"""
    normalized_type = (model_type or 'svm').lower()

    if normalized_type == 'bert':
        classifier = BertClassifier()
    elif normalized_type == 'bert_textcnn':
        classifier = BertTextCNNClassifier()
    elif normalized_type in {'cnn', 'lstm'}:
        classifier = DeepLearningClassifier()
    else:
        classifier = TextClassifier()

    classifier.set_config({'model_type': normalized_type})
    return classifier


def detect_saved_model_type(filepath: str):
    """从模型文件或目录中推断模型类型。"""
    metadata_path = os.path.join(filepath, 'metadata.pkl') if os.path.isdir(filepath) else None

    if metadata_path and os.path.exists(metadata_path):
        try:
            import pickle

            with open(metadata_path, 'rb') as file_obj:
                metadata = pickle.load(file_obj)

            config = metadata.get('config') or {}
            model_type = config.get('model_type')
            if model_type:
                return str(model_type).lower()
        except Exception:
            pass

    normalized_path = filepath.replace('\\', '/').lower()
    if 'bert_textcnn' in normalized_path:
        return 'bert_textcnn'
    if 'bert' in normalized_path:
        return 'bert'
    if 'lstm' in normalized_path:
        return 'lstm'
    if 'cnn' in normalized_path:
        return 'cnn'
    if 'rf' in normalized_path or 'randomforest' in normalized_path:
        return 'rf'
    if 'nb' in normalized_path:
        return 'nb'
    if 'knn' in normalized_path:
        return 'knn'
    if 'lr' in normalized_path or 'logistic' in normalized_path:
        return 'lr'
    return 'svm'


def detect_saved_model_task(filepath: str) -> str:
    """从模型文件或目录中推断用途任务（nlp_task）。"""
    metadata_path = os.path.join(filepath, 'metadata.pkl') if os.path.isdir(filepath) else None
    if metadata_path and os.path.exists(metadata_path):
        try:
            import pickle
            with open(metadata_path, 'rb') as file_obj:
                metadata = pickle.load(file_obj)
            config = metadata.get('config') or {}
            task = config.get('nlp_task') or config.get('task')
            if task:
                return str(task)
        except Exception:
            pass

    if os.path.isfile(filepath) and filepath.lower().endswith('.pkl'):
        try:
            import pickle
            with open(filepath, 'rb') as file_obj:
                model_data = pickle.load(file_obj)
            if isinstance(model_data, dict):
                config = model_data.get('config') or {}
                task = config.get('nlp_task') or config.get('task')
                if task:
                    return str(task)
        except Exception:
            pass

    return 'content_classification'


def get_saved_model_display_name(filepath: str) -> str:
    metadata_path = os.path.join(filepath, 'metadata.pkl') if os.path.isdir(filepath) else None
    if metadata_path and os.path.exists(metadata_path):
        try:
            import pickle
            with open(metadata_path, 'rb') as file_obj:
                metadata = pickle.load(file_obj)
            config = metadata.get('config') or {}
            display_name = config.get('display_name') or config.get('name')
            if display_name:
                return str(display_name)
        except Exception:
            pass
    return os.path.basename(filepath.rstrip('\\/'))


def detect_saved_model_capabilities(filepath: str) -> dict:
    can_vectorize = False
    can_predict = False

    if os.path.isdir(filepath):
        metadata_path = os.path.join(filepath, 'metadata.pkl')
        if os.path.exists(metadata_path):
            can_predict = True
            try:
                import pickle
                with open(metadata_path, 'rb') as file_obj:
                    metadata = pickle.load(file_obj)
                if isinstance(metadata, dict) and metadata.get('vectorizer') is not None:
                    can_vectorize = True
                if isinstance(metadata, dict):
                    config = metadata.get('config') or {}
                    model_type = str(config.get('model_type') or '').lower()
                    if model_type == 'bert_textcnn' and os.path.exists(os.path.join(filepath, 'model_state.bin')):
                        can_vectorize = True
            except Exception:
                pass

        if os.path.exists(os.path.join(filepath, 'config.json')):
            can_vectorize = True
        if os.path.exists(os.path.join(filepath, 'model_state.bin')) and (
            os.path.exists(os.path.join(filepath, 'tokenizer.json')) or
            os.path.exists(os.path.join(filepath, 'tokenizer_config.json'))
        ):
            can_vectorize = True

        return {'can_vectorize': bool(can_vectorize), 'can_predict': bool(can_predict)}

    if os.path.isfile(filepath) and filepath.lower().endswith('.pkl'):
        try:
            import pickle
            with open(filepath, 'rb') as file_obj:
                model_data = pickle.load(file_obj)
            if isinstance(model_data, dict):
                can_predict = bool(model_data.get('model') is not None and model_data.get('label_encoder') is not None)
                can_vectorize = bool(model_data.get('vectorizer') is not None)
        except Exception:
            pass

    return {'can_vectorize': bool(can_vectorize), 'can_predict': bool(can_predict)}


def list_saved_models() -> list:
    project_root = os.path.dirname(os.path.dirname(__file__))
    models = []

    if not os.path.isdir(SAVED_MODELS_DIR):
        return models

    for name in sorted(os.listdir(SAVED_MODELS_DIR)):
        if name.startswith('.'):
            continue
        if name == 'pretrained':
            continue
        if name == 'nlp':
            continue
        full_path = os.path.join(SAVED_MODELS_DIR, name)
        if not (os.path.isdir(full_path) or os.path.isfile(full_path)):
            continue

        try:
            mtime = os.path.getmtime(full_path)
        except Exception:
            mtime = None

        model_type = detect_saved_model_type(full_path)
        task = detect_saved_model_task(full_path)
        display_name = get_saved_model_display_name(full_path)
        capabilities = detect_saved_model_capabilities(full_path)

        models.append({
            'name': name,
            'path': os.path.relpath(full_path, project_root).replace('\\', '/'),
            'model_type': model_type,
            'task': task,
            'display_name': display_name,
            'mtime': mtime,
            'capabilities': capabilities,
        })

    nlp_dir = os.path.join(SAVED_MODELS_DIR, 'nlp')
    if os.path.isdir(nlp_dir):
        for name in sorted(os.listdir(nlp_dir)):
            if name.startswith('.'):
                continue
            full_path = os.path.join(nlp_dir, name)
            try:
                mtime = os.path.getmtime(full_path)
            except Exception:
                mtime = None
            model_type = detect_saved_model_type(full_path)
            task = detect_saved_model_task(full_path)
            display_name = get_saved_model_display_name(full_path)
            capabilities = detect_saved_model_capabilities(full_path)
            models.append({
                'name': f"nlp/{name}",
                'path': os.path.relpath(full_path, project_root).replace('\\', '/'),
                'model_type': model_type,
                'task': task,
                'display_name': display_name,
                'mtime': mtime,
                'capabilities': capabilities,
            })

    models.sort(key=lambda item: (item.get('mtime') is None, -(item.get('mtime') or 0)))
    return models


def prepare_labeled_model_samples(db, cleaner, limit: int = MODEL_DATA_LIMIT):
    """加载、清洗并去重训练样本。"""
    query = f"""
    SELECT id, title, content, category
    FROM {db.get_table_name('raw_articles')}
    WHERE (category IS NOT NULL AND category != '')
       OR (title IS NOT NULL AND content IS NOT NULL)
    ORDER BY id ASC
    LIMIT %s
    """

    with db.get_connection_ctx() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (limit,))
            articles = cursor.fetchall()

    samples = []
    seen_texts = set()
    summary = {
        'total_articles': len(articles),
        'auto_labeled_samples': 0,
        'deduplicated_samples': 0,
        'empty_samples': 0,
        'short_samples': 0,
        'unlabeled_samples': 0,
        'class_distribution': {}
    }

    for article in articles:
        title = (article.get('title') or '').strip()
        content = (article.get('content') or '').strip()
        category = (article.get('category') or '').strip()

        combined = f"{title} {content}".strip()
        normalized_text = ' '.join(combined.split())

        if not normalized_text:
            summary['empty_samples'] += 1
            continue

        if len(normalized_text) < 10:
            summary['short_samples'] += 1
            continue

        if normalized_text in seen_texts:
            summary['deduplicated_samples'] += 1
            continue

        if not category or category == '未分类':
            category = cleaner.auto_label(normalized_text)
            if category:
                summary['auto_labeled_samples'] += 1

        if not category or category == '未分类':
            summary['unlabeled_samples'] += 1
            continue

        seen_texts.add(normalized_text)
        samples.append({
            'id': article.get('id'),
            'text': normalized_text,
            'label': category
        })

    summary['class_distribution'] = dict(Counter(sample['label'] for sample in samples))
    return samples, summary


def _fetch_recent_articles(db, *, days: int, limit: int):
    query = f"""
    SELECT id, title, content
    FROM {db.get_table_name('raw_articles')}
    WHERE crawl_time >= DATE_SUB(NOW(), INTERVAL %s DAY)
    ORDER BY crawl_time DESC
    LIMIT %s
    """
    with db.get_connection_ctx() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (int(days), int(limit)))
            return cursor.fetchall()


def _candidate_entities_from_article(cleaner: DataCleaner, *, title: str, content: str, top_k: int = 12):
    text = f"标题：{(title or '').strip()}\n正文：{(content or '').strip()}"
    text = text[:2000]

    candidates = []
    for pattern in [r'《([^》]{2,30})》', r'“([^”]{2,30})”', r'"([^"]{2,30})"', r'（([^）]{2,30})）', r'\(([^)]{2,30})\)']:
        for match in re.findall(pattern, text):
            s = str(match).strip()
            if s and s not in candidates:
                candidates.append(s)

    try:
        keywords = cleaner.extract_keywords(text.replace('\n', ' '), top_k=max(1, int(top_k)))
    except Exception:
        keywords = []

    for kw in keywords:
        kw = str(kw).strip()
        if kw and kw not in candidates:
            candidates.append(kw)

    return candidates[:max(1, int(top_k))]


def prepare_sentiment_entity_samples(db, cleaner, *, days: int, limit: int, max_entities: int = 3, candidate_top_k: int = 12):
    articles = _fetch_recent_articles(db, days=days, limit=limit)
    samples = []
    seen = set()
    summary = {
        'total_articles': len(articles),
        'auto_labeled_samples': 0,
        'deduplicated_samples': 0,
        'empty_samples': 0,
        'short_samples': 0,
        'unlabeled_samples': 0,
        'class_distribution': {},
    }

    for row in articles:
        title = (row.get('title') or '').strip()
        content = (row.get('content') or '').strip()
        combined = f"{title} {content}".strip()
        normalized_text = ' '.join(combined.split())
        if not normalized_text:
            summary['empty_samples'] += 1
            continue
        if len(normalized_text) < 20:
            summary['short_samples'] += 1
            continue

        entities = llm_extract_entities(title=title, content=content, max_entities=max_entities)
        if not entities:
            summary['unlabeled_samples'] += 1
            continue
        summary['auto_labeled_samples'] += 1

        gold = set()
        for ent in entities:
            gold.add(str(ent.get('name') or '').strip())
            aliases = ent.get('aliases') if isinstance(ent.get('aliases'), list) else []
            for a in aliases:
                gold.add(str(a).strip())
        gold = {g for g in gold if g}

        candidates = _candidate_entities_from_article(cleaner, title=title, content=content, top_k=candidate_top_k)
        for cand in candidates:
            cand = str(cand).strip()
            if not cand:
                continue
            text = f"标题：{title}\n正文：{content}\n候选主体：{cand}"
            text = ' '.join(text.split())
            if text in seen:
                summary['deduplicated_samples'] += 1
                continue
            seen.add(text)
            label = 'keep' if cand in gold else 'drop'
            samples.append({'id': row.get('id'), 'text': text, 'label': label})

    summary['class_distribution'] = dict(Counter(sample['label'] for sample in samples))
    return samples, summary


def prepare_sentiment_stance_samples(db, cleaner, *, days: int, limit: int, max_entities: int = 3):
    articles = _fetch_recent_articles(db, days=days, limit=limit)
    samples = []
    seen = set()
    summary = {
        'total_articles': len(articles),
        'auto_labeled_samples': 0,
        'deduplicated_samples': 0,
        'empty_samples': 0,
        'short_samples': 0,
        'unlabeled_samples': 0,
        'class_distribution': {},
    }

    for row in articles:
        title = (row.get('title') or '').strip()
        content = (row.get('content') or '').strip()
        combined = f"{title} {content}".strip()
        normalized_text = ' '.join(combined.split())
        if not normalized_text:
            summary['empty_samples'] += 1
            continue
        if len(normalized_text) < 20:
            summary['short_samples'] += 1
            continue

        entities = llm_extract_entities(title=title, content=content, max_entities=max_entities)
        stances = llm_extract_stances(title=title, content=content, entities=entities)
        if not stances:
            summary['unlabeled_samples'] += 1
            continue
        summary['auto_labeled_samples'] += 1

        for item in stances:
            entity = str(item.get('entity') or '').strip()
            stance = str(item.get('stance') or '').strip()
            if not entity or not stance:
                continue
            text = f"标题：{title}\n正文：{content}\n主体：{entity}"
            text = ' '.join(text.split())
            if text in seen:
                summary['deduplicated_samples'] += 1
                continue
            seen.add(text)
            samples.append({'id': row.get('id'), 'text': text, 'label': stance})

    summary['class_distribution'] = dict(Counter(sample['label'] for sample in samples))
    return samples, summary


def prepare_sentiment_sentiment_samples(db, cleaner, *, days: int, limit: int, max_entities: int = 3):
    articles = _fetch_recent_articles(db, days=days, limit=limit)
    samples = []
    seen = set()
    summary = {
        'total_articles': len(articles),
        'auto_labeled_samples': 0,
        'deduplicated_samples': 0,
        'empty_samples': 0,
        'short_samples': 0,
        'unlabeled_samples': 0,
        'class_distribution': {},
    }

    for row in articles:
        title = (row.get('title') or '').strip()
        content = (row.get('content') or '').strip()
        combined = f"{title} {content}".strip()
        normalized_text = ' '.join(combined.split())
        if not normalized_text:
            summary['empty_samples'] += 1
            continue
        if len(normalized_text) < 20:
            summary['short_samples'] += 1
            continue

        entities = llm_extract_entities(title=title, content=content, max_entities=max_entities)
        stances = llm_extract_stances(title=title, content=content, entities=entities)
        if not stances:
            summary['unlabeled_samples'] += 1
            continue
        summary['auto_labeled_samples'] += 1

        for item in stances:
            entity = str(item.get('entity') or '').strip()
            sentiment = str(item.get('sentiment') or '').strip()
            if not entity or not sentiment:
                continue
            text = f"标题：{title}\n正文：{content}\n主体：{entity}"
            text = ' '.join(text.split())
            if text in seen:
                summary['deduplicated_samples'] += 1
                continue
            seen.add(text)
            samples.append({'id': row.get('id'), 'text': text, 'label': sentiment})

    summary['class_distribution'] = dict(Counter(sample['label'] for sample in samples))
    return samples, summary


def split_model_samples(samples, test_size: float = MODEL_EVAL_TEST_SIZE, random_state: int = MODEL_EVAL_RANDOM_STATE):
    """按固定随机种子划分训练集和测试集，并确保稀有类别保留在训练集。"""
    from sklearn.model_selection import train_test_split

    if len(samples) < 10:
        raise ValueError('有效样本太少，至少需要 10 条数据才能完成训练与评估')

    label_counter = Counter(sample['label'] for sample in samples)
    if len(label_counter) < 2:
        raise ValueError('至少需要 2 个分类才能进行模型训练')

    rare_train_samples = []
    splittable_samples = []
    for sample in samples:
        if label_counter[sample['label']] < 2:
            rare_train_samples.append(sample)
        else:
            splittable_samples.append(sample)

    if len(splittable_samples) < 2:
        raise ValueError('可用于评估的有效样本不足，请补充标注数据后重试')

    splittable_labels = [sample['label'] for sample in splittable_samples]
    unique_splittable_labels = len(set(splittable_labels))
    proposed_test_count = max(int(round(len(splittable_samples) * test_size)), 1)
    if unique_splittable_labels > 1:
        proposed_test_count = max(proposed_test_count, unique_splittable_labels)
    if proposed_test_count >= len(splittable_samples):
        proposed_test_count = max(1, len(splittable_samples) - 1)

    stratify_labels = None
    if unique_splittable_labels > 1 and proposed_test_count < len(splittable_samples):
        stratify_labels = splittable_labels

    train_samples, test_samples = train_test_split(
        splittable_samples,
        test_size=proposed_test_count,
        random_state=random_state,
        stratify=stratify_labels
    )

    train_samples = sorted(rare_train_samples + train_samples, key=lambda item: item['id'] or 0)
    test_samples = sorted(test_samples, key=lambda item: item['id'] or 0)

    return {
        'train_samples': train_samples,
        'test_samples': test_samples,
        'train_texts': [sample['text'] for sample in train_samples],
        'train_labels': [sample['label'] for sample in train_samples],
        'test_texts': [sample['text'] for sample in test_samples],
        'test_labels': [sample['label'] for sample in test_samples],
        'stratified': bool(stratify_labels),
        'rare_class_samples': len(rare_train_samples),
        'class_distribution': dict(label_counter)
    }


def filter_known_labels(classifier, texts, labels):
    """过滤掉当前分类器标签编码器无法识别的标签。"""
    label_encoder = getattr(classifier, 'label_encoder', None)
    known_label_values = getattr(label_encoder, 'classes_', None)

    if known_label_values is None:
        known_label_values = getattr(classifier, 'categories', None) or []
    elif isinstance(known_label_values, np.ndarray):
        known_label_values = known_label_values.tolist()
    else:
        known_label_values = list(known_label_values)

    known_labels = set(known_label_values)
    if not known_labels:
        return texts, labels, 0

    filtered_texts = []
    filtered_labels = []
    skipped = 0
    for text, label in zip(texts, labels):
        if label in known_labels:
            filtered_texts.append(text)
            filtered_labels.append(label)
        else:
            skipped += 1

    return filtered_texts, filtered_labels, skipped

def save_model_history(record):
    """保存模型历史记录"""
    try:
        project_root = os.path.dirname(os.path.dirname(__file__))
        log_dir = os.path.join(project_root, 'logs')
        os.makedirs(log_dir, exist_ok=True)
        history_path = os.path.join(log_dir, 'model_history.json')
        
        history = []
        if os.path.exists(history_path):
            try:
                with open(history_path, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except Exception:
                pass
        
        # 添加新记录
        normalized_record = normalize_model_history_record(record)
        normalized_record['timestamp'] = datetime.now().isoformat()
        history.append(normalized_record)
        
        # 保留最近 50 条
        if len(history) > 50:
            history = history[-50:]
            
        with open(history_path, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        logger.exception("保存模型历史记录失败: %s", e)

def get_db():
    """获取数据库处理器"""
    global _db_handler
    if _db_handler is None:
        config = load_config()
        db_config = config.get('database', {})
        _db_handler = DBHandler(db_config)
    return _db_handler


def get_cleaner():
    """获取数据清洗器"""
    global _cleaner
    if _cleaner is None:
        _cleaner = DataCleaner()
    return _cleaner


def auto_save_model(classifier, *, subdir: str = None, filename_prefix: str = 'latest'):
    """训练完成后自动保存模型到磁盘"""
    try:
        base_dir = SAVED_MODELS_DIR
        if subdir:
            base_dir = os.path.join(SAVED_MODELS_DIR, str(subdir))
        os.makedirs(base_dir, exist_ok=True)
        model_type = classifier.config.get('model_type', 'svm')
        if model_type in ('bert', 'bert_textcnn', 'cnn', 'lstm'):
            save_path = os.path.join(base_dir, f'{filename_prefix}_{model_type}')
        else:
            save_path = os.path.join(base_dir, f'{filename_prefix}_{model_type}.pkl')
        classifier.save(save_path)
        logger.info("[AutoSave] 模型已自动保存到: %s", save_path)
    except Exception as e:
        logger.exception("[AutoSave] 自动保存模型失败: %s", e)


def auto_load_model():
    """启动时自动加载最近保存的模型，成功返回 classifier，失败返回 None"""
    try:
        if not os.path.isdir(SAVED_MODELS_DIR):
            return None

        candidates = []
        for name in os.listdir(SAVED_MODELS_DIR):
            if not name.startswith('latest_'):
                continue
            full_path = os.path.join(SAVED_MODELS_DIR, name)
            mtime = os.path.getmtime(full_path)
            candidates.append((full_path, mtime))

        if not candidates:
            return None

        # 从新到旧依次尝试，遇到损坏或旧格式模型时自动跳过
        for best_path, _ in sorted(candidates, key=lambda item: item[1], reverse=True):
            try:
                model_type = detect_saved_model_type(best_path)
                classifier = build_classifier_by_type(model_type)
                classifier.load(best_path)
                if not classifier.is_ready():
                    raise ValueError('模型核心组件缺失')
                logger.info("[AutoLoad] 已自动加载模型: %s (类型: %s)", best_path, model_type)
                return classifier
            except Exception as load_err:
                logger.warning("[AutoLoad] 跳过不可用模型 %s: %s", best_path, load_err)

        return None
    except Exception as e:
        logger.exception("[AutoLoad] 自动加载模型失败: %s", e)
        return None


def get_classifier():
    """获取分类器，优先自动加载已持久化的模型"""
    global _classifier
    if _classifier is None:
        _classifier = auto_load_model()
    if _classifier is None:
        _classifier = TextClassifier()
    return _classifier


# ==================== 仪表盘接口 ====================

@api_bp.route('/dashboard/stats', methods=['GET'])
def dashboard_stats():
    """获取仪表盘统计数据"""
    try:
        db = get_db()
        
        # 统计数据
        stats = {
            'total_articles': 0,
            'today_articles': 0,
            'domestic_count': 0,
            'sources_count': 0,
            'recent_logs': []
        }
        
        # 获取总文章数
        try:
            query = f"SELECT COUNT(*) as total FROM {db.get_table_name('raw_articles')}"
            with db.get_connection_ctx() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    result = cursor.fetchone()
                    stats['total_articles'] = int(result['total'] or 0)
        except Exception as e:
            logger.warning("查询总文章数失败: %s", e)
        
        # 获取今日文章数
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            query = f"SELECT COUNT(*) as total FROM {db.get_table_name('raw_articles')} WHERE DATE(crawl_time) = %s"
            with db.get_connection_ctx() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, (today,))
                    result = cursor.fetchone()
                    stats['today_articles'] = int(result['total'] or 0)
        except Exception as e:
            logger.warning("查询今日文章数失败: %s", e)
        
        # 获取来源统计
        sources = db.get_all_sources()
        stats['sources_count'] = len(sources)
        
        # 按类型统计
        source_types = {'domestic': 0}
        for source in sources:
            stype = source.get('source_type')
            if stype in source_types:
                source_types[stype] += 1
        
        stats['domestic_count'] = source_types['domestic']
        
        return jsonify({
            'success': True,
            'data': stats
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==================== 可视化接口（前台仪表盘） ====================

def clamp_int(value, default, min_value, max_value):
    try:
        v = int(value)
    except Exception:
        v = default
    return max(min_value, min(max_value, v))


@api_bp.route('/visualize/category-hour-matrix', methods=['GET'])
def visualize_category_hour_matrix():
    try:
        db = get_db()

        days = clamp_int(request.args.get('days'), 7, 1, 90)
        start_dt = datetime.now() - timedelta(days=days)

        table_name = db.get_table_name('raw_articles')
        query = f"""
            SELECT
                category,
                HOUR(COALESCE(publish_time, crawl_time)) AS hour_bucket,
                COUNT(*) AS cnt
            FROM {table_name}
            WHERE crawl_time >= %s
              AND category IS NOT NULL
              AND category <> ''
            GROUP BY category, hour_bucket
        """

        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (start_dt,))
                rows = cursor.fetchall()

        if not rows:
            return jsonify({
                'success': True,
                'data': {
                    'days': days,
                    'categories': [],
                    'hours': list(range(24)),
                    'data': []
                }
            })

        totals = {}
        for row in rows:
            cat = row.get('category') or ''
            cnt = int(row.get('cnt') or 0)
            totals[cat] = totals.get(cat, 0) + cnt

        categories = [k for k, _ in sorted(totals.items(), key=lambda item: item[1], reverse=True)]
        category_index = {cat: idx for idx, cat in enumerate(categories)}

        data = []
        for row in rows:
            cat = row.get('category') or ''
            hour_bucket = row.get('hour_bucket')
            if hour_bucket is None:
                continue
            try:
                hour_bucket = int(hour_bucket)
            except Exception:
                continue
            if hour_bucket < 0 or hour_bucket > 23:
                continue
            cnt = int(row.get('cnt') or 0)
            idx = category_index.get(cat)
            if idx is None:
                continue
            data.append([idx, hour_bucket, cnt])

        return jsonify({
            'success': True,
            'data': {
                'days': days,
                'categories': categories,
                'hours': list(range(24)),
                'data': data
            }
        })
    except Exception as e:
        logger.exception("visualize_category_hour_matrix 执行失败: %s", e)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/visualize/content-length-ratio', methods=['GET'])
def visualize_content_length_ratio():
    try:
        db = get_db()

        days = clamp_int(request.args.get('days'), 7, 1, 90)
        threshold = clamp_int(request.args.get('threshold'), 200, 50, 5000)
        start_dt = datetime.now() - timedelta(days=days)

        table_name = db.get_table_name('raw_articles')
        query = f"""
            SELECT
                SUM(CASE WHEN (CHAR_LENGTH(COALESCE(title, '')) + CHAR_LENGTH(COALESCE(content, ''))) < %s THEN 1 ELSE 0 END) AS short_count,
                SUM(CASE WHEN (CHAR_LENGTH(COALESCE(title, '')) + CHAR_LENGTH(COALESCE(content, ''))) >= %s THEN 1 ELSE 0 END) AS long_count,
                COUNT(*) AS total
            FROM {table_name}
            WHERE crawl_time >= %s
        """

        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (threshold, threshold, start_dt))
                row = cursor.fetchone() or {}

        short_count = int(row.get('short_count') or 0)
        long_count = int(row.get('long_count') or 0)
        total = int(row.get('total') or 0)

        return jsonify({
            'success': True,
            'data': {
                'days': days,
                'threshold': threshold,
                'short_count': short_count,
                'long_count': long_count,
                'total': total
            }
        })
    except Exception as e:
        logger.exception("visualize_content_length_ratio 执行失败: %s", e)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/visualize/source-share', methods=['GET'])
def visualize_source_share():
    try:
        db = get_db()

        days = clamp_int(request.args.get('days'), 7, 1, 90)
        top_n = clamp_int(request.args.get('top_n'), 8, 3, 20)
        category = (request.args.get('category') or '').strip()
        category = category if category else None
        date_str = (request.args.get('date') or '').strip()
        date_value = None
        if date_str:
            try:
                date_value = datetime.strptime(date_str, '%Y-%m-%d').date()
            except Exception:
                date_value = None

        start_dt = datetime.now() - timedelta(days=days)

        table_name = db.get_table_name('raw_articles')
        where_clauses = ["crawl_time >= %s"]
        params = [start_dt]
        if category:
            where_clauses.append("category = %s")
            params.append(category)
        if date_value:
            where_clauses.append("DATE(COALESCE(publish_time, crawl_time)) = %s")
            params.append(date_value.strftime('%Y-%m-%d'))

        where_sql = " AND ".join(where_clauses)
        query = f"""
            SELECT
                COALESCE(source_name, '') AS source_name,
                COUNT(*) AS cnt
            FROM {table_name}
            WHERE {where_sql}
            GROUP BY COALESCE(source_name, '')
            ORDER BY cnt DESC
        """

        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall()

        items = []
        other_count = 0
        for idx, row in enumerate(rows or []):
            name = (row.get('source_name') or '').strip() or '未知来源'
            cnt = int(row.get('cnt') or 0)
            if idx < top_n:
                items.append({'name': name, 'value': cnt})
            else:
                other_count += cnt

        if other_count > 0:
            items.append({'name': '其他', 'value': other_count})

        return jsonify({
            'success': True,
            'data': {
                'days': days,
                'top_n': top_n,
                'category': category,
                'date': date_str if date_value else None,
                'items': items
            }
        })
    except Exception as e:
        logger.exception("visualize_source_share 执行失败: %s", e)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/visualize/category-trends', methods=['GET'])
def visualize_category_trends():
    try:
        db = get_db()

        days = clamp_int(request.args.get('days'), 30, 1, 90)
        top_n = clamp_int(request.args.get('top_n'), 8, 3, 20)

        start_date = (datetime.now() - timedelta(days=days - 1)).date()
        start_dt = datetime.combine(start_date, datetime.min.time())

        table_name = db.get_table_name('raw_articles')

        top_query = f"""
            SELECT category, COUNT(*) AS cnt
            FROM {table_name}
            WHERE crawl_time >= %s
              AND category IS NOT NULL
              AND category <> ''
            GROUP BY category
            ORDER BY cnt DESC
            LIMIT %s
        """

        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                cursor.execute(top_query, (start_dt, top_n))
                top_rows = cursor.fetchall()

        top_categories = [(r.get('category') or '').strip() for r in (top_rows or [])]
        top_categories = [c for c in top_categories if c]
        top_set = set(top_categories)

        daily_query = f"""
            SELECT
                DATE(crawl_time) AS d,
                category,
                COUNT(*) AS cnt
            FROM {table_name}
            WHERE crawl_time >= %s
              AND category IS NOT NULL
              AND category <> ''
            GROUP BY DATE(crawl_time), category
        """

        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                cursor.execute(daily_query, (start_dt,))
                rows = cursor.fetchall()

        if not rows or not top_categories:
            return jsonify({
                'success': True,
                'data': {
                    'days': days,
                    'top_n': top_n,
                    'dates': [],
                    'series': []
                }
            })

        min_d = None
        max_d = None
        for row in rows:
            d = row.get('d')
            if d is None:
                continue
            if hasattr(d, 'date'):
                d = d.date()
            if not hasattr(d, 'strftime'):
                continue
            if min_d is None or d < min_d:
                min_d = d
            if max_d is None or d > max_d:
                max_d = d

        if min_d is None or max_d is None:
            return jsonify({
                'success': True,
                'data': {
                    'days': days,
                    'top_n': top_n,
                    'dates': [],
                    'series': []
                }
            })

        dates = []
        cur = min_d
        while cur <= max_d:
            dates.append(cur.strftime('%Y-%m-%d'))
            cur = cur + timedelta(days=1)

        per_day = {d: {} for d in dates}
        other_name = '其他'

        for row in rows:
            d = row.get('d')
            if d is None:
                continue
            day_key = d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)
            if day_key not in per_day:
                continue
            cat = (row.get('category') or '').strip()
            cnt = int(row.get('cnt') or 0)
            if not cat:
                continue
            if cat in top_set:
                per_day[day_key][cat] = per_day[day_key].get(cat, 0) + cnt
            else:
                per_day[day_key][other_name] = per_day[day_key].get(other_name, 0) + cnt

        series = []
        for cat in top_categories:
            series.append({
                'name': cat,
                'data': [int(per_day[d].get(cat, 0)) for d in dates]
            })

        other_total = sum(int(per_day[d].get(other_name, 0)) for d in dates)
        if other_total > 0:
            series.append({
                'name': other_name,
                'data': [int(per_day[d].get(other_name, 0)) for d in dates]
            })

        return jsonify({
            'success': True,
            'data': {
                'days': days,
                'top_n': top_n,
                'dates': dates,
                'series': series
            }
        })
    except Exception as e:
        logger.exception("visualize_category_trends 执行失败: %s", e)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/visualize/info-density', methods=['GET'])
def visualize_info_density():
    try:
        db = get_db()
        cleaner = get_cleaner()

        days = clamp_int(request.args.get('days'), 30, 1, 90)
        top_n = clamp_int(request.args.get('top_n'), 8, 3, 20)
        sample_limit = 2000

        start_dt = datetime.now() - timedelta(days=days)
        table_name = db.get_table_name('raw_articles')

        query = f"""
            SELECT category, title, content
            FROM {table_name}
            WHERE crawl_time >= %s
              AND category IS NOT NULL
              AND category <> ''
            ORDER BY crawl_time DESC
            LIMIT %s
        """

        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (start_dt, sample_limit))
                rows = cursor.fetchall()

        if not rows:
            return jsonify({
                'success': True,
                'data': {
                    'days': days,
                    'top_n': top_n,
                    'sample_size': 0,
                    'items': []
                }
            })

        agg = {}
        sample_size = 0

        for row in rows:
            cat = (row.get('category') or '').strip()
            if not cat:
                continue
            text = f"{row.get('title') or ''} {row.get('content') or ''}"
            chars = len(text)
            tokens = cleaner.segment(str(text))
            tokens = cleaner.remove_stopwords(tokens)
            total_tokens = len(tokens)
            if total_tokens <= 0:
                continue
            unique_tokens = len(set(tokens))
            density = unique_tokens / total_tokens
            sample_size += 1

            if cat not in agg:
                agg[cat] = {
                    'count': 0,
                    'sum_density': 0.0,
                    'sum_tokens': 0,
                    'sum_unique_tokens': 0,
                    'sum_chars': 0
                }
            a = agg[cat]
            a['count'] += 1
            a['sum_density'] += float(density)
            a['sum_tokens'] += int(total_tokens)
            a['sum_unique_tokens'] += int(unique_tokens)
            a['sum_chars'] += int(chars)

        if not agg:
            return jsonify({
                'success': True,
                'data': {
                    'days': days,
                    'top_n': top_n,
                    'sample_size': sample_size,
                    'items': []
                }
            })

        ranked = sorted(agg.items(), key=lambda item: item[1].get('count', 0), reverse=True)[:top_n]
        items = []
        for cat, a in ranked:
            count = int(a.get('count') or 0)
            if count <= 0:
                continue
            items.append({
                'category': cat,
                'count': count,
                'avg_density': float(a.get('sum_density', 0.0)) / count,
                'avg_tokens': float(a.get('sum_tokens', 0)) / count,
                'avg_unique_tokens': float(a.get('sum_unique_tokens', 0)) / count,
                'avg_chars': float(a.get('sum_chars', 0)) / count
            })

        return jsonify({
            'success': True,
            'data': {
                'days': days,
                'top_n': top_n,
                'sample_size': sample_size,
                'items': items
            }
        })
    except Exception as e:
        logger.exception("visualize_info_density 执行失败: %s", e)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/visualize/representative-news', methods=['GET'])
def visualize_representative_news():
    try:
        db = get_db()

        category = (request.args.get('category') or '').strip()
        date_str = (request.args.get('date') or '').strip()
        limit = clamp_int(request.args.get('limit'), 10, 5, 50)

        if not category or not date_str:
            return jsonify({
                'success': False,
                'error': '缺少参数：category、date'
            }), 400

        try:
            date_value = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            return jsonify({
                'success': False,
                'error': 'date 格式错误，应为 YYYY-MM-DD'
            }), 400

        table_name = db.get_table_name('raw_articles')
        query = f"""
            SELECT
                id,
                title,
                source_name,
                publish_time,
                crawl_time
            FROM {table_name}
            WHERE category = %s
              AND DATE(COALESCE(publish_time, crawl_time)) = %s
            ORDER BY COALESCE(publish_time, crawl_time) DESC
            LIMIT %s
        """

        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (category, date_value.strftime('%Y-%m-%d'), limit))
                rows = cursor.fetchall()

        return jsonify({
            'success': True,
            'data': {
                'category': category,
                'date': date_str,
                'limit': limit,
                'items': rows or []
            }
        })
    except Exception as e:
        logger.exception("visualize_representative_news 执行失败: %s", e)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/visualize/category-similarity', methods=['GET'])
def visualize_category_similarity():
    try:
        db = get_db()
        cleaner = get_cleaner()

        days = clamp_int(request.args.get('days'), 30, 1, 90)
        top_words = clamp_int(request.args.get('top_words'), 80, 30, 200)
        min_count = clamp_int(request.args.get('min_count'), 20, 5, 200)
        sample_limit = 5000

        start_dt = datetime.now() - timedelta(days=days)
        table_name = db.get_table_name('raw_articles')

        query = f"""
            SELECT category, title, content
            FROM {table_name}
            WHERE crawl_time >= %s
              AND category IS NOT NULL
              AND category <> ''
            ORDER BY crawl_time DESC
            LIMIT %s
        """

        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (start_dt, sample_limit))
                rows = cursor.fetchall()

        if not rows:
            return jsonify({
                'success': True,
                'data': {
                    'days': days,
                    'top_words': top_words,
                    'min_count': min_count,
                    'sample_size': 0,
                    'categories': [],
                    'data': []
                }
            })

        cat_counters = {}
        cat_doc_counts = {}
        sample_size = 0

        for row in rows:
            cat = (row.get('category') or '').strip()
            if not cat:
                continue
            text = f"{row.get('title') or ''} {row.get('content') or ''}"
            tokens = cleaner.segment(str(text))
            tokens = cleaner.remove_stopwords(tokens)
            if not tokens:
                continue
            sample_size += 1
            if cat not in cat_counters:
                cat_counters[cat] = Counter()
                cat_doc_counts[cat] = 0
            cat_doc_counts[cat] += 1
            cat_counters[cat].update(tokens)

        categories = [c for c, cnt in sorted(cat_doc_counts.items(), key=lambda x: x[1], reverse=True) if cnt >= min_count]
        if len(categories) < 2:
            return jsonify({
                'success': True,
                'data': {
                    'days': days,
                    'top_words': top_words,
                    'min_count': min_count,
                    'sample_size': sample_size,
                    'categories': categories,
                    'data': []
                }
            })

        global_counter = Counter()
        for cat in categories:
            global_counter.update(cat_counters.get(cat, Counter()))
        vocab = [w for w, _ in global_counter.most_common(top_words)]
        if not vocab:
            return jsonify({
                'success': True,
                'data': {
                    'days': days,
                    'top_words': top_words,
                    'min_count': min_count,
                    'sample_size': sample_size,
                    'categories': categories,
                    'data': []
                }
            })

        vectors = []
        for cat in categories:
            counter = cat_counters.get(cat, Counter())
            vec = [float(counter.get(w, 0)) for w in vocab]
            norm = sum(v * v for v in vec) ** 0.5
            if norm > 0:
                vec = [v / norm for v in vec]
            vectors.append(vec)

        data = []
        n = len(categories)
        for i in range(n):
            vi = vectors[i]
            for j in range(n):
                vj = vectors[j]
                sim = 0.0
                for k in range(len(vocab)):
                    sim += vi[k] * vj[k]
                data.append([i, j, float(sim)])

        return jsonify({
            'success': True,
            'data': {
                'days': days,
                'top_words': top_words,
                'min_count': min_count,
                'sample_size': sample_size,
                'categories': categories,
                'data': data
            }
        })
    except Exception as e:
        logger.exception("visualize_category_similarity 执行失败: %s", e)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/visualize/keyword-trends', methods=['GET'])
def visualize_keyword_trends():
    try:
        db = get_db()
        cleaner = get_cleaner()

        days = clamp_int(request.args.get('days'), 14, 1, 90)
        top_k = clamp_int(request.args.get('top_k'), 5, 1, 10)
        category = (request.args.get('category') or '').strip()
        category = category if category else None
        sample_limit = 2000

        end_date = datetime.now().date()
        start_date = (datetime.now() - timedelta(days=days - 1)).date()
        start_dt = datetime.combine(start_date, datetime.min.time())

        table_name = db.get_table_name('raw_articles')
        if category:
            query = f"""
                SELECT
                    DATE(COALESCE(publish_time, crawl_time)) AS d,
                    title,
                    content
                FROM {table_name}
                WHERE crawl_time >= %s
                  AND category = %s
                ORDER BY crawl_time DESC
                LIMIT %s
            """
            params = (start_dt, category, sample_limit)
        else:
            query = f"""
                SELECT
                    DATE(COALESCE(publish_time, crawl_time)) AS d,
                    title,
                    content
                FROM {table_name}
                WHERE crawl_time >= %s
                ORDER BY crawl_time DESC
                LIMIT %s
            """
            params = (start_dt, sample_limit)

        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()

        dates = []
        cur = start_date
        while cur <= end_date:
            dates.append(cur.strftime('%Y-%m-%d'))
            cur = cur + timedelta(days=1)

        if not rows:
            return jsonify({
                'success': True,
                'data': {
                    'days': days,
                    'category': category,
                    'top_k': top_k,
                    'dates': dates,
                    'keywords': [],
                    'series': [],
                    'sample_size': 0
                }
            })

        overall_counter = Counter()
        per_day_counters = {}

        for row in rows:
            d = row.get('d')
            if d is None:
                continue
            if hasattr(d, 'strftime'):
                day_key = d.strftime('%Y-%m-%d')
            else:
                day_key = str(d)

            text = f"{row.get('title') or ''} {row.get('content') or ''}"
            tokens = cleaner.segment(str(text))
            tokens = cleaner.remove_stopwords(tokens)
            if not tokens:
                continue

            overall_counter.update(tokens)
            if day_key not in per_day_counters:
                per_day_counters[day_key] = Counter()
            per_day_counters[day_key].update(tokens)

        top_words = [w for w, _ in overall_counter.most_common(top_k)]

        series = []
        for word in top_words:
            series.append({
                'name': word,
                'data': [int(per_day_counters.get(d, Counter()).get(word, 0)) for d in dates]
            })

        return jsonify({
            'success': True,
            'data': {
                'days': days,
                'category': category,
                'top_k': top_k,
                'dates': dates,
                'keywords': top_words,
                'series': series,
                'sample_size': len(rows)
            }
        })
    except Exception as e:
        logger.exception("visualize_keyword_trends 执行失败: %s", e)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==================== 新闻接口 ====================

@api_bp.route('/news/list', methods=['GET'])
def get_news_list():
    """获取新闻列表"""
    try:
        db = get_db()
        
        # 获取查询参数
        source_type = request.args.get('type')  # domestic
        source_code = request.args.get('source')  # source code like 'sina', 'netease'
        category = request.args.get('category')
        limit = request.args.get('limit', 100, type=int)
        page = request.args.get('page', 1, type=int)
        offset = (page - 1) * limit
        
        articles = db.get_recent_articles(limit=limit, offset=offset, source_type=source_type, category=category, source_code=source_code)
        
        return jsonify({
            'success': True,
            'data': {
                'items': articles,
                'page': page,
                'limit': limit,
                'total': len(articles)
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/news/detail/<int:article_id>', methods=['GET'])
def get_news_detail(article_id):
    """获取新闻详情"""
    try:
        db = get_db()
        
        query = f"SELECT * FROM {db.get_table_name('raw_articles')} WHERE id = %s"
        
        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (article_id,))
                article = cursor.fetchone()
        
        if not article:
            return jsonify({
                'success': False,
                'error': '文章不存在'
            }), 404
        
        return jsonify({
            'success': True,
            'data': article
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==================== 来源接口 ====================

@api_bp.route('/sources', methods=['GET'])
def get_sources():
    """获取所有来源"""
    try:
        db = get_db()
        source_type = request.args.get('type')
        
        sources = db.get_all_sources(source_type)
        
        return jsonify({
            'success': True,
            'data': sources
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==================== 日志接口 ====================

@api_bp.route('/logs', methods=['GET'])
def get_logs():
    """获取爬虫执行日志"""
    try:
        db = get_db()
        
        limit = request.args.get('limit', 100, type=int)
        
        query = f"""
        SELECT * FROM {db.get_table_name('spider_logs')}
        ORDER BY start_time DESC
        LIMIT %s
        """
        
        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (limit,))
                logs = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'data': logs
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/logs/stats', methods=['GET'])
def get_log_stats():
    """获取日志统计"""
    try:
        db = get_db()
        
        # 统计今日执行情况
        today = datetime.now().strftime('%Y-%m-%d')
        
        query = f"""
        SELECT 
            COUNT(*) as total_runs,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_count,
            SUM(items_count) as total_items,
            AVG(duration) as avg_duration
        FROM {db.get_table_name('spider_logs')}
        WHERE DATE(start_time) = %s
        """
        
        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (today,))
                stats = cursor.fetchone()
        
        return jsonify({
            'success': True,
            'data': {
                'date': today,
                'total_runs': int(stats['total_runs'] or 0),
                'success_count': int(stats['success_count'] or 0),
                'failed_count': int(stats['failed_count'] or 0),
                'total_items': int(stats['total_items'] or 0),
                'avg_duration': round(float(stats['avg_duration'] or 0), 2)
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==================== 爬虫控制接口 ====================

@api_bp.route('/spider/list', methods=['GET'])
def get_spider_list():
    """获取所有可用的爬虫列表"""
    try:
        from scrapers import get_domestic_scrapers

        spiders = []

        # 国内新闻爬虫
        for spider in get_domestic_scrapers():
            spiders.append({
                'name': spider['name'],
                'description': spider['description'],
                'type': 'domestic',
                'type_name': '国内新闻'
            })

        return jsonify({
            'success': True,
            'data': spiders
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/spider/start', methods=['POST'])
def start_spider():
    """启动爬虫"""
    try:
        data = request.get_json() or {}
        spider_name = data.get('spider_name')
        spider_type = data.get('spider_type', 'domestic')

        if not spider_name:
            return jsonify({
                'success': False,
                'error': '缺少爬虫名称'
            }), 400

        from scrapers import get_domestic_scrapers
        from scrapers.db import DBHandler
        from scrapers.config import load_config
        import threading
        import subprocess
        import sys
        import os

        # 获取数据库配置
        config = load_config()
        db_config = config.get('database', {})
        db = DBHandler(db_config)

        # 创建并启动爬虫
        def run_spider():
            try:
                # 配置子线程的日志输出到控制台
                import logging
                import sys
                
                # 屏蔽 werkzeug 日志
                logging.getLogger('werkzeug').setLevel(logging.WARNING)

                # 配置根日志
                root_logger = logging.getLogger()
                root_logger.setLevel(logging.INFO)
                
                # 检查是否已经存在 Handler，避免重复添加
                has_console_handler = any(isinstance(h, logging.StreamHandler) and h.stream == sys.stdout for h in root_logger.handlers)
                has_file_handler = False
                
                # 检查文件 Handler
                import os
                log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
                log_file_path = os.path.join(log_dir, 'spider.log')
                
                for h in root_logger.handlers:
                    if isinstance(h, logging.FileHandler) and getattr(h, 'baseFilename', '').endswith('spider.log'):
                        has_file_handler = True
                        break

                formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

                # 添加控制台处理器
                if not has_console_handler:
                    handler = logging.StreamHandler(sys.stdout)
                    handler.setLevel(logging.INFO)
                    handler.setFormatter(formatter)
                    root_logger.addHandler(handler)
                
                # 添加文件处理器
                if not has_file_handler:
                    os.makedirs(log_dir, exist_ok=True)
                    file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
                    file_handler.setLevel(logging.INFO)
                    file_handler.setFormatter(formatter)
                    root_logger.addHandler(file_handler)

                logger.info("[SPIDER] 开始执行爬虫: %s (%s)", spider_name, spider_type)
                logger.info("[SPIDER] 线程ID: %s", threading.current_thread().name)
                
                if spider_type == 'domestic':
                    from scrapers.domestic import create_spider
                    spider = create_spider(spider_name, config, db)
                    if spider:
                        logger.info("[SPIDER] 开始运行 domestic 爬虫: %s", spider_name)
                        count = spider.run()
                        logger.info("[SPIDER] domestic 爬虫完成，采集数量: %s", count)
                        log_spider_execution(db, spider_name, 'success', count)
                    else:
                        logger.error("[SPIDER] 爬虫不存在: %s", spider_name)
                        log_spider_execution(db, spider_name, 'failed', 0, f'爬虫 {spider_name} 不存在')
                        
                logger.info("[SPIDER] 爬虫执行完毕: %s", spider_name)
            except Exception as e:
                logger.exception("[SPIDER] 爬虫执行异常: %s", e)
                log_spider_execution(db, spider_name, 'failed', 0, str(e))

        # 在后台线程中运行爬虫
        thread = threading.Thread(target=run_spider, daemon=True)
        thread.start()

        return jsonify({
            'success': True,
            'message': f'爬虫 {spider_name} 已启动'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/spider/run-all', methods=['POST'])
def run_all_spiders():
    """依次启动所有爬虫（一个完成后再启动下一个）"""
    try:
        data = request.get_json() or {}
        spider_names = data.get('spider_names', [])  # 可选，指定要执行的爬虫名称列表

        from scrapers import get_domestic_scrapers
        from scrapers.db import DBHandler
        from scrapers.config import load_config
        import time

        # 获取数据库配置
        config = load_config()
        db_config = config.get('database', {})
        db = DBHandler(db_config)

        # 获取爬虫列表
        domestic_scrapers = get_domestic_scrapers()

        spiders_to_run = []
        if spider_names:
            # 只运行指定的爬虫
            for spider in domestic_scrapers:
                if spider['name'] in spider_names:
                    spiders_to_run.append(spider)
        else:
            # 运行所有爬虫
            spiders_to_run = domestic_scrapers

        if not spiders_to_run:
            return jsonify({
                'success': False,
                'error': '没有找到可执行的爬虫'
            }), 400

        # 依次执行每个爬虫
        results = []
        for spider in spiders_to_run:
            spider_name = spider['name']
            spider_desc = spider.get('description', spider_name)

            try:
                logger.info("[RUN-ALL] 开始执行爬虫: %s", spider_name)

                # 执行爬虫（同步阻塞）
                count = 0
                success = False
                from scrapers.domestic import create_spider
                spider_obj = create_spider(spider_name, config, db)
                if spider_obj:
                    count = spider_obj.run()
                    success = True
                    log_spider_execution(db, spider_name, 'success', count)
                else:
                    log_spider_execution(db, spider_name, 'failed', 0, f'爬虫 {spider_name} 不存在')

                results.append({
                    'name': spider_name,
                    'description': spider_desc,
                    'success': success,
                    'count': count
                })

                logger.info("[RUN-ALL] 爬虫完成: %s, 采集数量: %s", spider_name, count)

                # 短暂延迟，避免对目标网站造成过大压力
                time.sleep(1)

            except Exception as e:
                logger.exception("[RUN-ALL] 爬虫执行失败: %s, 错误: %s", spider_name, e)
                log_spider_execution(db, spider_name, 'failed', 0, str(e))
                results.append({
                    'name': spider_name,
                    'description': spider_desc,
                    'success': False,
                    'error': str(e)
                })

        success_count = sum(1 for r in results if r['success'])
        total_count = len(results)

        return jsonify({
            'success': True,
            'message': f'执行完成，成功 {success_count}/{total_count} 个爬虫',
            'data': {
                'results': results,
                'total': total_count,
                'success_count': success_count
            }
        })

    except Exception as e:
        logger.exception("run_all_spiders 执行失败: %s", e)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def log_spider_execution(db, spider_name, status, items_count, error_message=None):
    """记录爬虫执行日志"""
    try:
        from datetime import datetime
        table_name = db.get_table_name('spider_logs')

        query = f"""
        INSERT INTO {table_name}
        (spider_name, status, items_count, start_time, end_time, error_message)
        VALUES (%s, %s, %s, %s, %s, %s)
        """

        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                now = datetime.now()
                cursor.execute(query, (spider_name, status, items_count, now, now, error_message))
    except Exception as e:
        logger.exception("记录爬虫日志失败: %s", e)


@api_bp.route('/spider/stop', methods=['POST'])
def stop_spider():
    """停止爬虫"""
    try:
        data = request.get_json() or {}
        spider_name = data.get('spider_name')
        
        return jsonify({
            'success': True,
            'message': f'爬虫 {spider_name} 已停止'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==================== 数据管理接口（管理员） ====================

@api_bp.route('/admin/data/stats', methods=['GET'])
def admin_data_stats():
    """获取数据统计信息"""
    try:
        db = get_db()
        cleaner = get_cleaner()
        
        # 获取原始数据统计
        query = f"SELECT COUNT(*) as total FROM {db.get_table_name('raw_articles')}"
        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query)
                total = cursor.fetchone()
        
        # 获取分类数据统计
        category_query = f"""
        SELECT category, COUNT(*) as count 
        FROM {db.get_table_name('raw_articles')} 
        WHERE category IS NOT NULL AND category != '' 
        GROUP BY category
        """
        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                cursor.execute(category_query)
                categories = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'data': {
                'total_articles': int(total['total'] if total else 0),
                'categories': [dict(c) for c in categories],
                'cleaner_status': {
                    'stopwords_count': len(cleaner.stopwords)
                }
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/admin/data/clean', methods=['POST'])
def admin_data_clean():
    """执行数据清洗"""
    try:
        db = get_db()
        cleaner = get_cleaner()
        
        # 获取配置
        data = request.get_json() or {}
        config = {
            'remove_duplicates': data.get('remove_duplicates', True),
            'remove_null': data.get('remove_null', True),
            'normalize_format': data.get('normalize_format', True),
            'filter_invalid': data.get('filter_invalid', True),
            'llm_filter': data.get('llm_filter', False),
            'preprocess': data.get('preprocess', True)
        }
        
        # 获取原始数据
        query = f"SELECT * FROM {db.get_table_name('raw_articles')}"
        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query)
                articles = cursor.fetchall()
        
        if not articles:
            return jsonify({
                'success': False,
                'error': '没有可清洗的数据'
            }), 400
        
        # 转换为 DataFrame
        df = pd.DataFrame(articles)
        
        # 执行清洗
        cleaned_df = cleaner.clean_dataframe(df, config)
        
        # 预处理文本
        if config.get('preprocess', True):
            cleaned_df = cleaner.process_dataframe(cleaned_df)
        
        # 获取统计信息
        stats = cleaner.get_statistics(cleaned_df)
        
        # 保存清洗后的数据
        cleaned_count = len(cleaned_df)
        
        # 将清洗结果（含自动打标）回写到数据库
        updated_count = 0
        if not cleaned_df.empty and 'id' in cleaned_df.columns:
            try:
                table_name = db.get_table_name('raw_articles')
                with db.get_connection_ctx() as conn:
                    with conn.cursor() as cursor:
                        for _, row in cleaned_df.iterrows():
                            article_id = row['id']
                            title = row.get('title', '')
                            content = row.get('content', '')
                            category = row.get('category')
                            
                            # 自动打标
                            if not category or pd.isna(category) or category == '未分类' or category == '':
                                combined = f"{title} {content}"
                                new_category = cleaner.auto_label(combined)
                                if new_category:
                                    category = new_category
                            
                            # 更新数据库
                            update_sql = f"UPDATE {table_name} SET title = %s, content = %s, category = %s WHERE id = %s"
                            cursor.execute(update_sql, (title, content, category, article_id))
                            updated_count += 1
                    conn.commit()
            except Exception as e:
                logger.exception("保存清洗数据失败: %s", e)
        
        return jsonify({
            'success': True,
            'data': {
                'original_count': len(articles),
                'cleaned_count': cleaned_count,
                'removed_count': len(articles) - cleaned_count,
                'statistics': stats,
                'updated_db_count': updated_count
            },
            'message': f'数据清洗完成，处理 {cleaned_count} 条数据，已同步更新数据库及自动标签'
        })
    except Exception as e:
        logger.exception("admin_data_clean 执行失败: %s", e)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/admin/data/word-frequency', methods=['GET'])
def admin_word_frequency():
    """获取词频分析"""
    try:
        db = get_db()
        cleaner = get_cleaner()
        
        # 获取查询参数
        top_k = request.args.get('top_k', 50, type=int)
        category = request.args.get('category')
        
        # 获取原始数据
        if category:
            query = f"SELECT title, content FROM {db.get_table_name('raw_articles')} WHERE category = %s LIMIT 1000"
            params = (category,)
        else:
            query = f"SELECT title, content FROM {db.get_table_name('raw_articles')} LIMIT 1000"
            params = ()

        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                articles = cursor.fetchall()
        
        if not articles:
            return jsonify({
                'success': True,
                'data': {
                    'word_frequency': []
                }
            })
        
        # 转换为 DataFrame
        df = pd.DataFrame(articles)
        df['text'] = df['title'].astype(str) + ' ' + df['content'].astype(str)
        
        # 词频分析
        word_freq = cleaner.analyze_word_frequency(df, 'text', top_k)
        
        return jsonify({
            'success': True,
            'data': {
                'word_frequency': [{'word': w, 'count': c} for w, c in word_freq]
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==================== 模型管理接口（管理员） ====================

@api_bp.route('/admin/model/status', methods=['GET'])
def admin_model_status():
    """获取模型状态"""
    try:
        classifier = get_classifier()
        
        return jsonify({
            'success': True,
            'data': {
                'is_trained': classifier.is_trained,
                'categories': classifier.categories,
                'config': classifier.config,
                'feature_count': len(classifier.get_feature_names()) if classifier.vectorizer else 0,
                'training_state': _training_state
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/admin/model/history', methods=['GET'])
def admin_model_history():
    """获取模型历史记录"""
    try:
        project_root = os.path.dirname(os.path.dirname(__file__))
        history_path = os.path.join(project_root, 'logs', 'model_history.json')
        
        history = []
        if os.path.exists(history_path):
            try:
                with open(history_path, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except Exception:
                pass

        history = [normalize_model_history_record(record) for record in history if isinstance(record, dict)]
        history.sort(key=lambda item: item.get('timestamp', ''))
        
        return jsonify({
            'success': True,
            'data': history
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/admin/model/history', methods=['DELETE'])
def admin_model_history_clear():
    """清空模型历史记录"""
    try:
        project_root = os.path.dirname(os.path.dirname(__file__))
        history_path = os.path.join(project_root, 'logs', 'model_history.json')
        
        if os.path.exists(history_path):
            os.remove(history_path)
            
        return jsonify({
            'success': True,
            'message': '历史记录已清空'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/admin/config/rules', methods=['GET', 'POST'])
def admin_config_rules():
    """管理分类规则 (已废弃)"""
    return jsonify({'success': False, 'error': '该功能已废弃，请使用大模型分类'})


@api_bp.route('/admin/model/train', methods=['POST'])
def admin_model_train():
    """训练模型"""
    try:
        global _training_state, _training_thread
        # 检查是否已有训练任务在运行
        if _training_state['status'] in {'training', 'stopping'}:
            return jsonify({
                'success': False,
                'error': '训练任务正在进行中，请稍后再试'
            }), 400

        # 获取配置
        data = request.get_json() or {}
        model_type = data.get('model_type', 'svm')
        nlp_task = str(data.get('nlp_task') or 'content_classification').strip() or 'content_classification'
        try:
            epochs = int(data.get('epochs', 5))
            batch_size = int(data.get('batch_size', 32))
            learning_rate = float(data.get('learning_rate', 2e-5))
        except (TypeError, ValueError):
            return jsonify({
                'success': False,
                'error': '训练参数格式无效，请检查训练轮次、批次大小和学习率'
            }), 400

        if epochs < 1 or batch_size < 1 or learning_rate <= 0:
            return jsonify({
                'success': False,
                'error': '训练参数必须大于 0'
            }), 400

        enable_augmentation = bool(data.get('enable_augmentation', False))
        use_fgm = bool(data.get('use_fgm', False))

        sentiment_days = int(data.get('sentiment_days', 3) or 3)
        sentiment_limit = int(data.get('sentiment_limit', 300) or 300)
        sentiment_max_entities = int(data.get('sentiment_max_entities', 3) or 3)
        
        # 重置状态
        _training_state = {
            'status': 'training',
            'progress': 0,
            'message': '准备开始训练...',
            'logs': [],
            'stop_requested': False
        }
        
        def training_task(app_context):
            """后台训练任务"""
            import threading
            global _training_state, _training_thread
            
            try:
                # 必须在线程中重新获取 DB 和 Classifier，或者传递进去
                # 这里简单起见重新获取
                db = get_db()
                
                # 根据模型类型重新实例化分类器
                global _classifier
                _classifier = build_classifier_by_type(model_type)
                classifier = _classifier

                cleaner = get_cleaner()
                
                def progress_callback(progress, message):
                    ensure_training_not_cancelled()
                    _training_state['progress'] = progress
                    _training_state['message'] = message
                    append_training_log(message)
                
                progress_callback(5, "正在加载训练数据...")
                
                # 更新配置
                classifier.set_config({
                    'model_type': model_type,
                    'nlp_task': nlp_task,
                    'display_name': str(data.get('display_name') or '').strip() or None,
                    'max_features': data.get('max_features', 5000),
                    'ngram_range': tuple(data.get('ngram_range', [1, 2])),
                    'epochs': epochs,
                    'batch_size': batch_size,
                    'learning_rate': learning_rate,
                })

                if nlp_task == 'content_classification':
                    samples, dataset_summary = prepare_labeled_model_samples(db, cleaner)
                elif nlp_task == 'sentiment_entity_ranker':
                    samples, dataset_summary = prepare_sentiment_entity_samples(
                        db,
                        cleaner,
                        days=sentiment_days,
                        limit=sentiment_limit,
                        max_entities=sentiment_max_entities,
                    )
                elif nlp_task == 'sentiment_stance':
                    samples, dataset_summary = prepare_sentiment_stance_samples(
                        db,
                        cleaner,
                        days=sentiment_days,
                        limit=sentiment_limit,
                        max_entities=sentiment_max_entities,
                    )
                elif nlp_task == 'sentiment_sentiment':
                    samples, dataset_summary = prepare_sentiment_sentiment_samples(
                        db,
                        cleaner,
                        days=sentiment_days,
                        limit=sentiment_limit,
                        max_entities=sentiment_max_entities,
                    )
                else:
                    raise ValueError(f'不支持的训练任务: {nlp_task}')
                ensure_training_not_cancelled()
                if not samples:
                    _training_state['status'] = 'failed'
                    _training_state['stop_requested'] = False
                    progress_callback(0, "没有找到任何可用于训练的样本")
                    return

                split_data = split_model_samples(samples)
                train_texts = split_data['train_texts']
                train_labels = split_data['train_labels']
                test_texts = split_data['test_texts']
                test_labels = split_data['test_labels']
                ensure_training_not_cancelled()

                if not train_texts or not test_texts:
                    _training_state['status'] = 'failed'
                    _training_state['stop_requested'] = False
                    progress_callback(0, "训练集或测试集为空，无法完成本次训练")
                    return

                # 设置类别
                unique_categories = sorted(set(train_labels))
                classifier.set_categories(unique_categories)

                progress_callback(
                    10,
                    f"数据加载完成，训练集 {len(train_texts)} 条，测试集 {len(test_texts)} 条，{len(unique_categories)} 个分类"
                )
                progress_callback(
                    12,
                    f"自动补标 {dataset_summary['auto_labeled_samples']} 条，去重 {dataset_summary['deduplicated_samples']} 条，分层切分: {'是' if split_data['stratified'] else '否'}"
                )
                progress_callback(
                    13,
                    f"训练参数: epochs={epochs}, batch_size={batch_size}, learning_rate={learning_rate:g}"
                )

                # 数据增强（仅对训练集，不触碰测试集）
                aug_summary = None
                if enable_augmentation and model_type in ('bert', 'bert_textcnn'):
                    try:
                        from scrapers.data_augmenter import augment_dataset
                        progress_callback(14, "正在执行数据增强（同义词替换 + EDA）...")
                        original_count = len(train_texts)
                        train_texts, train_labels, aug_summary = augment_dataset(
                            train_texts, train_labels,
                            callback=lambda p, m: progress_callback(13 + int(p * 0.02), m)
                        )
                        progress_callback(
                            15,
                            f"数据增强完成: {original_count} → {len(train_texts)} 条 (+{aug_summary['augmented_samples']}), "
                            f"覆盖 {aug_summary['classes_augmented']} 个低频类别"
                        )
                    except Exception as aug_err:
                        progress_callback(15, f"数据增强跳过（{aug_err}），使用原始数据继续训练")
                ensure_training_not_cancelled()
                
                # 训练模型
                # 根据模型类型传递不同的参数
                if model_type == 'bert_textcnn':
                    result = classifier.train(train_texts, train_labels, epochs=epochs, batch_size=batch_size, learning_rate=learning_rate, use_fgm=use_fgm, callback=progress_callback)
                elif model_type == 'bert':
                    result = classifier.train(train_texts, train_labels, epochs=epochs, batch_size=batch_size, learning_rate=learning_rate, use_fgm=use_fgm, callback=progress_callback)
                elif model_type in ['cnn', 'lstm']:
                    result = classifier.train(
                        train_texts,
                        train_labels,
                        epochs=epochs,
                        batch_size=batch_size,
                        learning_rate=learning_rate,
                        callback=progress_callback
                    )
                else:
                    result = classifier.train(train_texts, train_labels, callback=progress_callback)
                ensure_training_not_cancelled()
                
                if result['success']:
                    progress_callback(92, "正在评估固定测试集...")
                    evaluation_texts, evaluation_labels, skipped_unknown = filter_known_labels(
                        classifier,
                        test_texts,
                        test_labels
                    )
                    if not evaluation_texts:
                        raise ValueError('测试集标签与当前模型不兼容，请补充各类别样本后重试')

                    if skipped_unknown > 0:
                        progress_callback(94, f"测试集中有 {skipped_unknown} 条未知标签样本已跳过")

                    evaluation_result = classifier.evaluate(evaluation_texts, evaluation_labels)

                    _training_state['status'] = 'success'
                    progress_callback(
                        100,
                        f"模型训练成功，测试集 Accuracy {evaluation_result['accuracy']:.2%}，F1 {evaluation_result['f1_score']:.2%}"
                    )
                    
                    # 保存历史记录
                    train_scope = 'train'
                    train_scope_label = '训练集'
                    train_accuracy = extract_training_accuracy(result)
                    validation_accuracy = extract_validation_accuracy(result)
                    if train_accuracy is None and validation_accuracy is not None:
                        train_scope = 'validation'
                        train_scope_label = '验证集'

                    train_history_record = {
                        'type': 'train',
                        'model_type': model_type,
                    'nlp_task': nlp_task,
                        'accuracy': train_accuracy if train_accuracy is not None else validation_accuracy,
                        'f1_score': None,
                        'train_accuracy': train_accuracy,
                        'validation_accuracy': validation_accuracy,
                        'metric_scope': train_scope,
                        'scope_label': train_scope_label,
                        'is_ranked': False,
                        'params': {
                            'epochs': epochs,
                            'batch_size': batch_size,
                            'learning_rate': learning_rate,
                            'split_random_state': MODEL_EVAL_RANDOM_STATE,
                            'split_test_size': MODEL_EVAL_TEST_SIZE,
                            'enable_augmentation': enable_augmentation,
                            'use_fgm': use_fgm,
                        },
                        'samples': len(train_texts),
                        'augmented_samples': aug_summary['augmented_samples'] if aug_summary else 0,
                        'auto_labeled_samples': dataset_summary['auto_labeled_samples'],
                        'deduplicated_samples': dataset_summary['deduplicated_samples'],
                        'class_count': len(unique_categories)
                    }
                    save_model_history(train_history_record)

                    evaluate_history_record = {
                        'type': 'evaluate',
                        'model_type': model_type,
                    'nlp_task': nlp_task,
                        'accuracy': evaluation_result.get('accuracy'),
                        'f1_score': evaluation_result.get('f1_score'),
                        'precision': evaluation_result.get('precision'),
                        'recall': evaluation_result.get('recall'),
                        'metric_scope': 'test',
                        'scope_label': '测试集',
                        'is_ranked': True,
                        'params': {
                            'epochs': epochs,
                            'batch_size': batch_size,
                            'learning_rate': learning_rate,
                            'split_random_state': MODEL_EVAL_RANDOM_STATE,
                            'split_test_size': MODEL_EVAL_TEST_SIZE,
                            'stratified': split_data['stratified'],
                            'enable_augmentation': enable_augmentation,
                            'use_fgm': use_fgm,
                        },
                        'samples': len(evaluation_texts),
                        'augmented_samples': aug_summary['augmented_samples'] if aug_summary else 0,
                        'auto_labeled_samples': dataset_summary['auto_labeled_samples'],
                        'deduplicated_samples': dataset_summary['deduplicated_samples'],
                        'class_count': len(unique_categories)
                    }
                    save_model_history(evaluate_history_record)

                    # 自动持久化模型到磁盘
                    ensure_training_not_cancelled()
                    if nlp_task == 'sentiment_entity_ranker':
                        auto_save_model(classifier, subdir='nlp', filename_prefix='latest_sentiment_entity')
                    elif nlp_task == 'sentiment_stance':
                        auto_save_model(classifier, subdir='nlp', filename_prefix='latest_sentiment_stance')
                    elif nlp_task == 'sentiment_sentiment':
                        auto_save_model(classifier, subdir='nlp', filename_prefix='latest_sentiment_sentiment')
                    else:
                        auto_save_model(classifier)
                    _training_state['stop_requested'] = False
                    progress_callback(100, f"模型已自动保存，下次启动可自动加载")
                else:
                    _training_state['status'] = 'failed'
                    _training_state['stop_requested'] = False
                    progress_callback(0, f"训练失败: {result.get('error')}")
            except TrainingCancelledError as e:
                _training_state['status'] = 'stopped'
                _training_state['message'] = str(e)
                _training_state['stop_requested'] = False
                append_training_log(str(e))
            except Exception as e:
                import traceback
                traceback.print_exc()
                _training_state['status'] = 'failed'
                _training_state['message'] = str(e)
                _training_state['stop_requested'] = False
                append_training_log(f"ERROR: {str(e)}")
            finally:
                _training_thread = None

        import threading
        # 启动后台线程
        thread = threading.Thread(target=training_task, args=(None,))
        thread.daemon = True
        thread.start()
        _training_thread = thread
        
        return jsonify({
            'success': True,
            'message': '模型训练已在后台启动'
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/admin/model/stop', methods=['POST'])
def admin_model_stop():
    """停止当前训练任务"""
    try:
        global _training_state

        if _training_state.get('status') not in {'training', 'stopping'}:
            return jsonify({
                'success': False,
                'error': '当前没有正在执行的训练任务'
            }), 400

        if not _training_state.get('stop_requested'):
            _training_state['stop_requested'] = True
            _training_state['status'] = 'stopping'
            _training_state['message'] = '正在停止训练，请稍候...'
            append_training_log('收到停止请求，正在安全终止训练任务...')

        return jsonify({
            'success': True,
            'message': '已发送停止请求'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/admin/model/evaluate', methods=['POST'])
def admin_model_evaluate():
    """评估模型"""
    try:
        db = get_db()
        classifier = get_classifier()
        
        if not classifier.is_trained:
            return jsonify({
                'success': False,
                'error': '模型未训练，请先训练模型'
            }), 400

        cleaner = get_cleaner()
        samples, _ = prepare_labeled_model_samples(db, cleaner)
        split_data = split_model_samples(samples)
        texts, labels, skipped_unknown = filter_known_labels(
            classifier,
            split_data['test_texts'],
            split_data['test_labels']
        )

        if not texts:
            return jsonify({
                'success': False,
                'error': '当前模型无法识别测试集中的标签，请重新训练模型'
            }), 400

        # 评估模型
        result = classifier.evaluate(texts, labels)
        
        # 保存历史记录
        try:
            history_record = {
                'type': 'evaluate',
                'model_type': classifier.config.get('model_type', 'unknown'),
                'accuracy': result.get('accuracy'),
                'f1_score': result.get('f1_score'),
                'precision': result.get('precision'),
                'recall': result.get('recall'),
                'metric_scope': 'test',
                'scope_label': '测试集',
                'is_ranked': True,
                'params': {
                    **classifier.config,
                    'split_random_state': MODEL_EVAL_RANDOM_STATE,
                    'split_test_size': MODEL_EVAL_TEST_SIZE,
                    'stratified': split_data['stratified']
                },
                'samples': len(texts),
                'class_count': len(set(labels))
            }
            save_model_history(history_record)
        except Exception as e:
            logger.exception("保存评估历史失败: %s", e)
        
        # 获取混淆矩阵数据
        cm_data = classifier.get_confusion_matrix_data(texts, labels)
        
        return jsonify({
            'success': True,
            'data': {
                'metrics': result,
                'confusion_matrix': cm_data,
                'dataset': {
                    'samples': len(texts),
                    'skipped_unknown_labels': skipped_unknown,
                    'stratified': split_data['stratified']
                }
            }
        })
    except Exception as e:
        logger.exception("admin_model_evaluate 执行失败: %s", e)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/admin/model/evaluate/saved', methods=['POST'])
def admin_model_evaluate_saved():
    """评估指定已保存模型（不影响当前内存模型）"""
    try:
        payload = request.get_json(silent=True) or {}
        filepath_raw = payload.get('filepath')
        if not filepath_raw:
            return jsonify({'success': False, 'error': '请提供模型文件路径'}), 400

        rel_path = _normalize_and_validate_saved_model_path(filepath_raw)
        if not rel_path:
            return jsonify({'success': False, 'error': '模型路径无效'}), 400

        project_root = os.path.dirname(os.path.dirname(__file__))
        abs_path = os.path.normpath(os.path.join(project_root, rel_path.replace('/', os.sep)))

        model_type = detect_saved_model_type(abs_path)
        eval_classifier = build_classifier_by_type(model_type)
        eval_classifier.load(abs_path)

        if not eval_classifier.is_trained:
            return jsonify({'success': False, 'error': '指定模型未训练或不可用'}), 400

        db = get_db()
        cleaner = get_cleaner()
        samples, _ = prepare_labeled_model_samples(db, cleaner)
        split_data = split_model_samples(samples)

        texts, labels, skipped_unknown = filter_known_labels(
            eval_classifier,
            split_data['test_texts'],
            split_data['test_labels']
        )

        if not texts:
            return jsonify({'success': False, 'error': '指定模型无法识别测试集中的标签，请重新训练模型'}), 400

        result = eval_classifier.evaluate(texts, labels)
        cm_data = eval_classifier.get_confusion_matrix_data(texts, labels)

        return jsonify({
            'success': True,
            'data': {
                'metrics': result,
                'confusion_matrix': cm_data,
                'dataset': {
                    'samples': len(texts),
                    'skipped_unknown_labels': skipped_unknown,
                    'stratified': split_data['stratified']
                }
            }
        })
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.exception("admin_model_evaluate_saved 执行失败: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/admin/model/predict', methods=['POST'])
def admin_model_predict():
    """预测文本类别"""
    try:
        classifier = get_classifier()
        
        if not classifier.is_trained:
            return jsonify({
                'success': False,
                'error': '模型未训练，请先训练模型'
            }), 400
        
        data = request.get_json() or {}
        texts = data.get('texts', [])
        
        if not texts:
            return jsonify({
                'success': False,
                'error': '请提供要预测的文本'
            }), 400
        
        results = classifier.predict(texts)
        
        return jsonify({
            'success': True,
            'data': {
                'predictions': results
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/admin/model/apply', methods=['POST'])
def admin_model_apply():
    """应用当前模型到全量数据"""
    try:
        global _applying_state
        if _applying_state['status'] == 'processing':
            return jsonify({
                'success': False,
                'error': '正在应用模型中，请稍候...'
            }), 400

        classifier = get_classifier()
        if not classifier.is_trained:
            return jsonify({
                'success': False,
                'error': '模型未训练，请先训练模型'
            }), 400

        # 重置状态
        _applying_state = {
            'status': 'processing',
            'progress': 0,
            'message': '准备开始...',
            'total': 0,
            'current': 0
        }

        def apply_task():
            global _applying_state
            import threading
            
            try:
                db = get_db()
                
                # 1. 获取所有数据
                _applying_state['message'] = '正在读取数据...'
                query = f"SELECT id, title, content FROM {db.get_table_name('raw_articles')}"
                
                with db.get_connection_ctx() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(query)
                        articles = cursor.fetchall()
                
                total = len(articles)
                _applying_state['total'] = total
                _applying_state['message'] = f'共找到 {total} 条数据，开始处理...'
                
                if total == 0:
                    _applying_state['status'] = 'success'
                    _applying_state['progress'] = 100
                    return

                # 2. 批量处理
                batch_size = 100
                updated_count = 0
                
                for i in range(0, total, batch_size):
                    batch = articles[i:i+batch_size]
                    texts = []
                    ids = []
                    
                    for art in batch:
                        title = art.get('title', '')
                        content = art.get('content', '')
                        text = f"{title} {content}".strip()
                        if text:
                            texts.append(text)
                            ids.append(art['id'])
                    
                    if texts:
                        # 预测
                        predictions = classifier.predict(texts)
                        
                        # 更新数据库
                        with db.get_connection_ctx() as conn:
                            with conn.cursor() as cursor:
                                for art_id, pred in zip(ids, predictions):
                                    category = pred['category']
                                    update_sql = f"UPDATE {db.get_table_name('raw_articles')} SET category = %s WHERE id = %s"
                                    cursor.execute(update_sql, (category, art_id))
                            conn.commit()
                        
                        updated_count += len(texts)
                    
                    # 更新进度
                    current = min(i + batch_size, total)
                    _applying_state['current'] = current
                    _applying_state['progress'] = int((current / total) * 100)
                    _applying_state['message'] = f'已处理 {current}/{total} 条数据...'
                
                _applying_state['status'] = 'success'
                _applying_state['message'] = f'处理完成，共更新 {updated_count} 条数据'
                _applying_state['progress'] = 100
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                _applying_state['status'] = 'failed'
                _applying_state['message'] = str(e)

        # 启动后台线程
        import threading
        thread = threading.Thread(target=apply_task)
        thread.daemon = True
        thread.start()

        return jsonify({
            'success': True,
            'message': '已开始后台应用模型'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/admin/model/apply/status', methods=['GET'])
def admin_model_apply_status():
    """获取模型应用状态"""
    return jsonify({
        'success': True,
        'data': _applying_state
    })


@api_bp.route('/admin/model/save', methods=['POST'])
def admin_model_save():
    """保存模型"""
    try:
        classifier = get_classifier()
        
        if not classifier.is_trained:
            return jsonify({
                'success': False,
                'error': '模型未训练，无法保存'
            }), 400
        
        data = request.get_json() or {}
        model_type = classifier.config.get('model_type', 'svm')
        default_name = f'news_{model_type}_classifier'
        if model_type not in {'bert', 'bert_textcnn'}:
            default_name += '.pkl'

        filename = data.get('filename', default_name)
        
        filepath = classifier.save(filename)
        
        return jsonify({
            'success': True,
            'message': f'模型已保存到: {filepath}',
            'data': {
                'filepath': filepath
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/admin/model/load', methods=['POST'])
def admin_model_load():
    """加载模型"""
    try:
        data = request.get_json() or {}
        filepath = data.get('filepath')
        
        if not filepath:
            return jsonify({
                'success': False,
                'error': '请提供模型文件路径'
            }), 400

        global _classifier
        model_type = detect_saved_model_type(filepath)
        _classifier = build_classifier_by_type(model_type)
        classifier = _classifier
        classifier.load(filepath)
        
        return jsonify({
            'success': True,
            'message': '模型加载成功',
            'data': {
                'model_type': classifier.config.get('model_type', model_type),
                'is_trained': classifier.is_trained,
                'categories': classifier.categories
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/admin/model/clear', methods=['DELETE'])
def admin_model_clear():
    """清除已有模型（内存 + 磁盘自动保存文件）"""
    try:
        import shutil

        global _classifier
        _classifier = None

        include_pretrained_raw = (request.args.get('include_pretrained') or '').strip().lower()
        include_pretrained = include_pretrained_raw in ('1', 'true', 'yes', 'y', 'on')

        protected_names = set()
        if not include_pretrained:
            protected_names.add('pretrained')

        removed = []
        skipped = []
        if os.path.isdir(SAVED_MODELS_DIR):
            for name in os.listdir(SAVED_MODELS_DIR):
                if name.startswith('.'):
                    continue
                if name in protected_names:
                    skipped.append(name)
                    continue
                full_path = os.path.join(SAVED_MODELS_DIR, name)
                if os.path.isdir(full_path):
                    shutil.rmtree(full_path)
                else:
                    os.remove(full_path)
                removed.append(name)

        return jsonify({
            'success': True,
            'message': f'已清除内存模型及 saved_models 下 {len(removed)} 个模型存档（已保留预训练权重缓存）',
            'data': {'removed': removed, 'skipped': skipped, 'include_pretrained': include_pretrained}
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==================== 可视化数据接口 ====================

@api_bp.route('/admin/visualize/data-quality', methods=['GET'])
def admin_visualize_data_quality():
    """获取数据质量可视化数据"""
    try:
        db = get_db()
        cleaner = get_cleaner()
        
        # 获取数据
        query = f"SELECT title, content, source, publish_time FROM {db.get_table_name('raw_articles')} LIMIT 2000"
        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query)
                articles = cursor.fetchall()
        
        df = pd.DataFrame(articles)
        
        # 数据质量分析
        # 辅助函数：将 numpy/pandas 类型转换为 Python 原生类型
        def to_native_type(val):
            """将 numpy/pandas 类型转换为 Python 原生类型"""
            import numbers
            if val is None or pd.isna(val):
                return 0
            if isinstance(val, (np.integer, np.floating, np.bool_)):
                return val.item()
            if isinstance(val, numbers.Number):
                return val
            return val

        quality_data = {
            'total': to_native_type(len(df)),
            'with_title': to_native_type(df['title'].notna().sum() if 'title' in df.columns else 0),
            'with_content': to_native_type(df['content'].notna().sum() if 'content' in df.columns else 0),
            'title_length_avg': to_native_type(df['title'].str.len().mean() if 'title' in df.columns else 0),
            'content_length_avg': to_native_type(df['content'].str.len().mean() if 'content' in df.columns else 0),
            'sources': {str(k): to_native_type(v) for k, v in df['source'].value_counts().to_dict().items()} if 'source' in df.columns else {}
        }
        
        return jsonify({
            'success': True,
            'data': quality_data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/admin/visualize/collection-stats', methods=['GET'])
def admin_visualize_collection_stats():
    """获取采集统计可视化数据"""
    try:
        db = get_db()
        
        # 按日期统计采集量
        query = f"""
        SELECT DATE(start_time) as date, 
               SUM(items_count) as total_items,
               COUNT(*) as total_runs
        FROM {db.get_table_name('spider_logs')}
        GROUP BY DATE(start_time)
        ORDER BY date DESC
        LIMIT 30
        """
        
        try:
            with db.get_connection_ctx() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    stats = cursor.fetchall()
        except:
            stats = []
        
        daily_stats = []
        for s in stats:
            daily_stats.append({
                'date': str(s['date']),
                'total_items': int(s['total_items'] or 0),
                'total_runs': int(s['total_runs'] or 0)
            })

        return jsonify({
            'success': True,
            'data': {
                'daily_stats': daily_stats
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==================== 系统接口 ====================

@api_bp.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    try:
        db = get_db()
        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
        
        return jsonify({
            'success': True,
            'status': 'healthy',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'status': 'unhealthy',
            'error': str(e)
        }), 503


def _get_nlp_config():
    config = load_config() or {}
    return (config.get('nlp', {}) or {})


@api_bp.route('/admin/nlp/models', methods=['GET'])
def admin_nlp_models():
    try:
        models = list_saved_models()
        return jsonify({'success': True, 'data': models})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/admin/nlp/settings', methods=['GET'])
def admin_nlp_settings_get():
    try:
        nlp_config = _get_nlp_config()
        return jsonify({'success': True, 'data': nlp_config.get('model_selection', {}) or {}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _normalize_and_validate_saved_model_path(value):
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None

    project_root = os.path.dirname(os.path.dirname(__file__))
    saved_root = os.path.normpath(os.path.join(project_root, 'saved_models'))

    rel = value.replace('\\', '/')
    if rel.startswith('/'):
        rel = rel[1:]

    candidate = os.path.normpath(os.path.join(project_root, rel))
    if not candidate.startswith(saved_root + os.sep) and candidate != saved_root:
        raise ValueError('模型路径必须位于 saved_models 目录内')

    if not (os.path.isdir(candidate) or os.path.isfile(candidate)):
        raise ValueError('模型路径不存在')

    if os.path.isfile(candidate):
        if not candidate.lower().endswith('.pkl'):
            raise ValueError('模型文件必须为 .pkl')
    else:
        has_marker = (
            os.path.exists(os.path.join(candidate, 'metadata.pkl')) or
            os.path.exists(os.path.join(candidate, 'config.json')) or
            os.path.exists(os.path.join(candidate, 'model.keras'))
        )
        if not has_marker:
            raise ValueError('模型目录格式不正确')

    return os.path.relpath(candidate, project_root).replace('\\', '/')


@api_bp.route('/admin/nlp/settings', methods=['POST'])
def admin_nlp_settings_update():
    try:
        payload = request.get_json(silent=True) or {}
        model_selection = payload.get('model_selection') if isinstance(payload.get('model_selection'), dict) else payload
        if not isinstance(model_selection, dict):
            return jsonify({'success': False, 'error': 'model_selection 格式不正确'}), 400

        allowed_keys = {
            'sentiment_entity_model',
            'sentiment_stance_model',
            'sentiment_sentiment_model',
            'events_vector_model',
        }

        normalized = {}
        for key, value in model_selection.items():
            if key not in allowed_keys:
                continue
            normalized[key] = _normalize_and_validate_saved_model_path(value)

        updated = update_config({'nlp': {'model_selection': normalized}})
        selection = ((updated.get('nlp') or {}).get('model_selection') or {})
        return jsonify({'success': True, 'data': selection})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _run_sentiment_task(*, days: int, limit: int, max_entities: int, force: bool):
    global _nlp_sentiment_state

    nlp_config = _get_nlp_config()
    if not nlp_config.get('enabled', False):
        _nlp_sentiment_state = {
            'status': 'failed',
            'progress': 0,
            'message': 'NLP 功能未启用（config.yaml: nlp.enabled=false）',
            'total': 0,
            'current': 0,
            'last_error': ''
        }
        return

    model_selection = nlp_config.get('model_selection', {}) or {}
    entity_model_path = model_selection.get('sentiment_entity_model')
    stance_model_path = model_selection.get('sentiment_stance_model')
    sentiment_model_path = model_selection.get('sentiment_sentiment_model')
    if not entity_model_path or not stance_model_path or not sentiment_model_path:
        _nlp_sentiment_state = {
            'status': 'failed',
            'progress': 0,
            'message': '未配置情感抽取模型（nlp.model_selection.*）',
            'total': 0,
            'current': 0,
            'last_error': ''
        }
        return

    _nlp_sentiment_state = {
        'status': 'running',
        'progress': 0,
        'message': '开始处理',
        'total': 0,
        'current': 0,
        'last_error': ''
    }

    db = get_db()
    articles_query = f"""
    SELECT id, title, content, publish_time, source_name
    FROM {db.get_table_name('raw_articles')}
    WHERE crawl_time >= DATE_SUB(NOW(), INTERVAL %s DAY)
    ORDER BY crawl_time DESC
    LIMIT %s
    """

    try:
        with db.get_connection_ctx() as conn:
            if not conn:
                raise RuntimeError('无法获取数据库连接')
            with conn.cursor() as cursor:
                cursor.execute(articles_query, (int(days), int(limit)))
                articles = cursor.fetchall()

            total = len(articles)
            _nlp_sentiment_state['total'] = total
            if total == 0:
                _nlp_sentiment_state.update({
                    'status': 'success',
                    'progress': 100,
                    'message': '无可处理文章',
                    'current': 0
                })
                return

            inserted = 0
            for idx, row in enumerate(articles, start=1):
                article_id = int(row['id'])
                title = str(row.get('title') or '')
                content = str(row.get('content') or '')

                _nlp_sentiment_state['current'] = idx
                _nlp_sentiment_state['progress'] = int(idx * 100 / total)

                if not force:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            f"""
                            SELECT id
                            FROM {db.get_table_name('article_nlp_results')}
                            WHERE article_id=%s AND task=%s
                            ORDER BY updated_at DESC
                            LIMIT 1
                            """,
                            (article_id, 'sentiment_stance')
                        )
                        exists = cursor.fetchone()
                    if exists:
                        continue

                entities_result = extract_entities(
                    title=title,
                    content=content,
                    max_entities=max_entities,
                    entity_model_path=entity_model_path,
                )
                stances_result = extract_stances(
                    title=title,
                    content=content,
                    entities=entities_result.get('entities') or [],
                    stance_model_path=stance_model_path,
                    sentiment_model_path=sentiment_model_path,
                )

                with conn.cursor() as cursor:
                    cursor.execute(
                        f"""
                        INSERT INTO {db.get_table_name('article_nlp_results')}
                        (article_id, task, provider, model, version, label, score, result_json)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            article_id,
                            'sentiment_entities',
                            entities_result.get('provider') or 'model',
                            entities_result.get('model') or os.path.basename(str(entity_model_path)),
                            None,
                            None,
                            None,
                            json.dumps(
                                {
                                    'entities': entities_result.get('entities') or [],
                                    'models': {'entity': str(entity_model_path)},
                                },
                                ensure_ascii=False
                            ),
                        )
                    )
                    cursor.execute(
                        f"""
                        INSERT INTO {db.get_table_name('article_nlp_results')}
                        (article_id, task, provider, model, version, label, score, result_json)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            article_id,
                            'sentiment_stance',
                            stances_result.get('provider') or 'model',
                            stances_result.get('model') or os.path.basename(str(stance_model_path)),
                            None,
                            None,
                            None,
                            json.dumps(
                                {
                                    'stances': stances_result.get('stances') or [],
                                    'models': {'stance': str(stance_model_path), 'sentiment': str(sentiment_model_path)},
                                },
                                ensure_ascii=False
                            ),
                        )
                    )
                inserted += 1

                if inserted % 20 == 0:
                    conn.commit()

            conn.commit()

        _nlp_sentiment_state.update({
            'status': 'success',
            'progress': 100,
            'message': '处理完成'
        })
    except Exception as e:
        _nlp_sentiment_state.update({
            'status': 'failed',
            'message': '处理失败',
            'last_error': str(e)
        })


@api_bp.route('/admin/nlp/sentiment/run', methods=['POST'])
def admin_nlp_sentiment_run():
    global _nlp_sentiment_thread, _nlp_sentiment_state

    payload = request.get_json(silent=True) or {}
    nlp_config = _get_nlp_config()
    days = int(payload.get('days', nlp_config.get('event_window_days', 3)))
    limit = int(payload.get('limit', nlp_config.get('limit', 500)))
    max_entities = int(payload.get('max_entities', 3))
    force = bool(payload.get('force', False))

    if _nlp_sentiment_thread and _nlp_sentiment_thread.is_alive():
        return jsonify({'success': False, 'error': '情感抽取任务正在运行'}), 409

    _nlp_sentiment_state.update({
        'status': 'running',
        'progress': 0,
        'message': '任务已启动',
        'total': 0,
        'current': 0,
        'last_error': ''
    })

    _nlp_sentiment_thread = threading.Thread(
        target=_run_sentiment_task,
        kwargs={'days': days, 'limit': limit, 'max_entities': max_entities, 'force': force},
        daemon=True
    )
    _nlp_sentiment_thread.start()

    task_id = f'sentiment-{datetime.now().strftime("%Y%m%d%H%M%S")}'
    return jsonify({'ok': True, 'task_id': task_id})


@api_bp.route('/admin/nlp/sentiment/status', methods=['GET'])
def admin_nlp_sentiment_status():
    return jsonify(dict(_nlp_sentiment_state))


@api_bp.route('/articles/<int:article_id>/sentiment/analyze', methods=['POST'])
def analyze_article_sentiment(article_id: int):
    try:
        payload = request.get_json(silent=True) or {}
        nlp_config = _get_nlp_config()
        if not nlp_config.get('enabled', False):
            return jsonify({'error': 'NLP 功能未启用（config.yaml: nlp.enabled=false）'}), 400

        selection = nlp_config.get('model_selection', {}) or {}
        entity_model_path = payload.get('entity_model_path') or selection.get('sentiment_entity_model')
        stance_model_path = payload.get('stance_model_path') or selection.get('sentiment_stance_model')
        sentiment_model_path = payload.get('sentiment_model_path') or selection.get('sentiment_sentiment_model')
        max_entities = int(payload.get('max_entities', 3))
        save_result = bool(payload.get('save_result', True))

        if not entity_model_path or not stance_model_path or not sentiment_model_path:
            return jsonify({'error': '缺少模型选择：请在页面选择实体/立场/情绪模型'}), 400

        entity_model_path = _normalize_and_validate_saved_model_path(entity_model_path)
        stance_model_path = _normalize_and_validate_saved_model_path(stance_model_path)
        sentiment_model_path = _normalize_and_validate_saved_model_path(sentiment_model_path)

        db = get_db()
        query = f"""
        SELECT id, title, content
        FROM {db.get_table_name('raw_articles')}
        WHERE id=%s
        """
        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (int(article_id),))
                row = cursor.fetchone()
                if not row:
                    return jsonify({'error': '新闻不存在'}), 404

            title = str(row.get('title') or '')
            content = str(row.get('content') or '')
            entities_result = extract_entities(
                title=title,
                content=content,
                max_entities=max_entities,
                entity_model_path=entity_model_path,
            )
            stances_result = extract_stances(
                title=title,
                content=content,
                entities=entities_result.get('entities') or [],
                stance_model_path=stance_model_path,
                sentiment_model_path=sentiment_model_path,
            )

            entities = entities_result.get('entities') or []
            stances = stances_result.get('stances') or []

            if save_result:
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"""
                        INSERT INTO {db.get_table_name('article_nlp_results')}
                        (article_id, task, provider, model, version, label, score, result_json)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            int(article_id),
                            'sentiment_entities',
                            entities_result.get('provider') or 'model',
                            entities_result.get('model') or os.path.basename(str(entity_model_path)),
                            None,
                            None,
                            None,
                            json.dumps(
                                {
                                    'entities': entities,
                                    'models': {'entity': str(entity_model_path)},
                                },
                                ensure_ascii=False
                            ),
                        )
                    )
                    cursor.execute(
                        f"""
                        INSERT INTO {db.get_table_name('article_nlp_results')}
                        (article_id, task, provider, model, version, label, score, result_json)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            int(article_id),
                            'sentiment_stance',
                            stances_result.get('provider') or 'model',
                            stances_result.get('model') or os.path.basename(str(stance_model_path)),
                            None,
                            None,
                            None,
                            json.dumps(
                                {
                                    'stances': stances,
                                    'models': {'stance': str(stance_model_path), 'sentiment': str(sentiment_model_path)},
                                },
                                ensure_ascii=False
                            ),
                        )
                    )
                conn.commit()

        return jsonify({
            'article_id': int(article_id),
            'entities': entities,
            'stances': stances,
            'models': {
                'entity': str(entity_model_path),
                'stance': str(stance_model_path),
                'sentiment': str(sentiment_model_path),
            }
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/articles/<int:article_id>/sentiment', methods=['GET'])
def get_article_sentiment(article_id: int):
    try:
        db = get_db()
        query = f"""
        SELECT task, result_json
        FROM {db.get_table_name('article_nlp_results')}
        WHERE article_id=%s AND task IN ('sentiment_entities', 'sentiment_stance')
        ORDER BY updated_at DESC
        """

        entities = []
        stances = []
        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (int(article_id),))
                rows = cursor.fetchall()

        seen = set()
        for row in rows:
            task = row.get('task')
            if task in seen:
                continue
            seen.add(task)
            raw = row.get('result_json')
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception:
                parsed = {}
            if task == 'sentiment_entities':
                entities = parsed.get('entities') or []
            elif task == 'sentiment_stance':
                stances = parsed.get('stances') or []

        return jsonify({'article_id': int(article_id), 'entities': entities, 'stances': stances})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _run_events_task(*, limit: int, min_cluster_size: int, similarity_threshold: float, force: bool):
    global _nlp_events_state

    nlp_config = _get_nlp_config()
    if not nlp_config.get('enabled', False):
        _nlp_events_state = {
            'status': 'failed',
            'progress': 0,
            'message': 'NLP 功能未启用（config.yaml: nlp.enabled=false）',
            'total': 0,
            'current': 0,
            'last_error': ''
        }
        return

    embedding_max_length = int(nlp_config.get('embedding_max_length', 256))
    embedding_batch_size = int(nlp_config.get('embedding_batch_size', 16))
    use_llm_frame = bool(nlp_config.get('llm_use_for_event_framing', False))
    model_selection = nlp_config.get('model_selection', {}) or {}
    vector_model_path = model_selection.get('events_vector_model')
    if not vector_model_path:
        _nlp_events_state = {
            'status': 'failed',
            'progress': 0,
            'message': '未配置事件聚合向量模型（nlp.model_selection.events_vector_model）',
            'total': 0,
            'current': 0,
            'last_error': ''
        }
        return

    window_end = datetime.now()
    window_start = window_end - timedelta(seconds=1)

    _nlp_events_state = {
        'status': 'running',
        'progress': 0,
        'message': '开始处理',
        'total': 0,
        'current': 0,
        'last_error': ''
    }

    db = get_db()
    articles_query = f"""
    SELECT id, title, content, publish_time, source_name
    FROM {db.get_table_name('raw_articles')}
    ORDER BY crawl_time DESC
    LIMIT %s
    """

    try:
        with db.get_connection_ctx() as conn:
            if not conn:
                raise RuntimeError('无法获取数据库连接')

            if force:
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"""
                        SELECT window_start, window_end
                        FROM {db.get_table_name('events')}
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    )
                    last_batch = cursor.fetchone()
                    if last_batch:
                        last_start = last_batch.get('window_start')
                        last_end = last_batch.get('window_end')
                        cursor.execute(
                            f"""
                            DELETE FROM {db.get_table_name('event_articles')}
                            WHERE event_id IN (
                                SELECT id FROM {db.get_table_name('events')}
                                WHERE window_start=%s AND window_end=%s
                            )
                            """,
                            (last_start, last_end)
                        )
                        cursor.execute(
                            f"""
                            DELETE FROM {db.get_table_name('events')}
                            WHERE window_start=%s AND window_end=%s
                            """,
                            (last_start, last_end)
                        )
                conn.commit()

            with conn.cursor() as cursor:
                cursor.execute(articles_query, (int(limit),))
                articles = cursor.fetchall()

            total = len(articles)
            _nlp_events_state['total'] = total
            if total == 0:
                _nlp_events_state.update({
                    'status': 'success',
                    'progress': 100,
                    'message': '无可处理文章',
                    'current': 0
                })
                return

            clusters, meta = cluster_event_articles(
                articles=articles,
                embedding_max_length=embedding_max_length,
                embedding_batch_size=embedding_batch_size,
                vector_model_path=vector_model_path,
                similarity_threshold=float(similarity_threshold),
                min_cluster_size=int(min_cluster_size),
            )

            _nlp_events_state['message'] = f"聚类完成：{len(clusters)} 个事件簇"

            llm_cfg = get_llm_config() or {}
            llm_model = llm_cfg.get('model') if use_llm_frame else None

            created_events = 0
            for idx, cluster in enumerate(clusters, start=1):
                _nlp_events_state['current'] = idx
                _nlp_events_state['progress'] = int(idx * 100 / max(1, len(clusters)))

                cluster_articles = [articles[i] for i in cluster['indices']]
                frame = build_event_frame(cluster_articles=cluster_articles, use_llm=use_llm_frame)
                title = str(frame.get('title') or '热点事件')[:300]
                summary = str(frame.get('summary') or '')[:1000]

                with conn.cursor() as cursor:
                    cursor.execute(
                        f"""
                        INSERT INTO {db.get_table_name('events')}
                        (window_start, window_end, title, summary, frame_json, article_count)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            window_start,
                            window_end,
                            title,
                            summary,
                            json.dumps(frame, ensure_ascii=False),
                            int(cluster['size']),
                        )
                    )
                    event_id = cursor.lastrowid

                    for a in cluster_articles:
                        cursor.execute(
                            f"""
                            INSERT IGNORE INTO {db.get_table_name('event_articles')}
                            (event_id, article_id, score)
                            VALUES (%s, %s, %s)
                            """,
                            (int(event_id), int(a['id']), None)
                        )

                    for a in cluster_articles:
                        cursor.execute(
                            f"""
                            INSERT INTO {db.get_table_name('article_nlp_results')}
                            (article_id, task, provider, model, version, label, score, result_json)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                int(a['id']),
                                'event_assignment',
                                'model',
                                str(meta.get('model') or os.path.basename(str(vector_model_path))),
                                None,
                                str(event_id),
                                None,
                                json.dumps(
                                    {
                                        'event_id': int(event_id),
                                        'window_start': str(window_start),
                                        'window_end': str(window_end),
                                        'models': {'vector': str(vector_model_path)},
                                        'vectorizer': meta,
                                    },
                                    ensure_ascii=False
                                ),
                            )
                        )

                created_events += 1
                if created_events % 10 == 0:
                    conn.commit()

            conn.commit()

        _nlp_events_state.update({
            'status': 'success',
            'progress': 100,
            'message': f'处理完成：生成 {len(clusters)} 个事件',
        })
    except Exception as e:
        _nlp_events_state.update({
            'status': 'failed',
            'message': '处理失败',
            'last_error': str(e)
        })


@api_bp.route('/admin/nlp/events/run', methods=['POST'])
def admin_nlp_events_run():
    global _nlp_events_thread, _nlp_events_state

    payload = request.get_json(silent=True) or {}
    nlp_config = _get_nlp_config()
    limit = int(payload.get('limit', nlp_config.get('limit', 500)))
    min_cluster_size = int(payload.get('min_cluster_size', nlp_config.get('min_cluster_size', 3)))
    similarity_threshold = float(payload.get('similarity_threshold', nlp_config.get('similarity_threshold', 0.72)))
    force = bool(payload.get('force', True))

    if _nlp_events_thread and _nlp_events_thread.is_alive():
        return jsonify({'error': '事件聚合任务正在运行'}), 409

    _nlp_events_state.update({
        'status': 'running',
        'progress': 0,
        'message': '任务已启动',
        'total': 0,
        'current': 0,
        'last_error': ''
    })

    _nlp_events_thread = threading.Thread(
        target=_run_events_task,
        kwargs={
            'limit': limit,
            'min_cluster_size': min_cluster_size,
            'similarity_threshold': similarity_threshold,
            'force': force
        },
        daemon=True
    )
    _nlp_events_thread.start()

    task_id = f'events-{datetime.now().strftime("%Y%m%d%H%M%S")}'
    return jsonify({'ok': True, 'task_id': task_id})


@api_bp.route('/admin/nlp/events/status', methods=['GET'])
def admin_nlp_events_status():
    return jsonify(dict(_nlp_events_state))


@api_bp.route('/events', methods=['GET'])
def list_events():
    try:
        db = get_db()
        nlp_config = _get_nlp_config()
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        min_article_count = int(request.args.get('min_article_count', 3))
        offset = (page - 1) * limit

        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                if 'days' in request.args:
                    days = int(request.args.get('days', nlp_config.get('event_window_days', 3)))
                    window_end = datetime.now()
                    window_start = window_end - timedelta(days=days)
                    query = f"""
                    SELECT SQL_CALC_FOUND_ROWS id, window_start, window_end, title, summary, article_count, created_at
                    FROM {db.get_table_name('events')}
                    WHERE window_start >= %s AND window_end <= %s AND article_count >= %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """
                    cursor.execute(query, (window_start, window_end, min_article_count, limit, offset))
                    items = cursor.fetchall()
                    cursor.execute("SELECT FOUND_ROWS() as total")
                    total = int(cursor.fetchone()['total'])
                else:
                    cursor.execute(
                        f"""
                        SELECT window_start, window_end
                        FROM {db.get_table_name('events')}
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    )
                    last_batch = cursor.fetchone()
                    if not last_batch:
                        return jsonify({'items': [], 'page': page, 'limit': limit, 'total': 0})

                    window_start = last_batch.get('window_start')
                    window_end = last_batch.get('window_end')
                    query = f"""
                    SELECT SQL_CALC_FOUND_ROWS id, window_start, window_end, title, summary, article_count, created_at
                    FROM {db.get_table_name('events')}
                    WHERE window_start=%s AND window_end=%s AND article_count >= %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """
                    cursor.execute(query, (window_start, window_end, min_article_count, limit, offset))
                    items = cursor.fetchall()
                    cursor.execute("SELECT FOUND_ROWS() as total")
                    total = int(cursor.fetchone()['total'])

        return jsonify({'items': items, 'page': page, 'limit': limit, 'total': total})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/events/<int:event_id>', methods=['GET'])
def get_event_detail(event_id: int):
    try:
        db = get_db()
        event_query = f"""
        SELECT id, window_start, window_end, title, summary, frame_json, article_count, created_at
        FROM {db.get_table_name('events')}
        WHERE id=%s
        """
        articles_query = f"""
        SELECT a.id, a.title, a.publish_time, a.source_name
        FROM {db.get_table_name('event_articles')} ea
        JOIN {db.get_table_name('raw_articles')} a ON a.id = ea.article_id
        WHERE ea.event_id=%s
        ORDER BY a.publish_time DESC
        """

        with db.get_connection_ctx() as conn:
            with conn.cursor() as cursor:
                cursor.execute(event_query, (int(event_id),))
                event = cursor.fetchone()
                if not event:
                    return jsonify({'error': '事件不存在'}), 404

                frame = event.get('frame_json')
                try:
                    event['frame_json'] = json.loads(frame) if isinstance(frame, str) else (frame or {})
                except Exception:
                    event['frame_json'] = {}

                cursor.execute(articles_query, (int(event_id),))
                articles = cursor.fetchall()

        return jsonify({'event': event, 'articles': articles})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
