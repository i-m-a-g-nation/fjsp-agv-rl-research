"""Official API contract and local readiness checks, without external requests."""

import json
import os

import pytest

from src.ai_workflow.config import LLMConfig
from src.ai_workflow.runtime_budget import BudgetLimits, RunBudget


@pytest.fixture(autouse=True)
def clean_model_environment(monkeypatch):
    for name in ('OPENAI_API_KEY', 'OPENAI_BASE_URL', 'LLM_MODEL_NAME',
                 'LLM_THINKING_MODE', 'LLM_REASONING_EFFORT',
                 'LLM_MAX_OUTPUT_TOKENS', 'LLM_REQUEST_TIMEOUT_SECONDS',
                 'LLM_REQUEST_PROFILE',
                 'RAG_EMBEDDING_BACKEND', 'EMBEDDING_MODEL_NAME'):
        # Register even initially absent keys: the .env loader writes directly
        # to os.environ and must not leave synthetic credentials for later tests.
        monkeypatch.setenv(name, os.environ.get(name, ''))
        monkeypatch.delenv(name, raising=False)


def test_official_default_uses_flash_alias_and_explicit_bounded_call_mode():
    cfg = LLMConfig()
    assert cfg.base_url == 'https://api.deepseek.com'
    assert cfg.model_name == 'deepseek-flash'
    assert cfg.thinking_mode == 'disabled'
    assert cfg.reasoning_effort == 'max'
    assert cfg.extraction_repair_attempts == 1
    assert cfg.request_profile == 'bounded'
    assert cfg.chat_request_options() == {'max_tokens': None,
        'extra_body': {'thinking': {'type': 'disabled'}, 'max_tokens': 4096}}
    assert cfg.max_output_tokens == 4096 and cfg.max_retries == 0
    assert cfg.provider_timeout(output_tokens=4096) == 30.0


@pytest.mark.parametrize('tokens, timeout', [(1, 0.25), (8192, 60.0)])
def test_per_request_environment_profile_respects_existing_bounds(monkeypatch, tokens, timeout):
    monkeypatch.setenv('LLM_MAX_OUTPUT_TOKENS', str(tokens))
    monkeypatch.setenv('LLM_REQUEST_TIMEOUT_SECONDS', str(timeout))
    cfg = LLMConfig()
    assert type(cfg.max_output_tokens) is int
    assert cfg.max_output_tokens == tokens
    assert cfg.chat_request_options()['extra_body']['max_tokens'] == tokens
    assert cfg.provider_timeout(output_tokens=tokens) == timeout


@pytest.mark.parametrize('value', ['', 'abc', '4096.0', '1.5', 'true', 'NaN', 'inf', '-1', '0', '8193'])
def test_invalid_token_environment_profile_is_rejected(monkeypatch, value):
    monkeypatch.setenv('LLM_MAX_OUTPUT_TOKENS', value)
    with pytest.raises(ValueError):
        LLMConfig()


@pytest.mark.parametrize('value', ['', 'abc', 'true', 'NaN', 'inf', '-inf', '1e309', '-1', '0', '60.01'])
def test_invalid_timeout_environment_profile_is_rejected(monkeypatch, value):
    monkeypatch.setenv('LLM_REQUEST_TIMEOUT_SECONDS', value)
    with pytest.raises(ValueError):
        LLMConfig()


@pytest.mark.parametrize('options', [
    {'max_output_tokens': 8193}, {'request_timeout_seconds': 61},
])
def test_default_request_profile_keeps_existing_constructor_caps(options):
    with pytest.raises(ValueError, match='bounds'):
        LLMConfig(**options)


def test_paper_excerpt_profile_requires_explicit_constructor_opt_in(monkeypatch):
    monkeypatch.setenv('LLM_REQUEST_PROFILE', 'paper_excerpt')
    assert LLMConfig().request_profile == 'bounded'
    with pytest.raises(ValueError, match='bounds'):
        LLMConfig(max_output_tokens=16384, request_timeout_seconds=120)


@pytest.mark.parametrize('budget', [None, True, object()])
def test_paper_excerpt_profile_requires_real_run_budget(budget):
    with pytest.raises(ValueError, match='RunBudget'):
        LLMConfig(request_profile='paper_excerpt', budget=budget,
                  max_output_tokens=16384, request_timeout_seconds=120)


@pytest.mark.parametrize('profile', ['', 'paper', 'PAPER_EXCERPT', True, False, None, 1])
def test_unknown_or_non_string_request_profile_is_rejected(profile):
    with pytest.raises(ValueError, match='request_profile'):
        LLMConfig(request_profile=profile)


@pytest.mark.parametrize('options', [
    {'max_output_tokens': 16385}, {'request_timeout_seconds': 120.01},
    {'max_output_tokens': 0}, {'max_output_tokens': True},
    {'request_timeout_seconds': float('inf')}, {'max_retries': 2},
    {'max_retries': True},
])
def test_paper_excerpt_profile_keeps_finite_token_timeout_and_retry_caps(tmp_path, options):
    budget = RunBudget(tmp_path / 'budget.sqlite', BudgetLimits())
    with pytest.raises(ValueError, match='bounds'):
        LLMConfig(request_profile='paper_excerpt', budget=budget, **options)


def test_paper_excerpt_profile_preserves_budget_reservation_and_timeout_clamp(tmp_path):
    from src.ai_workflow.runtime_budget import BudgetExceeded

    budget = RunBudget(tmp_path / 'budget.sqlite', BudgetLimits(
        max_active_seconds=50, max_provider_calls=2, max_output_tokens=32768))
    cfg = LLMConfig(request_profile='paper_excerpt', budget=budget,
                    max_output_tokens=16384, request_timeout_seconds=120, max_retries=1)
    assert cfg.provider_timeout(output_tokens=16384) == 50
    snapshot = budget.snapshot()
    assert snapshot['provider_calls'] == 2
    assert snapshot['output_tokens_reserved'] == 32768
    with pytest.raises(BudgetExceeded):
        cfg.provider_timeout(output_tokens=16384)


def test_paper_excerpt_profile_is_part_of_identity_without_exposing_key(tmp_path):
    from src.ai_workflow.sessions import _config_values

    budget = RunBudget(tmp_path / 'budget.sqlite', BudgetLimits())
    bounded = LLMConfig(api_key='sk-offline-sentinel', budget=budget)
    paper = LLMConfig(api_key='sk-offline-sentinel', budget=budget, request_profile='paper_excerpt')
    assert bounded != paper
    assert _config_values(bounded) != _config_values(paper)
    assert _config_values(paper)['request_profile'] == 'paper_excerpt'
    assert 'api_key' not in _config_values(paper)
    assert 'sk-offline-sentinel' not in repr(paper)


def test_thinking_environment_is_explicit_and_options_are_detached(monkeypatch):
    monkeypatch.setenv('LLM_THINKING_MODE', 'enabled')
    cfg = LLMConfig()
    options = cfg.chat_request_options()
    assert options['extra_body']['thinking']['type'] == 'enabled'
    assert options['extra_body']['reasoning_effort'] == 'max'
    options['extra_body']['thinking']['type'] = 'disabled'
    options['extra_body']['reasoning_effort'] = 'low'
    assert cfg.chat_request_options()['extra_body']['thinking']['type'] == 'enabled'
    assert cfg.chat_request_options()['extra_body']['reasoning_effort'] == 'max'


@pytest.mark.parametrize('effort', ['low', 'high', 'max'])
def test_reasoning_effort_environment_reaches_enabled_official_request(monkeypatch, effort):
    monkeypatch.setenv('LLM_REASONING_EFFORT', effort)
    cfg = LLMConfig(thinking_mode='enabled')
    assert cfg.reasoning_effort == effort
    assert cfg.chat_request_options()['extra_body']['reasoning_effort'] == effort


@pytest.mark.parametrize('effort', ['low', 'high', 'max'])
def test_disabled_thinking_omits_reasoning_effort(effort):
    cfg = LLMConfig(thinking_mode='disabled', reasoning_effort=effort)
    assert cfg.chat_request_options() == {'max_tokens': None,
        'extra_body': {'thinking': {'type': 'disabled'}, 'max_tokens': 4096}}


@pytest.mark.parametrize('effort', ['medium', 'MAX', 'enabled', '', True, 1, None])
def test_invalid_reasoning_effort_is_rejected(effort):
    with pytest.raises(ValueError, match='reasoning_effort'):
        LLMConfig(reasoning_effort=effort)


@pytest.mark.parametrize('attempts', [0, 1])
def test_extraction_repair_limit_accepts_bounded_integers(attempts):
    assert LLMConfig(extraction_repair_attempts=attempts).extraction_repair_attempts == attempts


@pytest.mark.parametrize('attempts', [-1, 2, True, False, 0.0, 1.0, '1', None])
def test_extraction_repair_limit_rejects_non_integers_and_out_of_bounds(attempts):
    with pytest.raises(ValueError, match='extraction_repair_attempts'):
        LLMConfig(extraction_repair_attempts=attempts)


@pytest.mark.parametrize('mode', ['on', '', 'false', True, None])
def test_invalid_thinking_mode_is_rejected(mode):
    with pytest.raises(ValueError, match='thinking'):
        LLMConfig(thinking_mode=mode)


@pytest.mark.parametrize('url', ['https://api.example.org/v1', 'http://localhost:8123/v1',
                                 'https://api.deepseek.com.example.org'])
def test_generic_hosts_do_not_receive_deepseek_only_fields(url):
    assert LLMConfig(base_url=url, thinking_mode='enabled').chat_request_options() == {'max_tokens': 4096}


def test_key_does_not_appear_in_config_repr_or_session_identity():
    from src.ai_workflow.sessions import _config_values
    cfg = LLMConfig(api_key='sk-offline-sentinel', thinking_mode='enabled')
    assert 'sk-offline-sentinel' not in repr(cfg)
    fields = _config_values(cfg)
    assert fields['thinking_mode'] == 'enabled'
    assert fields['reasoning_effort'] == 'max'
    assert fields['extraction_repair_attempts'] == 1
    assert 'api_key' not in fields
    assert fields != _config_values(LLMConfig(thinking_mode='disabled'))
    assert fields != _config_values(LLMConfig(thinking_mode='enabled', reasoning_effort='high'))
    assert fields != _config_values(LLMConfig(thinking_mode='enabled', extraction_repair_attempts=0))


@pytest.mark.parametrize('operation', ['extract', 'generate'])
@pytest.mark.parametrize('mode', ['enabled', 'disabled'])
@pytest.mark.parametrize('effort', ['max', 'high', 'low'])
@pytest.mark.parametrize('tokens, timeout, profile', [
    (4096, 30.0, 'bounded'), (8192, 60.0, 'bounded'), (16384, 120.0, 'paper_excerpt'),
])
def test_both_pipeline_calls_serialize_official_chat_payload_in_memory(monkeypatch, tmp_path, operation, mode, effort, tokens, timeout, profile):
    import httpx
    import langchain_openai
    from src.ai_workflow.langgraph_pipeline import _llm_extract_paper, _llm_generate_rule_code

    captured = []
    monkeypatch.setenv('LLM_MAX_OUTPUT_TOKENS', str(tokens))
    monkeypatch.setenv('LLM_REQUEST_TIMEOUT_SECONDS', str(timeout))
    original = langchain_openai.ChatOpenAI
    text = (json.dumps({'title': 'Paper', 'problem_type': 'FJSP', 'math_model': {},
                       'rl_formulation': {}, 'codebase_alignment': {}}) if operation == 'extract'
            else '```python\ndef ai_select_candidate(candidates, instance, rng=None):\n    return candidates[0]\n```')

    def respond(request):
        captured.append((request.url.path, json.loads(request.content), request.extensions['timeout']))
        return httpx.Response(200, json={
            'id': 'offline-chat', 'object': 'chat.completion', 'created': 0,
            'model': 'deepseek-flash', 'choices': [{'index': 0, 'finish_reason': 'stop',
                'message': {'role': 'assistant', 'content': text}}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 2, 'total_tokens': 3},
        })

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        monkeypatch.setattr(langchain_openai, 'ChatOpenAI', lambda **kw: original(http_client=client, **kw))
        budget = (RunBudget(tmp_path / 'budget.sqlite', BudgetLimits(
            max_active_seconds=300, max_provider_calls=4, max_output_tokens=32768))
            if profile == 'paper_excerpt' else None)
        cfg = LLMConfig(api_key='sk-offline-sentinel', thinking_mode=mode, reasoning_effort=effort,
                        request_profile=profile, budget=budget)
        if operation == 'extract':
            report = _llm_extract_paper(cfg, 'Paper', 'An input paragraph.', 'full_text', [], '', [], [], [])
            assert report.title == 'Paper' and report.evidence_status == 'unverified'
        else:
            assert 'def ai_select_candidate' in _llm_generate_rule_code(cfg, {}, [], '', 1)
    assert len(captured) == 1
    path, payload, request_timeout = captured[0]
    assert path == '/chat/completions'
    assert payload['model'] == 'deepseek-flash'
    assert payload['thinking'] == {'type': mode}
    if mode == 'enabled':
        assert payload['reasoning_effort'] == effort
    else:
        assert 'reasoning_effort' not in payload
    assert payload['max_tokens'] == tokens
    assert request_timeout['read'] == timeout
    assert 'max_completion_tokens' not in payload
    assert payload['messages'] and 'extra_body' not in payload


def test_config_checker_loads_explicit_file_without_printing_key(tmp_path, capsys):
    from scripts.check_model_config import main
    path = tmp_path / 'local.env'
    path.write_text('OPENAI_API_KEY=sk-offline-sentinel\nLLM_THINKING_MODE=enabled\n'
                    'LLM_REASONING_EFFORT=max\n', encoding='utf-8')
    assert not LLMConfig().has_api_key
    assert main(['--env-file', str(path)]) == 0
    output = capsys.readouterr().out
    assert 'deepseek-flash' in output and 'enabled' in output
    assert 'reasoning_effort=max' in output
    assert 'extraction_repair_attempts=1' in output
    assert 'max_output_tokens=4096' in output
    assert 'request_timeout_seconds=30.0' in output
    assert 'sk-offline-sentinel' not in output
    assert 'not tested' in output


def test_example_settings_explicitly_choose_max_thinking(capsys):
    from scripts.check_model_config import ROOT, main
    assert main(['--env-file', str(ROOT / '.env.example')]) == 1
    output = capsys.readouterr().out
    assert 'thinking_mode=enabled' in output
    assert 'reasoning_effort=max' in output
    assert 'max_output_tokens=8192' in output
    assert 'request_timeout_seconds=60.0' in output
    assert 'api_key_configured=False' in output


def test_invalid_effort_environment_fails_safely_without_echoing_secret(tmp_path, monkeypatch, capsys):
    from scripts.check_model_config import main
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-offline-sentinel')
    monkeypatch.setenv('LLM_REASONING_EFFORT', 'sk-offline-sentinel')
    path = tmp_path / 'local.env'
    path.write_text('', encoding='utf-8')
    assert main(['--env-file', str(path)]) == 1
    output = capsys.readouterr().out
    assert 'NOT_READY' in output
    assert 'sk-offline-sentinel' not in output


@pytest.mark.parametrize('name, value', [
    ('LLM_MAX_OUTPUT_TOKENS', '8193'), ('LLM_MAX_OUTPUT_TOKENS', '4096.0'),
    ('LLM_REQUEST_TIMEOUT_SECONDS', '60.01'), ('LLM_REQUEST_TIMEOUT_SECONDS', 'NaN'),
    ('LLM_MAX_OUTPUT_TOKENS', 'sk-offline-sentinel'),
    ('LLM_REQUEST_TIMEOUT_SECONDS', 'sk-offline-sentinel'),
])
def test_checker_hides_invalid_per_request_environment_values(tmp_path, monkeypatch, capsys, name, value):
    from scripts.check_model_config import main
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-offline-sentinel')
    monkeypatch.setenv(name, value)
    path = tmp_path / 'local.env'
    path.write_text('', encoding='utf-8')
    assert main(['--env-file', str(path)]) == 1
    output = capsys.readouterr().out
    assert 'NOT_READY' in output
    assert 'sk-offline-sentinel' not in output


def test_process_environment_takes_precedence_over_dotenv(tmp_path, monkeypatch, capsys):
    from scripts.check_model_config import main
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-existing-sentinel')
    monkeypatch.setenv('LLM_MODEL_NAME', 'deepseek-v4-pro')
    monkeypatch.setenv('LLM_MAX_OUTPUT_TOKENS', '1024')
    monkeypatch.setenv('LLM_REQUEST_TIMEOUT_SECONDS', '5.5')
    path = tmp_path / 'local.env'
    path.write_text('OPENAI_API_KEY=sk-file-sentinel\nLLM_MODEL_NAME=deepseek-flash\n'
                    'LLM_MAX_OUTPUT_TOKENS=8192\nLLM_REQUEST_TIMEOUT_SECONDS=60\n', encoding='utf-8')
    assert main(['--env-file', str(path)]) == 0
    output = capsys.readouterr().out
    assert 'deepseek-v4-pro' in output
    assert 'max_output_tokens=1024' in output
    assert 'request_timeout_seconds=5.5' in output
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
