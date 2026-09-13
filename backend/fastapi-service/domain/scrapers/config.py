"""配置加载模块

提供从 config.yaml 读取/写入配置的功能
"""

import os
import logging
import yaml


def load_config():
    """加载 scrapers/config.yaml 配置文件"""
    config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            return config if isinstance(config, dict) else {}
    except Exception as e:
        logging.getLogger(__name__).exception("加载配置文件失败: %s", e)
        return {}


def save_config(config: dict):
    """保存 scrapers/config.yaml 配置文件"""
    config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    tmp_path = f"{config_path}.tmp"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(
            config if isinstance(config, dict) else {},
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
    os.replace(tmp_path, config_path)


def update_config(patch: dict) -> dict:
    """合并更新配置并写回磁盘，返回写回后的完整配置。"""
    def deep_merge(target: dict, src: dict) -> dict:
        if not isinstance(target, dict) or not isinstance(src, dict):
            return target
        for key, value in src.items():
            if isinstance(target.get(key), dict) and isinstance(value, dict):
                deep_merge(target[key], value)
            else:
                target[key] = value
        return target

    config = load_config()
    if not isinstance(config, dict):
        config = {}
    if isinstance(patch, dict):
        deep_merge(config, patch)
    save_config(config)
    return config

