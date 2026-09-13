import os
from typing import Any, Dict, Optional, Tuple

import numpy as np

from .embeddings import LocalTransformerEmbedder


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_model_path(model_path: str) -> str:
    if not model_path:
        raise ValueError('缺少模型路径')
    model_path = str(model_path).strip()
    if not model_path:
        raise ValueError('缺少模型路径')
    if os.path.isabs(model_path):
        return model_path
    return os.path.normpath(os.path.join(_project_root(), model_path))


def vectorize_texts(
    *,
    texts,
    model_path: str,
    embedding_max_length: int = 256,
    embedding_batch_size: int = 16,
) -> Tuple[Any, Dict[str, Any]]:
    resolved = resolve_model_path(model_path)
    texts_list = list(texts)

    if os.path.isdir(resolved) and os.path.exists(os.path.join(resolved, 'config.json')):
        embedder = LocalTransformerEmbedder(
            resolved,
            max_length=int(embedding_max_length),
            batch_size=int(embedding_batch_size),
            normalize=True,
        )
        vectors = embedder.embed_texts(texts_list)
        return vectors, {'vectorizer': 'hf_encoder', 'model': os.path.basename(resolved)}

    if os.path.isfile(resolved) and resolved.lower().endswith('.pkl'):
        import pickle
        with open(resolved, 'rb') as file_obj:
            model_data = pickle.load(file_obj)
        vectorizer = model_data.get('vectorizer') if isinstance(model_data, dict) else None
        if vectorizer is None:
            raise ValueError('模型不包含 vectorizer，无法生成向量')
        vectors = vectorizer.transform(texts_list)
        return vectors, {'vectorizer': 'sklearn', 'model': os.path.basename(resolved)}

    if os.path.isdir(resolved):
        meta_path = os.path.join(resolved, 'metadata.pkl')
        if os.path.exists(meta_path):
            import pickle
            with open(meta_path, 'rb') as file_obj:
                meta = pickle.load(file_obj)
            vectorizer = meta.get('vectorizer') if isinstance(meta, dict) else None
            if vectorizer is not None:
                vectors = vectorizer.transform(texts_list)
                return vectors, {'vectorizer': 'sklearn', 'model': os.path.basename(resolved)}
        if os.path.exists(os.path.join(resolved, 'model_state.bin')) and os.path.exists(os.path.join(resolved, 'metadata.pkl')):
            try:
                import torch
                import torch.nn.functional as torchF
            except Exception as exc:
                raise RuntimeError('当前模型需要 torch/transformers 才能生成向量') from exc

            from .model_registry import load_classifier

            classifier = load_classifier(resolved)
            model = getattr(classifier, 'bert_model', None) or getattr(classifier, 'model', None)
            tokenizer = getattr(classifier, 'tokenizer', None)
            device = getattr(classifier, 'device', None)
            if model is None or tokenizer is None or device is None:
                raise ValueError('模型加载失败，无法生成向量')

            model.eval()
            batch_size = max(1, int(embedding_batch_size))
            max_length = max(8, int(embedding_max_length))

            all_vecs = []
            with torch.no_grad():
                for start in range(0, len(texts_list), batch_size):
                    batch = texts_list[start:start + batch_size]
                    inputs = tokenizer(
                        batch,
                        padding=True,
                        truncation=True,
                        max_length=max_length,
                        return_tensors='pt',
                    )
                    inputs = {k: v.to(device) for k, v in inputs.items()}

                    bert = getattr(model, 'bert', None)
                    convs = getattr(model, 'convs', None)
                    if bert is None or convs is None:
                        raise ValueError('模型结构不支持向量化')

                    outputs = bert(input_ids=inputs.get('input_ids'), attention_mask=inputs.get('attention_mask'))
                    sequence_output = outputs.last_hidden_state
                    pooled_output = outputs.pooler_output

                    conv_input = sequence_output.transpose(1, 2)
                    conv_features = []
                    for conv in convs:
                        activated = torch.relu(conv(conv_input))
                        pooled = torch.max(activated, dim=2).values
                        conv_features.append(pooled)

                    if conv_features:
                        textcnn_features = torch.cat(conv_features, dim=1)
                        combined = torch.cat([pooled_output, textcnn_features], dim=1)
                    else:
                        combined = pooled_output

                    combined = torchF.normalize(combined, p=2, dim=1)
                    all_vecs.append(combined.detach().cpu().numpy())

            vectors = np.concatenate(all_vecs, axis=0).astype(np.float32) if all_vecs else np.zeros((0, 0), dtype=np.float32)
            return vectors, {'vectorizer': 'bert_textcnn', 'model': os.path.basename(resolved)}

    raise ValueError('不支持的模型格式，无法生成向量')


def to_dense_distance_matrix(vectors, *, similarity_threshold: float) -> Tuple[Optional[np.ndarray], float]:
    distance_threshold = max(0.0, min(1.0, 1.0 - float(similarity_threshold)))

    try:
        import scipy.sparse as sp
    except Exception:
        sp = None

    if sp is not None and sp.issparse(vectors):
        from sklearn.metrics.pairwise import cosine_similarity
        sim = cosine_similarity(vectors)
        dist = 1.0 - sim
        return dist.astype(np.float32), distance_threshold

    return None, distance_threshold

