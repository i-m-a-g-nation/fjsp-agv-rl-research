"""A registered template can be materialized only inside its owned batch."""
import json
from pathlib import Path

import pytest

from src.ai_workflow import controlled_candidate as candidate
from src.ai_workflow.contracts import get_research_contract
from src.ai_workflow.research_controller import _source_hashes


def _record_gate(batch, receipt):
    raw = candidate.encoded(receipt)
    (batch / 'task_01.json').write_bytes(raw)
    (batch / 'state.json').write_text(json.dumps({'tasks': [{'id': 'check_shared_scorer',
        'status': 'COMPLETED', 'result_sha256': candidate.sha(raw)}]}), encoding='utf-8')
    spec_path = batch / 'spec.json'
    spec = json.loads(spec_path.read_text(encoding='utf-8'))
    spec['input_hashes'] = {'validation/manifest.json': receipt['checks']['reference_manifest_sha256'],
                          'validation/results.json': receipt['checks']['reference_results_sha256']}
    spec_path.write_text(json.dumps(spec), encoding='utf-8')


@pytest.fixture
def batch(tmp_path):
    folder = tmp_path / 'batch'
    folder.mkdir()
    spec = {'identity': {'profile': 'shared_scorer_v1', 'source_hashes': _source_hashes(),
            'contracts': {name: get_research_contract(name).to_dict() for name in ('graduation', 'innovation')}}}
    (folder / 'spec.json').write_text(json.dumps(spec), encoding='utf-8')
    return folder


def test_materialization_is_exact_add_only_and_never_changes_protected_sources(batch):
    before = _source_hashes()
    result = candidate.materialize_candidate(batch)
    assert result['status'] == 'COMPLETED'
    assert result['kind'] == 'controlled_candidate_materialization'
    assert (batch / 'candidate/policy.py').read_bytes() == candidate.TEMPLATE.read_bytes()
    patch = (batch / 'candidate/candidate.patch').read_text(encoding='utf-8')
    assert '+++ candidate/policy.py' in patch and '--- /dev/null' in patch
    assert _source_hashes() == before
    candidate.verify_candidate_result('materialize_shared_scorer', result, batch)
    with pytest.raises(ValueError, match='exists'):
        candidate.materialize_candidate(batch)


def test_tampered_template_cannot_execute_even_when_manifest_is_rehashed(batch):
    candidate.materialize_candidate(batch)
    source = batch / 'candidate/policy.py'
    source.write_text("raise RuntimeError('must never execute')", encoding='utf-8')
    manifest_path = batch / 'candidate/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['files_sha256']['policy.py'] = candidate.sha(source.read_bytes())
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='template|identity'):
        candidate.load_candidate(batch)


def test_protected_source_change_refuses_candidate_loading(batch):
    candidate.materialize_candidate(batch)
    spec_path = batch / 'spec.json'
    spec = json.loads(spec_path.read_text(encoding='utf-8'))
    spec['identity']['source_hashes']['src/graduation/rl_environment.py'] = '0'*64
    spec_path.write_text(json.dumps(spec), encoding='utf-8')
    with pytest.raises(ValueError, match='protected|identity'):
        candidate.load_candidate(batch)


def test_runtime_gate_exercises_copied_code_and_preserves_checkpoint_schema(batch):
    candidate.materialize_candidate(batch)
    result = candidate.check_candidate(batch)
    assert result['kind'] == 'controlled_candidate_check'
    assert result['checks']['parameter_count'] == 545
    assert result['checks']['gradient_coordinates'] == 545
    assert result['checks']['equivariance_states'] == 192
    assert result['checks']['max_probability_error'] <= 1e-10
    candidate.verify_candidate_result('check_shared_scorer', result, batch)
    actor = candidate.load_candidate(batch)(seed=17)
    assert actor.policy_kind == 'shared_scorer_v1'


def test_budget_interruption_leaves_package_and_does_not_claim_pass(batch):
    candidate.materialize_candidate(batch)
    def exhausted():
        raise TimeoutError('test cap')
    with pytest.raises(TimeoutError):
        candidate.check_candidate(batch, check_budget=exhausted)
    assert not (batch / 'candidate/checks.json').exists()


def test_profile_and_existing_candidate_directory_are_enforced(batch):
    spec_path = batch / 'spec.json'
    spec = json.loads(spec_path.read_text(encoding='utf-8'))
    spec['identity']['profile'] = 'audit_v1'
    spec_path.write_text(json.dumps(spec), encoding='utf-8')
    with pytest.raises(ValueError, match='profile'):
        candidate.materialize_candidate(batch)


def test_artifact_path_escape_and_empty_comparison_cannot_be_accepted(batch):
    candidate.materialize_candidate(batch)
    result = {'kind': 'controlled_candidate_comparison', 'status': 'COMPLETED',
              'research_status': 'not_achieved', 'artifacts': {'../outside': '0'*64}}
    with pytest.raises(ValueError):
        candidate.verify_candidate_result('compare_shared_scorer', result, batch)


def test_two_count_file_cannot_bypass_completed_check_receipt(batch, monkeypatch):
    candidate.materialize_candidate(batch)
    (batch / 'candidate/checks.json').write_text(json.dumps({
        'gradient_coordinates': 545, 'equivariance_states': 192}), encoding='utf-8')
    from src.ai_workflow import candidate_comparison
    calls = []
    monkeypatch.setattr(candidate_comparison, 'run_comparison', lambda *a, **k: calls.append(True))
    with pytest.raises(ValueError, match='gate|check|receipt'):
        candidate.compare_candidate(batch)
    assert calls == []


def test_declared_counts_and_materialization_hashes_are_not_training_evidence(batch):
    materialized = candidate.materialize_candidate(batch)
    _record_gate(batch, candidate.check_candidate(batch))
    result = {'kind': 'controlled_candidate_comparison', 'status': 'COMPLETED',
        'research_status': 'not_achieved', 'counts': {'training_runs': 4, 'training_steps': 1536,
            'candidate_validation_plans': 16, 'control_validation_plans': 16, 'rule_reference_plans': 48,
            'cp_reference_plans': 8, 'equivariance_states': 384},
        'probe_evaluated': False, 'final_test_evaluated': False, 'production_default_changed': False,
        'model_api_calls': 0, 'network_calls': 0, 'training_performed': True,
        'artifacts': materialized['artifacts'], 'decisions': {mode: {'status': 'DECIDED',
            'selected_method': 'shared_scorer_v1', 'mean_validation_tardiness': {'none': 10, 'shared_scorer_v1': 1}}
            for mode in ('fixed', 'joint')}}
    with pytest.raises(ValueError, match='comparison|training|artifact'):
        candidate.verify_candidate_result('compare_shared_scorer', result, batch)


def test_check_receipt_requires_identical_saved_checks_and_all_gate_artifacts(batch):
    candidate.materialize_candidate(batch)
    result = candidate.check_candidate(batch)
    result['artifacts'].pop('candidate/checks.json')
    with pytest.raises(ValueError, match='gate|check|artifact'):
        candidate.verify_candidate_result('check_shared_scorer', result, batch)
