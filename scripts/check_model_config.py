"""Check local model settings without sending requests or displaying API keys."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ai_workflow.config import LLMConfig, load_dotenv_if_present


def check_configuration(config: LLMConfig) -> tuple[dict, list[str]]:
    """Return public settings and fixed diagnostics, not connection evidence."""
    errors = []
    valid_url = True
    official = False
    try:
        url = urlsplit(config.base_url)
        port = url.port
        official = url.hostname == 'api.deepseek.com'
        loopback = url.hostname in ('localhost', '127.0.0.1', '::1')
        valid_url = bool(url.hostname) and (url.scheme == 'https' or (url.scheme == 'http' and loopback))
        valid_url = valid_url and not any((url.username, url.password, url.query, url.fragment))
        valid_url = valid_url and not url.path.rstrip('/').endswith(('/chat/completions', '/responses', '/embeddings'))
        if official:
            valid_url = valid_url and port in (None, 443) and url.path.rstrip('/') in ('', '/v1')
    except (TypeError, ValueError, AttributeError):
        valid_url = False
    if not valid_url:
        errors.append('Base URL must be an SDK base address without credentials/query/fragment or a full API endpoint.')

    model_valid = isinstance(config.model_name, str) and bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}', config.model_name))
    if not model_valid:
        errors.append('Model ID is missing or malformed.')
    elif official and config.model_name not in ('deepseek-flash', 'deepseek-v4-pro'):
        errors.append('Official DeepSeek model ID must be deepseek-flash or deepseek-v4-pro; check provider-specific IDs.')
    if not config.has_api_key:
        errors.append('API key is missing; fill OPENAI_API_KEY in the local .env or process environment.')

    summary = {'base_url': config.base_url if valid_url else '<invalid; hidden>',
               'model': config.model_name if model_valid else '<invalid; hidden>',
               'thinking_mode': config.thinking_mode, 'reasoning_effort': config.reasoning_effort,
               'extraction_repair_attempts': config.extraction_repair_attempts,
               'max_output_tokens': config.max_output_tokens,
               'request_timeout_seconds': config.request_timeout_seconds,
               'embedding_backend': config.embedding_backend,
               'api_key_configured': config.has_api_key}
    # Even a credential accidentally reused in another public field stays hidden.
    if config.api_key:
        summary = {key: value.replace(config.api_key, '<redacted>') if isinstance(value, str) else value
                   for key, value in summary.items()}
    return summary, errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, help='Explicit local settings file; process environment takes precedence.')
    args = parser.parse_args(argv)
    path = args.env_file or ROOT / '.env'
    if args.env_file is not None and not path.is_file():
        print('NOT_READY: explicitly requested configuration file does not exist.')
        return 1
    load_dotenv_if_present(path)
    try:
        summary, errors = check_configuration(LLMConfig())
    except (TypeError, ValueError, AttributeError):
        print('NOT_READY: invalid local settings; check mode and numeric limits. Secret values are hidden.')
        return 1
    print('Local configuration only; API connectivity and model quality not tested.')
    print('Environment variables take precedence over .env.')
    for key, value in summary.items():
        print(f'{key}={value}')
    for error in errors:
        print(f'- {error}')
    print('NOT_READY' if errors else 'LOCAL_CONFIG_OK')
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
