import os
from typing import Optional


def detect_saved_model_type(filepath: str) -> str:
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
    if 'nb' in normalized_path:
        return 'nb'
    if 'lr' in normalized_path or 'logistic' in normalized_path:
        return 'lr'
    return 'svm'


def build_classifier_by_type(model_type: str):
    from .model_builder import TextClassifier, BertClassifier, BertTextCNNClassifier, DeepLearningClassifier

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


def load_classifier(filepath: str, *, model_type: Optional[str] = None):
    resolved_type = (model_type or detect_saved_model_type(filepath)).lower()
    classifier = build_classifier_by_type(resolved_type)
    classifier.load(filepath)
    return classifier

