import json

import pytest

from tests.test_graduation_backend import graduation_request


def test_cli_graduation_pauses_without_paper_and_all_test_reviews_end_unachieved(tmp_path, graduation_request):
    from experiments.exp_018_ai_rag_workflow import main
    folder = tmp_path / 'run'
    common = ['--track', 'graduation', '--session-dir', str(folder)]
    assert main([*common, '--graduation-request', str(graduation_request)]) == 3
    assert main([*common, '--status']) == 0
    assert not (folder / 'graduation_run').exists()
    for stage, expected_exit in [('scope', 3), ('evidence', 3), ('conclusion', 2)]:
        request = json.loads((folder / 'review-request.json').read_text(encoding='utf-8'))
        assert request['stage'] == stage
        decision = tmp_path / f'test-only-{stage}.json'
        decision.write_text(json.dumps({'stage': stage, 'artifact_hash': request['artifact_hash'],
            'decision': 'approve', 'reviewer': 'synthetic CLI test reviewer', 'note': 'TEST ONLY, no scientific acceptance'}), encoding='utf-8')
        assert main([*common, '--decision-file', str(decision)]) == expected_exit
    status = json.loads((folder / 'status.json').read_text(encoding='utf-8'))
    assert status['state']['acceptance']['research_status'] == 'not_achieved'
    assert status['state']['eval_passed'] and status['budget']['provider_calls'] == 0


@pytest.mark.parametrize('flags', [['--mode', 'live'], ['--track', 'innovation'],
    ['--experiment-protocol', 'other.json'], ['--allow-network-fetch'], ['--allow-fallback']])
def test_cli_rejects_mixed_or_online_routes_before_credentials(graduation_request, monkeypatch, flags):
    from experiments import exp_018_ai_rag_workflow as cli
    def forbidden(): pytest.fail('Graduation route must reject before loading credentials')
    monkeypatch.setattr(cli, 'load_dotenv_if_present', forbidden)
    assert cli.main(['--track', 'graduation', '--graduation-request', str(graduation_request), *flags]) == 1


def test_explicit_request_override_cannot_change_persistent_input(tmp_path, graduation_request):
    from experiments.exp_018_ai_rag_workflow import main
    common = ['--track', 'graduation', '--session-dir', str(tmp_path / 'run')]
    assert main([*common, '--graduation-request', str(graduation_request)]) == 3
    other = tmp_path / 'different.json'
    other.write_bytes(graduation_request.read_bytes())
    assert main([*common, '--graduation-request', str(other)]) == 1
