"""Bounded JSON calls with public response diagnostics before answer parsing."""
from __future__ import annotations

from collections.abc import Callable
import json

from src.ai_workflow.config import LLMConfig
from src.ai_workflow.langgraph_pipeline import ModelOutputIncompleteError


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate answer field')
        result[key] = value
    return result


def request_json_answer(cfg: LLMConfig, *, system: str, prompt: str,
                        on_response: Callable[[dict], None] | None = None) -> tuple[dict, dict]:
    from langchain_openai import ChatOpenAI
    options = cfg.chat_request_options()
    # Preserve the documented HTTP body without SDK eager parse(), which hides
    # length-limited responses behind an exception before diagnostics are saved.
    options['extra_body'] = {**options.get('extra_body', {}), 'response_format': {'type': 'json_object'}}
    llm = ChatOpenAI(api_key=cfg.api_key, base_url=cfg.base_url, model=cfg.model_name,
        temperature=cfg.temperature, timeout=cfg.provider_timeout(output_tokens=cfg.max_output_tokens),
        max_retries=cfg.max_retries, **options)
    response = llm.invoke([('system', system), ('human', prompt)])
    raw = str(response.content).strip()
    metadata = getattr(response, 'response_metadata', None) or {}
    reason = metadata.get('finish_reason')
    allowed = {'stop', 'length', 'content_filter', 'tool_calls', 'insufficient_system_resource', 'aborted'}
    reason = reason if isinstance(reason, str) and reason in allowed else 'unknown'
    tokens = metadata.get('token_usage') or {}
    usage = {key: value for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')
             if type(value := tokens.get(key)) is int and value >= 0}
    reasoning = (tokens.get('completion_tokens_details') or {}).get('reasoning_tokens')
    if type(reasoning) is int and reasoning >= 0:
        usage['reasoning_tokens'] = reasoning
    diagnostic = {'finish_reason': reason, 'usage': usage, 'final_text_characters': len(raw),
                  'final_text': raw.replace(cfg.api_key, '<redacted>') if cfg.api_key else raw}
    if on_response:
        on_response({**diagnostic, 'usage': dict(usage)})
    try:
        if not raw or reason != 'stop':
            raise ModelOutputIncompleteError('JSON final answer did not finish normally')
        parsed = json.loads(raw, object_pairs_hook=_unique_fields,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite answer value')))
        if not isinstance(parsed, dict):
            raise ValueError('JSON answer must be an object')
        return parsed, diagnostic
    except (ValueError, TypeError, RuntimeError) as exc:
        exc.model_response = diagnostic
        raise
