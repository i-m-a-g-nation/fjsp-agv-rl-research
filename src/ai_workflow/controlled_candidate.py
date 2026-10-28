"""Materialize one exact, versioned policy template in an owned batch directory.

This boundary never applies a patch to repository sources. Executable bytes must
match the registered template; documents and model replies cannot supply code.
"""
import difflib
import math
from pathlib import Path
import sys
import time
import types

import numpy as np

from src.ai_workflow.contracts import get_research_contract
from src.ai_workflow.research_tasks import ROOT, DEFAULT_REFERENCE, encoded, read_json, sha
from src.graduation.validation_diagnostics import _path_inside

TEMPLATE = ROOT / 'src/graduation/candidate_templates/shared_scorer.py'
KINDS = {'materialize_shared_scorer': 'controlled_candidate_materialization',
         'check_shared_scorer': 'controlled_candidate_check',
         'compare_shared_scorer': 'controlled_candidate_comparison',
         'diagnose_rejected_candidate': 'rejected_candidate_diagnosis',
         'compare_larger_step': 'controlled_candidate_step_comparison'}
PROTECTED = {'src/graduation/rl_environment.py', 'src/graduation/feasibility.py',
    'src/graduation/metrics.py', 'src/graduation/neural_policy.py', 'src/graduation/policy_training.py',
    'src/graduation/solver.py', 'src/ai_workflow/contracts.py'}


def _write(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(encoded(value))
    temporary.replace(path)


def _context(batch):
    batch = Path(batch).resolve()
    spec = read_json(batch / 'spec.json')['identity']
    if spec.get('profile') not in ('shared_scorer_v1', 'shared_scorer_feedback_v1'):
        raise ValueError('Candidate requires an explicit registered candidate profile')
    hashes = spec['source_hashes']
    if not PROTECTED <= hashes.keys():
        raise ValueError('Missing protected source identity')
    for relative, expected in hashes.items():
        if sha(_path_inside(ROOT, relative).read_bytes()) != expected:
            raise ValueError('Candidate protected source identity changed')
    contracts = {name: get_research_contract(name).contract_hash for name in ('graduation', 'innovation')}
    if any(spec['contracts'][name]['contract_hash'] != value for name, value in contracts.items()):
        raise ValueError('Candidate contract identity changed')
    folder = batch / 'candidate'
    if folder.is_symlink() or not folder.resolve().is_relative_to(batch):
        raise ValueError('Candidate directory escapes its batch')
    return batch, folder, hashes, contracts


def _artifact_hashes(batch, paths):
    return {path.relative_to(batch).as_posix(): sha(path.read_bytes()) for path in paths}


def materialize_candidate(batch):
    batch, folder, protected, contracts = _context(batch)
    if folder.exists():
        raise ValueError('Candidate package already exists')
    folder.mkdir()
    source = TEMPLATE.read_bytes()
    (folder / 'policy.py').write_bytes(source)
    patch = ''.join(difflib.unified_diff([], source.decode('utf-8').splitlines(keepends=True),
                                        fromfile='/dev/null', tofile='candidate/policy.py'))
    (folder / 'candidate.patch').write_text(patch, encoding='utf-8', newline='')
    manifest = {'version': 1, 'profile': 'shared_scorer_v1', 'template_sha256': sha(source),
        'files_sha256': {name: sha((folder / name).read_bytes()) for name in ('policy.py', 'candidate.patch')},
        'protected_source_hashes': protected, 'contract_hashes': contracts}
    _write(folder / 'manifest.json', manifest)
    return {'kind': KINDS['materialize_shared_scorer'], 'status': 'COMPLETED',
        'research_status': 'not_achieved', 'template_sha256': sha(source),
        'repository_patch_applied': False, 'artifacts': _artifact_hashes(batch, sorted(folder.iterdir()))}


def _package(batch):
    batch, folder, protected, contracts = _context(batch)
    manifest = read_json(folder / 'manifest.json')
    source = (folder / 'policy.py').read_bytes()
    if (manifest.get('profile') != 'shared_scorer_v1' or sha(source) != sha(TEMPLATE.read_bytes())
            or manifest.get('template_sha256') != sha(source)
            or manifest.get('protected_source_hashes') != protected or manifest.get('contract_hashes') != contracts
            or set(manifest['files_sha256']) != {'policy.py', 'candidate.patch'}):
        raise ValueError('Candidate template/package identity mismatch')
    for relative, expected in manifest['files_sha256'].items():
        if sha(_path_inside(folder.resolve(), relative).read_bytes()) != expected:
            raise ValueError('Candidate file identity mismatch')
    if any(p.is_symlink() or not p.is_file() or p.name not in
           {'policy.py', 'candidate.patch', 'manifest.json', 'checks.json'} for p in folder.iterdir()):
        raise ValueError('Unregistered candidate package content')
    return batch, folder, manifest, source


def load_candidate(batch):
    _, folder, manifest, source = _package(batch)
    # Only these exact versioned bytes reach compile/exec. No import path from a paper/model is accepted.
    name = '_fjsp_shared_candidate_' + sha(str(folder).encode()) + manifest['template_sha256']
    module = types.ModuleType(name)
    module.__file__ = str(folder / 'policy.py')
    sys.modules[name] = module
    try:
        exec(compile(source, module.__file__, 'exec'), module.__dict__)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module.SharedScorer


def _deadline(callback):
    started = time.monotonic()
    def check():
        if time.monotonic() - started >= 120:
            raise TimeoutError('Candidate check active-time cap expired')
        if callback is not None:
            callback()
    return check


def check_candidate(batch, reference_archive=DEFAULT_REFERENCE, *, check_budget=None):
    from src.graduation.neural_policy import PolicySample, policy_features
    from src.graduation.permutation_diagnostics import _read, _permutation
    from src.graduation.rl_environment import ParallelMaintenanceEnv
    from src.graduation.policy_training import run_policy_episode
    from src.graduation.state_encoding import encode_construction_observation as encode

    budget = _deadline(check_budget)
    budget()
    _, folder, _, _ = _package(batch)
    if (folder / 'checks.json').exists():
        raise ValueError('Candidate checks already exist')
    actor_class = load_candidate(batch)
    reference_manifest, reference_hash, _, validation, _, _ = _read(Path(reference_archive).resolve(), budget)
    actor = actor_class(seed=17)
    parameters = actor.state_dict()
    count = sum(v.size for v in parameters.values())
    if count != 545:
        raise ValueError('Candidate parameter schema differs')
    observation = ParallelMaintenanceEnv(validation[0], mode='fixed').observe()
    sample = PolicySample(policy_features(encode(observation)), observation.action_mask,
                          next(i for i, legal in enumerate(observation.action_mask) if legal), -.5)
    _, gradient = actor.log_probability_gradient(sample)
    max_gradient_error, gradient_count = 0., 0
    for name, array in parameters.items():
        for index in np.ndindex(array.shape):
            budget()
            values = []
            for sign in (-1, 1):
                changed = {k: v.copy() for k, v in parameters.items()}
                changed[name][index] += sign * 1e-6
                values.append(actor_class.from_state(changed).log_probability_gradient(sample)[0])
            numerical = (values[1] - values[0]) / 2e-6
            max_gradient_error = max(max_gradient_error, abs(float(gradient[name][index]) - numerical))
            gradient_count += 1
    if max_gradient_error > 2e-6:
        raise ValueError('Candidate gradient check failed')
    states, max_error = 0, 0.
    for mode in ('fixed', 'joint'):
        for data in validation:
            episode = run_policy_episode(data, mode=mode, actor=actor, seed=17, deterministic=True,
                                         check_budget=budget)
            for permutation in ('identity', 'jobs_reverse', 'machines_reverse', 'both_reverse'):
                relabeled, _, _, action_map = _permutation(data, permutation)
                original = ParallelMaintenanceEnv(data, mode=mode)
                mapped = ParallelMaintenanceEnv(relabeled, mode=mode)
                for action in episode.actions:
                    budget()
                    p, q = actor.probabilities(encode(original.observe())), actor.probabilities(encode(mapped.observe()))
                    error = max(abs(p[i] - q[action_map[i]]) for i in range(100))
                    max_error = max(max_error, error)
                    original.step(action)
                    mapped.step(action_map[action])
                    states += 1
    if states != 192 or max_error > 1e-10:
        raise ValueError('Candidate same-state distribution check failed')
    checks = {'parameter_count': count, 'gradient_coordinates': gradient_count,
              'max_gradient_error': max_gradient_error, 'equivariance_states': states,
              'max_probability_error': max_error, 'original_checked_episodes': 8,
              'reference_manifest_sha256': reference_hash,
              'reference_results_sha256': reference_manifest['artifacts']['results.json'],
              'template_sha256': sha(TEMPLATE.read_bytes())}
    budget()
    _package(batch)
    _write(folder / 'checks.json', checks)
    return {'kind': KINDS['check_shared_scorer'], 'status': 'COMPLETED', 'research_status': 'not_achieved',
            'checks': checks, 'artifacts': _artifact_hashes(Path(batch).resolve(), sorted(folder.iterdir()))}


def compare_candidate(batch, reference_archive=DEFAULT_REFERENCE, *, trial='initial'):
    _completed_gate(batch)
    from src.ai_workflow.candidate_comparison import run_comparison
    result = run_comparison(batch, reference_archive, load_candidate(batch), trial=trial)
    _package(batch)
    return result


def _completed_gate(batch, check_budget=lambda: None):
    """The controller's completed task receipt, file and reference must agree."""
    batch = Path(batch).resolve()
    try:
        state = read_json(batch / 'state.json')
        entries = [(index, task) for index, task in enumerate(state['tasks'], 1)
                   if task['id'] == 'check_shared_scorer']
        if len(entries) != 1 or entries[0][1]['status'] != 'COMPLETED':
            raise ValueError('Missing completed candidate check receipt')
        index, task = entries[0]
        path = batch / f'task_{index:02d}.json'
        if sha(path.read_bytes()) != task['result_sha256']:
            raise ValueError('Candidate check receipt identity changed')
        receipt = read_json(path)
        verify_candidate_result('check_shared_scorer', receipt, batch, check_budget=check_budget)
        inputs = read_json(batch / 'spec.json')['input_hashes']
        checks = receipt['checks']
        if (checks['reference_manifest_sha256'] != inputs['validation/manifest.json']
                or checks['reference_results_sha256'] != inputs['validation/results.json']):
            raise ValueError('Candidate check reference identity changed')
    except (OSError, KeyError, TypeError) as exc:
        raise ValueError('Candidate requires a complete bound check receipt') from exc


def verify_candidate_result(task_id, result, batch, *, check_budget=lambda: None):
    check_budget()
    batch, _, _, _ = _package(batch)
    if (result.get('kind') != KINDS[task_id] or result.get('status') != 'COMPLETED'
            or result.get('research_status') != 'not_achieved'):
        raise ValueError('Invalid controlled candidate result')
    if task_id == 'diagnose_rejected_candidate':
        from src.ai_workflow.candidate_feedback import verify_diagnosis
        verify_diagnosis(result, batch, check_budget=check_budget)
        return
    artifacts = result.get('artifacts')
    if type(artifacts) is not dict or not 3 <= len(artifacts) <= 512:
        raise ValueError('Incomplete controlled candidate artifacts')
    for relative, expected in artifacts.items():
        check_budget()
        if not relative.startswith(('candidate/', 'candidate_run/', 'candidate_step_run/')):
            raise ValueError('Candidate artifact is outside owned outputs')
        if sha(_path_inside(batch, relative).read_bytes()) != expected:
            raise ValueError('Candidate artifact identity changed')
    if task_id == 'materialize_shared_scorer' and result.get('repository_patch_applied') is not False:
        raise ValueError('Candidate cannot modify repository sources')
    if task_id == 'check_shared_scorer':
        check = result['checks']
        if (check['parameter_count'] != 545 or check['gradient_coordinates'] != 545
                or check['equivariance_states'] != 192 or not 0 <= check['max_gradient_error'] <= 2e-6
                or not 0 <= check['max_probability_error'] <= 1e-10
                or check.get('original_checked_episodes') != 8
                or not {'candidate/manifest.json', 'candidate/policy.py', 'candidate/candidate.patch',
                        'candidate/checks.json'} <= artifacts.keys()
                or check != read_json(batch / 'candidate/checks.json')
                or check.get('template_sha256') != sha(TEMPLATE.read_bytes())):
            raise ValueError('Incomplete controlled candidate gate')
    if task_id in ('compare_shared_scorer', 'compare_larger_step'):
        if result.get('trial', 'initial') != ('initial' if task_id == 'compare_shared_scorer' else 'larger_step_v1'):
            raise ValueError('Comparison receipt belongs to another trial')
        expected = {'training_runs': 4, 'training_steps': 1536, 'candidate_validation_plans': 16,
            'control_validation_plans': 16, 'rule_reference_plans': 48,
            'cp_reference_plans': 8, 'equivariance_states': 384}
        if (result.get('counts') != expected or any(result.get(k) is not False for k in
                ('probe_evaluated', 'final_test_evaluated', 'production_default_changed'))
                or any(result.get(k) != 0 for k in ('model_api_calls', 'network_calls'))
                or result.get('training_performed') is not True):
            raise ValueError('Incomplete controlled comparison')
        for mode in ('fixed', 'joint'):
            decision = result['decisions'][mode]
            means = decision['mean_validation_tardiness']
            selected = 'shared_scorer_v1' if means['shared_scorer_v1'] < means['none'] else 'none'
            if (decision['status'] != 'DECIDED' or decision['selected_method'] != selected
                    or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in means.values())):
                raise ValueError('Inconsistent controlled comparison decision')
        _completed_gate(batch, check_budget)
        from src.ai_workflow.candidate_evidence import verify_comparison_evidence
        verify_comparison_evidence(batch, result, check_budget=check_budget)
