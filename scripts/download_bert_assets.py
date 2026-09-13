"""下载并缓存项目使用的 BERT 预训练权重与分词器。"""

import argparse
import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MODEL_ID = 'bert-base-chinese'
DEFAULT_OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'saved_models', 'pretrained', DEFAULT_MODEL_ID)


def parse_args():
    parser = argparse.ArgumentParser(description='下载 BERT 权重和分词器到项目目录')
    parser.add_argument('--model-id', default=DEFAULT_MODEL_ID, help='Hugging Face 模型 ID')
    parser.add_argument('--output-dir', default=DEFAULT_OUTPUT_DIR, help='下载输出目录')
    parser.add_argument('--force', action='store_true', help='已存在时强制重新下载')
    parser.add_argument('--timeout', type=int, default=120, help='下载超时时间（秒）')
    return parser.parse_args()


def validate_local_model(model_dir: str):
    required_files = ['config.json']
    tokenizer_files = ['vocab.txt', 'tokenizer.json']
    weight_files = ['model.safetensors', 'pytorch_model.bin']

    missing = [name for name in required_files if not os.path.exists(os.path.join(model_dir, name))]
    if missing:
        return False, f"缺少必要文件: {', '.join(missing)}"

    if not any(os.path.exists(os.path.join(model_dir, name)) for name in tokenizer_files):
        return False, '缺少分词器文件 vocab.txt 或 tokenizer.json'

    if not any(os.path.exists(os.path.join(model_dir, name)) for name in weight_files):
        return False, '缺少模型权重文件 model.safetensors 或 pytorch_model.bin'

    return True, '模型文件完整'


def main():
    args = parse_args()

    os.environ.setdefault('HF_HUB_DOWNLOAD_TIMEOUT', str(args.timeout))
    os.makedirs(args.output_dir, exist_ok=True)

    is_ready, message = validate_local_model(args.output_dir)
    if is_ready and not args.force:
        print(f"本地模型已可用: {args.output_dir}")
        print(message)
        return 0

    try:
        from transformers import BertForSequenceClassification, BertTokenizer
    except ImportError as exc:
        print(f"缺少 transformers 依赖: {exc}", file=sys.stderr)
        return 1

    print(f"开始下载模型: {args.model_id}")
    print(f"输出目录: {args.output_dir}")

    try:
        tokenizer = BertTokenizer.from_pretrained(args.model_id)
        tokenizer.save_pretrained(args.output_dir)

        model = BertForSequenceClassification.from_pretrained(args.model_id)
        model.save_pretrained(args.output_dir)
    except Exception as exc:
        print(f"下载失败: {exc}", file=sys.stderr)
        return 1

    is_ready, message = validate_local_model(args.output_dir)
    if not is_ready:
        print(f"下载后校验失败: {message}", file=sys.stderr)
        return 1

    print(f"下载完成: {args.output_dir}")
    print(message)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())