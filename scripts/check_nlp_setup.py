import sys

from scrapers.config import load_config
from scrapers.llm_client import get_llm_config
from scrapers.embeddings import LocalTransformerEmbedder


def main() -> int:
    config = load_config() or {}
    nlp_cfg = (config.get('nlp') or {})
    print('nlp.enabled:', bool(nlp_cfg.get('enabled', False)))

    llm_cfg = get_llm_config()
    print('llm.available:', bool(llm_cfg))
    if llm_cfg:
        print('llm.api_base:', llm_cfg.get('api_base'))
        print('llm.model:', llm_cfg.get('model'))

    embedding_model = str(nlp_cfg.get('embedding_model', 'bert-base-chinese'))
    print('embedding.model:', embedding_model)
    try:
        embedder = LocalTransformerEmbedder(
            embedding_model,
            max_length=int(nlp_cfg.get('embedding_max_length', 256)),
            batch_size=1,
        )
        vec = embedder.embed_texts(['测试文本'])
        print('embedding.ok:', True, 'shape:', tuple(vec.shape))
    except Exception as e:
        print('embedding.ok:', False, 'error:', str(e))
        return 2

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
