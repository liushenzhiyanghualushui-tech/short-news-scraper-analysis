import json
import logging
from typing import Any, Dict, Optional

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

from .config import load_config

logger = logging.getLogger(__name__)


class LLMUnavailableError(RuntimeError):
    pass


def get_llm_config() -> Optional[Dict[str, Any]]:
    sys_config = load_config()
    llm_config = (sys_config or {}).get('llm', {}) or {}

    api_key = llm_config.get('api_key')
    if not api_key or api_key == 'sk-...':
        return None

    return {
        'enabled': bool(llm_config.get('enabled', False)),
        'api_base': llm_config.get('api_base', 'https://api.openai.com/v1'),
        'api_key': api_key,
        'model': llm_config.get('model', 'gpt-3.5-turbo'),
        'temperature': float(llm_config.get('temperature', 0.1)),
        'max_tokens': int(llm_config.get('max_tokens', 256)),
    }


def _create_client(llm_config: Dict[str, Any]):
    if OpenAI is None:
        raise LLMUnavailableError('openai 库不可用')
    return OpenAI(api_key=llm_config['api_key'], base_url=llm_config['api_base'])


def chat_json(
    *,
    system_prompt: str,
    user_content: str,
    schema_hint: str,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None
) -> Dict[str, Any]:
    llm_config = get_llm_config()
    if not llm_config:
        raise LLMUnavailableError('缺少 LLM 配置或 API Key 无效')

    client = _create_client(llm_config)
    resolved_model = model or llm_config['model']
    resolved_temperature = llm_config['temperature'] if temperature is None else float(temperature)
    resolved_max_tokens = llm_config['max_tokens'] if max_tokens is None else int(max_tokens)

    full_system_prompt = (
        f"{system_prompt}\n\n"
        "严格要求：只输出 JSON，不要输出任何额外文字。\n"
        f"JSON schema 提示：{schema_hint}"
    )

    response = client.chat.completions.create(
        model=resolved_model,
        messages=[
            {'role': 'system', 'content': full_system_prompt},
            {'role': 'user', 'content': user_content},
        ],
        temperature=resolved_temperature,
        max_tokens=resolved_max_tokens,
    )

    content = (response.choices[0].message.content or '').strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f'LLM 未返回有效 JSON: {exc}') from exc
