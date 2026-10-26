"""Finite, offline tool registry for the first outer research batch.

Archive integrity is checked; a partial archive is never promoted into a full
source bundle or a human scientific approval. Text in an archive is data only.
"""

from pathlib import Path
import hashlib
import json
import math

from src.graduation.validation_diagnostics import _raw_fields, _decode, _path_inside


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REFERENCE = ROOT / 'experiments/results/exp_026_validation_iteration_v1'
DEFAULT_PAPER = ROOT / 'experiments/results/exp_023_state_semantic_v1'
TASK_KINDS = {'audit_paper_evidence': 'archived_paper_evidence_audit',
              'diagnose_identifier_permutations': 'validation_only_permutation_diagnosis',
              'materialize_shared_scorer': 'controlled_candidate_materialization',
              'check_shared_scorer': 'controlled_candidate_check',
              'compare_shared_scorer': 'controlled_candidate_comparison'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def read_json(path):
    raw = Path(path).read_bytes()
    if len(raw) > 32 * 1024 * 1024:
        raise ValueError('Research evidence exceeds the bounded file size')
    return _decode(raw.decode('utf-8-sig'))


def input_hashes(reference_archive, paper_archive, check_budget=lambda: None):
    """Hash opaque artifact bytes; do not decode unused splits or training logs."""
    result = {}
    for name, folder, field in (('validation', reference_archive, 'artifacts'),
                                ('paper', paper_archive, 'files_sha256')):
        root = Path(folder).resolve()
        manifest_bytes = (root / 'manifest.json').read_bytes()
        result[name + '/manifest.json'] = sha(manifest_bytes)
        manifest = _decode(manifest_bytes.decode('utf-8-sig'))
        mapping = manifest[field]
        if type(mapping) is not dict or not 1 <= len(mapping) <= 512:
            raise ValueError('Invalid bounded evidence manifest')
        for relative, expected in sorted(mapping.items()):
            check_budget()
            actual = sha(_path_inside(root, relative).read_bytes())
            if actual != expected:
                raise ValueError('Research input artifact hash mismatch')
            result[name + '/' + relative] = actual
    return result


def inspect_inputs(reference_archive, paper_archive, check_budget=lambda: None):
    """Recompute the archived validation decision, rather than trust a summary."""
    from experiments.exp_026_validation_iteration import _decisions

    input_hashes(reference_archive, paper_archive, check_budget)
    root = Path(reference_archive).resolve()
    manifest = read_json(root / 'manifest.json')
    if manifest.get('status') != 'COMPLETED':
        raise ValueError('A completed validation reference is required')
    for relative, expected in manifest['source_hashes'].items():
        check_budget()
        if sha(_path_inside(ROOT, relative).read_bytes()) != expected:
            raise ValueError('Archived validation source differs from current code')
    fields = _raw_fields((root / 'results.json').read_text(encoding='utf-8-sig'),
        {'decisions', 'validation_rows', 'probe_evaluated', 'final_test_evaluated'}, check_budget)
    if _decode(fields['probe_evaluated']) is not False or _decode(fields['final_test_evaluated']) is not False:
        raise ValueError('This registry requires validation-only evidence')
    decisions = _decode(fields['decisions'])
    recomputed = _decisions(_decode(fields['validation_rows']), complete=True)
    if recomputed != decisions or any(row['status'] != 'DECIDED' for row in decisions.values()):
        raise ValueError('Archived validation decision/denominator mismatch')
    rejected = ['running_mean'] if all(row['selected_method'] == 'none' for row in decisions.values()) else []
    return {'validation_status': 'VERIFIED', 'rejected_candidates': rejected,
            'means': {mode: row['mean_validation_tardiness'] for mode, row in decisions.items()},
            'probe_evaluated': False, 'final_test_evaluated': False}


def audit_paper(paper_archive):
    root = Path(paper_archive).resolve()
    manifest = read_json(root / 'manifest.json')
    summary = read_json(root / 'batch_summary.json')
    if (manifest.get('complete_source_bundle') is not False or summary.get('human_approval') is not False
            or summary.get('research_status') != 'not_achieved'):
        raise ValueError('Unsupported paper evidence approval/source status')
    claims = []
    for fact in summary['facts']:
        context = _path_inside(root, 'contexts/' + fact['id'] + '.txt').read_text(encoding='utf-8')
        review = fact['semantic_review']
        if sha(context.encode('utf-8')) != review['source_text_sha256']:
            raise ValueError('Paper excerpt identity mismatch')
        for claim in fact['claims']:
            if claim['status'] != 'located_unreviewed' or not claim['locations']:
                raise ValueError('Paper claim must retain unreviewed location evidence')
            for location in claim['locations']:
                if context[location['start']:location['end']] != location['quote']:
                    raise ValueError('Paper quote offset mismatch')
            claims.append({'claim': claim['claim'], 'field': claim['field'],
                           'status': 'located_unreviewed', 'semantic_verdict': review['verdict'],
                           'context_sha256': review['source_text_sha256'],
                           'full_pdf_reverified': False, 'human_approval': False})
    if len(claims) != summary['claims_located'] or len(claims) != summary['claims_total']:
        raise ValueError('Paper claim denominator mismatch')
    return {'kind': TASK_KINDS['audit_paper_evidence'], 'status': 'COMPLETED',
            'claims_located': len(claims), 'claims': claims, 'human_approval': False,
            'complete_source_bundle': False, 'full_pdf_reverified': False,
            'author_code_reexecuted': False, 'research_status': 'not_achieved',
            'decision': 'retain_excerpt_provenance_without_approving_transplant',
            'compatibility_constraints': ['preserve_mandatory_maintenance_and_full_window',
                'preserve_total_tardiness_and_original_reward',
                'do_not_transplant_family_speed_arrival_or_terminal_bonus'],
            'limitation': 'Checks archived excerpt bytes/offsets only; no new paper discovery, '
                          'full PDF verification, original-method reproduction or human approval.'}


def execute_task(task_id, reference_archive, paper_archive, *, expected_inputs=None, batch_dir=None):
    if task_id not in TASK_KINDS:
        raise ValueError('Task is not registered')
    before = input_hashes(reference_archive, paper_archive)
    if expected_inputs is not None and before != expected_inputs:
        raise ValueError('Worker input identity changed')
    if task_id == 'audit_paper_evidence':
        result = audit_paper(paper_archive)
    elif task_id == 'diagnose_identifier_permutations':
        from src.graduation.permutation_diagnostics import diagnose_permutations
        result = diagnose_permutations(reference_archive)
    else:
        if batch_dir is None:
            raise ValueError('Candidate task requires an owned controller batch')
        from src.ai_workflow.controlled_candidate import materialize_candidate, check_candidate, compare_candidate
        if task_id == 'materialize_shared_scorer':
            result = materialize_candidate(batch_dir)
        elif task_id == 'check_shared_scorer':
            result = check_candidate(batch_dir, reference_archive)
        else:
            result = compare_candidate(batch_dir, reference_archive)
    if input_hashes(reference_archive, paper_archive) != before:
        raise ValueError('Worker inputs changed during execution')
    return result


def validate_task_result(task_id, result, expected_inputs=None, batch_dir=None):
    if (type(result) is not dict or result.get('kind') != TASK_KINDS[task_id]
            or result.get('status') != 'COMPLETED' or result.get('research_status') != 'not_achieved'):
        raise ValueError('Invalid registered task result envelope')
    if task_id == 'audit_paper_evidence':
        claims = result.get('claims')
        if (any(result.get(key) is not False for key in ('human_approval', 'complete_source_bundle',
                'full_pdf_reverified', 'author_code_reexecuted')) or type(claims) is not list
                or not 1 <= len(claims) <= 16 or type(result.get('claims_located')) is not int
                or result['claims_located'] != len(claims) or any(
                    claim.get('human_approval') is not False or claim.get('full_pdf_reverified') is not False
                    or claim.get('status') != 'located_unreviewed' for claim in claims)):
            raise ValueError('Paper result cannot supply approval')
    elif task_id == 'diagnose_identifier_permutations':
        _validate_diagnostic(result)
        if expected_inputs is not None and any(result['hash_checks'][field] != expected_inputs[path]
                for field, path in (('manifest_sha256', 'validation/manifest.json'),
                                    ('results_sha256', 'validation/results.json'))):
            raise ValueError('Diagnostic reference identity mismatch')
    else:
        from src.ai_workflow.controlled_candidate import verify_candidate_result
        if batch_dir is None:
            raise ValueError('Candidate verification requires its batch')
        verify_candidate_result(task_id, result, batch_dir)
    encoded(result)


def _validate_diagnostic(result):
    """Reject empty denominators and self-contradictory completion envelopes."""
    if (any(result.get(key) is not False for key in
            ('probe_evaluated', 'final_test_evaluated', 'training_performed'))
            or type(result.get('cases')) is not list or len(result['cases']) != 64
            or result.get('tolerance') != 1e-10):
        raise ValueError('Invalid validation diagnostic scope/denominator')
    try:
        counters = result['denominators']
        expected = {'expected_original_cases': 16, 'original_cases': 16,
            'expected_permutation_cases': 64, 'permutation_cases': 64,
            'G1_accepted_greedy_plans': 64, 'G1_accepted_mapped_replay_plans': 64}
        if any(type(counters[key]) is not int or counters[key] != value for key, value in expected.items()):
            raise ValueError('Invalid validation plan denominator')
        keys, sensitive, count = [], 0, 0
        for case in result['cases']:
            keys.append((case['mode'], case['seed'], case['validation_index'], case['permutation']))
            if (case['greedy']['G1_accepted'] is not True or case['mapped_replay']['G1_accepted'] is not True
                    or type(case['states']) is not list or len(case['states']) != 6
                    or len(case['input']['tasks']) != 4 or case['input']['num_machines'] != 2):
                raise ValueError('Invalid validation checked plans/states')
            _validate_plan(case['greedy'], case['input'], case['mode'])
            _validate_plan(case['mapped_replay'], case['input'], case['mode'])
            for state in case['states']:
                error = state['max_probability_error']
                if (type(error) not in (int, float) or not math.isfinite(error) or not 0 <= error <= 1
                        or type(state['sensitive']) is not bool or state['sensitive'] != (error > 1e-10)
                        or state['uniform_max_error'] != 0
                        or (case['permutation'] == 'identity' and error > 1e-10)):
                    raise ValueError('Invalid validation distribution/control evidence')
                sensitive += state['sensitive']
                count += 1
        expected_keys = {(mode, seed, index, name) for mode in ('fixed', 'joint') for seed in (17, 29)
                         for index in range(4) for name in
                         ('identity', 'jobs_reverse', 'machines_reverse', 'both_reverse')}
        if (len(set(keys)) != 64 or set(keys) != expected_keys
                or count != 384 or counters['expected_state_comparisons'] != count or counters['state_comparisons'] != count
                or type(result['sensitive_states']) is not int or result['sensitive_states'] != sensitive
                or result['aggregate']['sensitive_states'] != sensitive
                or result['aggregate']['uniform_sensitive_states'] != 0):
            raise ValueError('Invalid validation state/aggregate denominator')
    except (KeyError, TypeError) as exc:
        raise ValueError('Incomplete validation diagnostic evidence') from exc


def _validate_plan(plan, raw, mode):
    """Recheck worker actions/complete schedules with the original environment/G1."""
    from dataclasses import asdict
    from src.graduation.data import ProductionTask, MaintenanceRequirement, ParallelMaintenanceInstance
    from src.graduation.rl_environment import ParallelMaintenanceEnv
    from src.graduation.feasibility import check_parallel_maintenance_feasibility

    data = ParallelMaintenanceInstance(tuple(ProductionTask(**v) for v in raw['tasks']), raw['num_machines'],
                                       tuple(MaintenanceRequirement(**v) for v in raw['maintenance']))
    if (len(plan['actions']) != 6 or len(plan['rewards']) != 6
            or sha(encoded(plan['payload'])) != plan['plan_sha256']):
        raise ValueError('Incomplete validation plan/action evidence')
    env = ParallelMaintenanceEnv(data, mode=mode)
    for action, reward in zip(plan['actions'], plan['rewards']):
        transition = env.step(action)
        if transition.reward != reward or transition.truncated:
            raise ValueError('Validation action reward replay mismatch')
    result = env.get_result()
    accepted, _ = check_parallel_maintenance_feasibility(result, data, mode=mode)
    payload = {'records': sorted([asdict(r) for r in result.records], key=lambda r: r['job_id']),
        'maintenance_records': sorted([asdict(r) for r in result.maintenance_records], key=lambda r: r['machine_id']),
        'makespan': result.makespan, 'total_tardiness': result.total_tardiness}
    if not accepted or payload != plan['payload']:
        raise ValueError('Validation complete plan replay/G1 mismatch')


def choose_next(observation, completed, *, track, profile='audit_v1'):
    if track == 'innovation':
        return {'stop_reason': 'no_registered_innovation_executor', 'next_task': {
            'id': 'define_innovation_transport_milestone', 'executable': False,
            'reason': 'Production/logistics requirements remain separate; this registry has no AGV executor.'}}
    if not observation['rejected_candidates']:
        return {'stop_reason': 'unsupported_reference_decision', 'next_task': None}
    if 'audit_paper_evidence' not in completed:
        return {'task_id': 'audit_paper_evidence',
                'reason': 'Check provenance and compatibility before reusing a paper design.'}
    if 'diagnose_identifier_permutations' not in completed:
        return {'task_id': 'diagnose_identifier_permutations',
                'reason': 'running_mean was rejected; diagnose representation sensitivity without retraining.'}
    sensitive = completed['diagnose_identifier_permutations']['sensitive_states']
    if profile == 'shared_scorer_v1' and sensitive:
        for task_id, reason in (
            ('materialize_shared_scorer', 'Materialize only the registered shared scoring template into this batch.'),
            ('check_shared_scorer', 'Verify copied candidate gradients, masks and same-state distribution symmetry.'),
            ('compare_shared_scorer', 'Train the checked candidate and compare all frozen validation cases.')):
            if task_id not in completed:
                return {'task_id': task_id, 'reason': reason}
        decisions = completed['compare_shared_scorer']['decisions']
        selected = {mode: decision['selected_method'] for mode, decision in decisions.items()}
        return {'stop_reason': 'candidate_round_complete', 'next_task': {
            'id': 'diagnose_rejected_candidate' if all(v == 'none' for v in selected.values())
                  else 'review_retained_validation_candidate',
            'executable': False, 'selected_methods': selected,
            'reason': 'Bounded template round ended; another hypothesis/executor must be registered.',
            'production_default_changed': False}}
    return {'stop_reason': 'implementation_required', 'next_task': {
        'id': 'design_shared_scorer_candidate' if sensitive else 'design_next_validation_diagnostic',
        'executable': False, 'sensitive_states': sensitive,
        'reason': 'Registry exhausted. A bounded candidate implementation adapter is still required.',
        'constraints': ['original_G1_and_reward_unchanged', 'validation_only_selection',
                        'same_budget_all_seeds', 'no_guaranteed_improvement']}}
