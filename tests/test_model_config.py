"""Official API contract and local readiness checks, without external requests."""

import json
import os

import pytest

from src.ai_workflow.config import LLMConfig


@pytest.fixture(autouse=True)
def clean_model_environment(monkeypatch):
    for name in ('OPENAI_API_KEY', 'OPENAI_BASE_URL', 'LLM_MODEL_NAME',
                 'LLM_THINKING_MODE', 'RAG_EMBEDDING_BACKEND', 'EMBEDDING_MODEL_NAME'):
        # Register even initially absent keys: the .env loader writes directly
        # to os.environ and must not leave synthetic credentials for later tests.
        monkeypatch.setenv(name, os.environ.get(name, ''))
        monkeypatch.delenv(name, raising=False)


def test_official_default_uses_flash_alias_and_explicit_bounded_call_mode():
    cfg = LLMConfig()
    assert cfg.base_url == 'https://api.deepseek.com'
    assert cfg.model_name == 'deepseek-flash'
    assert cfg.thinking_mode == 'disabled'
    assert cfg.chat_request_options() == {'max_tokens': None,
        'extra_body': {'thinking': {'type': 'disabled'}, 'max_tokens': 4096}}
    assert cfg.max_output_tokens == 4096 and cfg.max_retries == 0


def test_thinking_environment_is_explicit_and_options_are_detached(monkeypatch):
    monkeypatch.setenv('LLM_THINKING_MODE', 'enabled')
    cfg = LLMConfig()
    options = cfg.chat_request_options()
    assert options['extra_body']['thinking']['type'] == 'enabled'
    options['extra_body']['thinking']['type'] = 'disabled'
    assert cfg.chat_request_options()['extra_body']['thinking']['type'] == 'enabled'


@pytest.mark.parametrize('mode', ['on', '', 'false', True, None])
def test_invalid_thinking_mode_is_rejected(mode):
    with pytest.raises(ValueError, match='thinking'):
        LLMConfig(thinking_mode=mode)


@pytest.mark.parametrize('url', ['https://api.example.org/v1', 'http://localhost:8123/v1',
                                 'https://api.deepseek.com.example.org'])
def test_generic_hosts_do_not_receive_deepseek_only_fields(url):
    assert LLMConfig(base_url=url).chat_request_options() == {'max_tokens': 4096}


def test_key_does_not_appear_in_config_repr_or_session_identity():
    from src.ai_workflow.sessions import _config_values
    cfg = LLMConfig(api_key='sk-offline-sentinel', thinking_mode='enabled')
    assert 'sk-offline-sentinel' not in repr(cfg)
    fields = _config_values(cfg)
    assert fields['thinking_mode'] == 'enabled'
    assert 'api_key' not in fields
    assert fields != _config_values(LLMConfig(thinking_mode='disabled'))


@pytest.mark.parametrize('operation', ['extract', 'generate'])
@pytest.mark.parametrize('mode', ['enabled', 'disabled'])
def test_both_pipeline_calls_serialize_official_chat_payload_in_memory(monkeypatch, operation, mode):
    import httpx
    import langchain_openai
    from src.ai_workflow.langgraph_pipeline import _llm_extract_paper, _llm_generate_rule_code

    captured = []
    original = langchain_openai.ChatOpenAI
    text = (json.dumps({'title': 'Paper', 'problem_type': 'FJSP', 'math_model': {},
                       'rl_formulation': {}, 'codebase_alignment': {}}) if operation == 'extract'
            else '```python\ndef ai_select_candidate(candidates, instance, rng=None):\n    return candidates[0]\n```')

    def respond(request):
        captured.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={
            'id': 'offline-chat', 'object': 'chat.completion', 'created': 0,
            'model': 'deepseek-flash', 'choices': [{'index': 0, 'finish_reason': 'stop',
                'message': {'role': 'assistant', 'content': text}}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 2, 'total_tokens': 3},
        })

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(langchain_openai, 'ChatOpenAI', lambda **kw: original(http_client=client, **kw))
        cfg = LLMConfig(api_key='sk-offline-sentinel', thinking_mode=mode)
        if operation == 'extract':
            report = _llm_extract_paper(cfg, 'Paper', 'An input paragraph.', 'full_text', [], '', [], [], [])
            assert report.title == 'Paper' and report.evidence_status == 'unverified'
        else:
            assert 'def ai_select_candidate' in _llm_generate_rule_code(cfg, {}, [], '', 1)
    assert len(captured) == 1
    path, payload = captured[0]
    assert path == '/chat/completions'
    assert payload['model'] == 'deepseek-flash'
    assert payload['thinking'] == {'type': mode}
    assert payload['max_tokens'] == 4096
    assert 'max_completion_tokens' not in payload
    assert payload['messages'] and 'extra_body' not in payload


def test_config_checker_loads_explicit_file_without_printing_key(tmp_path, capsys):
    from scripts.check_model_config import main
    path = tmp_path / 'local.env'
    path.write_text('OPENAI_API_KEY=sk-offline-sentinel\nLLM_THINKING_MODE=enabled\n', encoding='utf-8')
    assert not LLMConfig().has_api_key
    assert main(['--env-file', str(path)]) == 0
    output = capsys.readouterr().out
    assert 'deepseek-flash' in output and 'enabled' in output
    assert 'sk-offline-sentinel' not in output
    assert 'not tested' in output


def test_process_environment_takes_precedence_over_dotenv(tmp_path, monkeypatch, capsys):
    from scripts.check_model_config import main
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-existing-sentinel')
    monkeypatch.setenv('LLM_MODEL_NAME', 'deepseek-v4-pro')
    path = tmp_path / 'local.env'
    path.write_text('OPENAI_API_KEY=sk-file-sentinel\nLLM_MODEL_NAME=deepseek-flash\n', encoding='utf-8')
    assert main(['--env-file', str(path)]) == 0
    output = capsys.readouterr().out
    assert 'deepseek-v4-pro' in output
    assert 'sk-existing-sentinel' not in output and 'sk-file-sentinel' not in output
    assert os.environ['OPENAI_API_KEY'] == 'sk-existing-sentinel'


def test_missing_key_is_not_reported_as_connected(tmp_path, capsys):
    from scripts.check_model_config import main
    path = tmp_path / 'local.env'
    path.write_text('OPENAI_API_KEY=\n', encoding='utf-8')
    assert main(['--env-file', str(path)]) == 1
    output = capsys.readouterr().out
    assert 'NOT_READY' in output and 'api_key_configured=False' in output


@pytest.mark.parametrize('url', [
    'https://api.deepseek.com/chat/completions', 'https://api.deepseek.com/v1/chat/completions',
    'https://user:sk-offline-sentinel@api.deepseek.com',
    'https://api.deepseek.com?key=sk-offline-sentinel',
    'https://api.deepseek.com#sk-offline-sentinel', 'http://api.deepseek.com',
    'https://api.deepseek.com:invalid',
])
def test_checker_rejects_malformed_or_secret_bearing_base_without_echo(url, monkeypatch, tmp_path, capsys):
    from scripts.check_model_config import main
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-offline-sentinel')
    monkeypatch.setenv('OPENAI_BASE_URL', url)
    path = tmp_path / 'local.env'
    path.write_text('', encoding='utf-8')
    assert main(['--env-file', str(path)]) == 1
    assert 'sk-offline-sentinel' not in capsys.readouterr().out


def test_official_and_third_party_model_names_are_not_confused(monkeypatch, tmp_path, capsys):
    from scripts.check_model_config import main
    path = tmp_path / 'local.env'
    path.write_text('', encoding='utf-8')
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-offline-sentinel')
    monkeypatch.setenv('LLM_MODEL_NAME', 'deepseek-v4.1-flash-1017')
    assert main(['--env-file', str(path)]) == 1
    monkeypatch.setenv('OPENAI_BASE_URL', 'https://provider.example/compatible-mode/v1')
    assert main(['--env-file', str(path)]) == 0
    assert 'sk-offline-sentinel' not in capsys.readouterr().out


def test_explicit_missing_env_file_does_not_silently_succeed(tmp_path, monkeypatch, capsys):
    from scripts.check_model_config import main
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-offline-sentinel')
    assert main(['--env-file', str(tmp_path / 'missing.env')]) == 1
