import logging
import os
from typing import Any, Dict, Optional


def setup_logging(config: Optional[Dict[str, Any]] = None) -> None:
    logging_config = (config or {}).get('logging') if isinstance(config, dict) else None
    if not isinstance(logging_config, dict):
        logging_config = {}

    level_name = str(logging_config.get('level') or 'INFO').upper()
    level = getattr(logging, level_name, logging.INFO)

    fmt = logging_config.get('format') or '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(fmt)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    has_console_handler = any(
        isinstance(handler, logging.StreamHandler) and getattr(handler, 'stream', None) is not None
        for handler in root_logger.handlers
    )
    if not has_console_handler:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    file_config = logging_config.get('file')
    if not isinstance(file_config, dict):
        return

    enabled = bool(file_config.get('enabled', False))
    if not enabled:
        return

    file_path = file_config.get('path')
    if not file_path:
        return

    normalized_path = os.path.abspath(str(file_path))
    file_dir = os.path.dirname(normalized_path)
    if file_dir:
        os.makedirs(file_dir, exist_ok=True)

    has_same_file_handler = any(
        isinstance(handler, logging.FileHandler)
        and os.path.abspath(getattr(handler, 'baseFilename', '')) == normalized_path
        for handler in root_logger.handlers
    )
    if has_same_file_handler:
        return

    file_handler = logging.FileHandler(normalized_path, encoding='utf-8')
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
