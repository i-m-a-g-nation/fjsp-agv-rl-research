"""Verified rejection diagnostics and one registered, non-causal hypothesis."""
import math
from pathlib import Path

import numpy as np

from src.ai_workflow.research_tasks import encoded, read_json, sha
from src.graduation.permutation_diagnostics import _rollout
from src.graduation.state_encoding import encode_construction_observation as encode
from src.graduation.validation_diagnostics import (
    _decode, _instances, _path_inside, _raw_fields, _require, _state_hash,
)

PROFILE = 'shared_scorer_feedback_v1'
DIAGNOSIS = 'diagnose_rejected_candidate'
TRIAL_TASK = 'compare_larger_step'
TRIAL = 'larger_step_v1'
KIND = 'rejected_candidate_diagnosis'
RUNS = {(mode, seed) for mode in ('fixed', 'joint') for seed in (17, 29)}


def step_hypothesis(rows, decisions):
    """This predicate proposes a trial; it never asserts a cause or improvement."""
    stalled = sum(r['changed_updates'] > 0 and r['parameter_l2_change'] > 0
        and r['max_probability_change'] > 0 and r['same_state_argmax_changes'] == 0
        and r['greedy_plans_changed'] == 0 and r['flat_validation'] is True for r in rows)
    rejected = all(decisions[m]['selected_method'] == 'none' for m in ('fixed', 'joint'))
    eligible = len(rows) == 4 and rejected and stalled >= 3 and all(r['clipped_updates'] == 0 for r in rows)
    return {'id': TRIAL, 'eligible': eligible, 'stalled_runs': stalled,
        'causal_claim': False, 'learning_rate': .1, 'previous_learning_rate': .01,
        'only_changed_factor': 'learning_rate', 'max_additional_training_episodes': 256,
        'max_additional_training_steps': 1536, 'max_trials': 1,
        'reason': 'test_step_size_without_claiming_insufficient_step_is_the_cause' if eligible
                  else 'no_registered_trial_matches_verified_diagnosis',
        'constraints': ['same_initial_parameters', 'same_train8_validation4', 'same_seeds17_29',
                        'same_64episodes_per_run', 'original_reward_and_G1', 'no_held_out_selection']}


def _load_actor(batch, checkpoint, actor_class):
    _require(checkpoint['path'].startswith('candidate_run/checkpoints/'), 'Unexpected diagnostic checkpoint path')
    path = _path_inside(batch, checkpoint['path'])
    _require(sha(path.read_bytes()) == checkpoint['sha256']
             and read_json(path.with_suffix('.json')) == checkpoint, 'Diagnostic checkpoint identity mismatch')
    with np.load(path, allow_pickle=False) as saved:
        state = {key: saved[key] for key in saved.files}
    _require(_state_hash(state) == checkpoint['state_sha256'], 'Diagnostic checkpoint parameters differ')
    return actor_class.from_state(state), state


def analyse_comparison(batch, reference, comparison, actor_class, *, check_budget=lambda: None):
    """Read only training/validation fields; verify all interval plans and ranks."""
    check_budget()
    batch, reference = Path(batch).resolve(), Path(reference).resolve()
    from src.ai_workflow.candidate_replay import verify_training_replay
    verify_training_replay(batch, reference, comparison, actor_class, check_budget=check_budget)
    _require(comparison['config']['learning_rate'] == .01, 'Diagnosis requires the initial step-size trial')
    runs = comparison['training_runs']
    _require(len(runs) == 4 and {(r['mode'], r['seed']) for r in runs} == RUNS, 'Incomplete diagnostic runs')
    raw = (reference / 'results.json').read_text(encoding='utf-8-sig')
    validation = _raw_fields(_raw_fields(raw, {'splits'}, check_budget)['splits'], {'validation'}, check_budget)
    data, identities = _instances(_decode(validation['validation']), 4, check_budget)
    _require(len(data) == 4, 'Incomplete diagnostic validation split')
    rows, total_plans, total_states = [], 0, 0
    for run in sorted(runs, key=lambda r: (r['mode'], r['seed'])):
        check_budget()
        _require(run['episodes_completed'] == 64 and run['training_steps'] == 384
            and len(run['logs']) == 64 and [r['episode'] for r in run['logs']] == list(range(1, 65)),
            'Incomplete diagnostic training log')
        log = _path_inside(batch, run['progress_log'])
        events = [_decode(line) for line in log.read_text(encoding='utf-8').splitlines()]
        _require(sha(log.read_bytes()) == run['progress_log_sha256'] and len(events) == 69
            and [e['log'] for e in events if e['kind'] == 'episode'] == run['logs'],
            'Diagnostic durable training log differs')
        history = run['validation_history']
        intervals = run['interval_checkpoints']
        _require([h['episode'] for h in history] == [0, 16, 32, 48, 64]
            and [h['episode'] for h in intervals] == [0, 16, 32, 48, 64], 'Incomplete diagnostic intervals')
        interval_events = [e for e in events if e['kind'] == 'validation']
        _require(len(interval_events) == 5, 'Incomplete diagnostic durable intervals')
        actors, parameters = {}, {}
        for name in ('initial', 'final', 'selected'):
            actors[name], parameters[name] = _load_actor(batch, run['checkpoints'][name], actor_class)
        cache, initial_states = {}, []
        means = []
        for h, checkpoint, event in zip(history, intervals, interval_events):
            check_budget()
            _require(encoded({k: event[k] for k in h}) == encoded(h)
                and event['checkpoints'] == checkpoint, 'Diagnostic interval log differs')
            actor, _ = _load_actor(batch, checkpoint['current'], actor_class)
            plans = []
            _require(len(h['validation_rows']) == 4, 'Incomplete diagnostic interval plans')
            for index, instance in enumerate(data):
                plan, states = _rollout(actor, instance, run['mode'], check_budget)
                saved = h['validation_rows'][index]
                _require(saved['validation_index'] == index and saved['instance_identity'] == identities[index]
                    and plan['actions'] == saved['actions'] and plan['rewards'] == saved['rewards']
                    and plan['payload']['total_tardiness'] == saved['total_tardiness'],
                    'Diagnostic checkpoint does not reproduce interval plan')
                plans.append(plan)
                if h['episode'] == 0:
                    initial_states.append(states)
                total_plans += 1
            mean = math.fsum(p['payload']['total_tardiness'] for p in plans)/4
            _require(mean == h['validation_mean_tardiness'], 'Diagnostic interval mean mismatch')
            cache[h['episode']] = plans
            means.append(mean)
        best = history[means.index(min(means))]['episode']
        _require(run['selected_episode'] == best and all(
            run['checkpoints'][name]['state_sha256'] == next(
                c['current']['state_sha256'] for c in intervals if c['episode'] == ep)
            for name, ep in (('initial', 0), ('final', 64), ('selected', best))),
            'Diagnostic selected/initial/final checkpoint binding differs')
        cases = []
        for index, states in enumerate(initial_states):
            selected = cache[best][index]
            saved = [r for r in comparison['candidate_rows'] if
                     (r['mode'], r['seed'], r['validation_index']) == (run['mode'], run['seed'], index)]
            _require(len(saved) == 1 and selected['payload'] == saved[0]['payload']
                and selected['actions'] == saved[0]['actions'], 'Diagnostic selected plan differs')
            state_rows = []
            for step, (observation, before, _) in enumerate(states):
                check_budget()
                after = actors['final'].probabilities(encode(observation))
                state_rows.append({'step': step, 'legal_count': sum(observation.action_mask),
                    'initial_probabilities': list(before), 'final_probabilities': list(after),
                    'max_probability_change': max(abs(p-q) for p, q in zip(before, after)),
                    'initial_argmax': int(np.argmax(before)), 'final_argmax': int(np.argmax(after)),
                    'argmax_changed': bool(np.argmax(before) != np.argmax(after))})
            _require(len(state_rows) == 6, 'Incomplete diagnostic state comparisons')
            total_states += len(state_rows)
            cases.append({'validation_index': index, 'base_identity': identities[index],
                'initial': cache[0][index], 'final': cache[64][index], 'selected': selected,
                'states': state_rows, 'greedy_plan_changed': cache[0][index]['payload'] != cache[64][index]['payload']})
        updates = [l['update'] for l in run['logs']]
        _require(all(type(u['changed']) is bool and type(u['gradient_norm']) in (int, float)
            and math.isfinite(u['gradient_norm']) and u['gradient_norm'] >= 0
            and u['applied_gradient_norm'] == min(u['gradient_norm'], 1.) for u in updates),
            'Invalid diagnostic update evidence')
        rows.append({'mode': run['mode'], 'seed': run['seed'], 'selected_episode': best,
            'changed_updates': sum(u['changed'] for u in updates),
            'clipped_updates': sum(u['gradient_norm'] > 1. for u in updates),
            'parameter_l2_change': math.sqrt(math.fsum(float(np.sum((parameters['final'][k]-parameters['initial'][k])**2))
                                                       for k in parameters['initial'])),
            'max_probability_change': max(s['max_probability_change'] for c in cases for s in c['states']),
            'same_state_argmax_changes': sum(s['argmax_changed'] for c in cases for s in c['states']),
            'greedy_plans_changed': sum(c['greedy_plan_changed'] for c in cases),
            'flat_validation': len(set(means)) == 1, 'interval_means': means,
            'interval_plan_hashes': {str(ep): [p['plan_sha256'] for p in plans] for ep, plans in cache.items()},
            'cases': cases})
    counts = {'training_runs': 4, 'training_updates': 256, 'checked_plans': total_plans,
              'same_state_comparisons': total_states, 'validation_checkpoints': 20}
    _require(total_plans == 80 and total_states == 96, 'Incomplete diagnostic denominators')
    return {'kind': KIND, 'status': 'COMPLETED', 'research_status': 'not_achieved',
        'training_performed': False, 'probe_evaluated': False, 'final_test_evaluated': False,
        'production_default_changed': False, 'model_api_calls': 0, 'network_calls': 0,
        'counts': counts, 'runs': rows, 'hypothesis': step_hypothesis(rows, comparison['decisions'])}


def completed_receipt(batch, task_id, check_budget=lambda: None):
    """Load exactly one completed, byte-bound receipt; never synthesize approval."""
    batch = Path(batch).resolve()
    check_budget()
    entries = [(i, t) for i, t in enumerate(read_json(batch / 'state.json')['tasks'], 1) if t['id'] == task_id]
    _require(len(entries) == 1 and entries[0][1]['status'] == 'COMPLETED', 'Missing completed feedback receipt')
    index, task = entries[0]
    path = batch / f'task_{index:02d}.json'
    _require(sha(path.read_bytes()) == task['result_sha256'], 'Feedback receipt identity changed')
    result = read_json(path)
    if task_id == DIAGNOSIS:
        verify_diagnosis(result, batch, check_budget=check_budget)
    else:
        from src.ai_workflow.controlled_candidate import verify_candidate_result
        verify_candidate_result(task_id, result, batch, check_budget=check_budget)
    return result


def diagnose_candidate(batch, *, persist=True, check_budget=lambda: None):
    from src.ai_workflow.controlled_candidate import _context, load_candidate, _deadline
    batch, _, _, _ = _context(batch)
    budget = _deadline(check_budget)
    spec = read_json(batch / 'spec.json')
    _require(spec['identity']['profile'] == PROFILE, 'Feedback requires its explicit profile')
    previous = completed_receipt(batch, 'compare_shared_scorer', budget)
    report = analyse_comparison(batch, spec['identity']['reference_archive'], previous,
                                load_candidate(batch), check_budget=budget)
    report['previous_result_sha256'] = sha((batch / 'candidate_run/results.json').read_bytes())
    report['hypothesis_sha256'] = sha(encoded(report['hypothesis']))
    if persist:
        folder = _path_inside(batch, 'candidate_diagnosis')
        folder.mkdir(exist_ok=False)
        (folder / 'report.json').write_bytes(encoded(report))
        (folder / 'hypothesis.json').write_bytes(encoded(report['hypothesis']))
    return {**report, 'artifacts': {name: sha(_path_inside(batch, name).read_bytes()) for name in
            ('candidate_diagnosis/report.json', 'candidate_diagnosis/hypothesis.json')}}


def verify_diagnosis(result, batch, *, check_budget=lambda: None):
    recomputed = diagnose_candidate(batch, persist=False, check_budget=check_budget)
    _require(encoded(result) == encoded(recomputed), 'Feedback diagnosis differs from verified replay')
    _require(read_json(Path(batch) / 'candidate_diagnosis/report.json') ==
             {k: v for k, v in result.items() if k != 'artifacts'}, 'Saved diagnosis report differs')
    _require(read_json(Path(batch) / 'candidate_diagnosis/hypothesis.json') == result['hypothesis'],
             'Saved feedback hypothesis differs')


def require_trial(batch, check_budget=lambda: None):
    report = completed_receipt(batch, DIAGNOSIS, check_budget)
    _require(report['hypothesis']['eligible'] is True, 'No registered trial matches diagnosis')
    return report


def comparison_feedback(batch, result, *, check_budget=lambda: None):
    """Recompute the single-factor relation; a field claiming equality is insufficient."""
    batch = Path(batch).resolve()
    diagnosis = require_trial(batch, check_budget)
    previous = completed_receipt(batch, 'compare_shared_scorer', check_budget)
    _require(result.get('trial') == TRIAL and result['config']['learning_rate'] == .1,
             'Unregistered feedback configuration')
    _require(encoded({k:v for k,v in previous['config'].items() if k != 'learning_rate'}) ==
             encoded({k:v for k,v in result['config'].items() if k != 'learning_rate'}),
             'Feedback changed more than learning rate')
    _require(read_json(batch/'candidate_run/inputs.json') == read_json(batch/'candidate_step_run/inputs.json'),
             'Feedback changed frozen inputs')
    _require(all(encoded(previous[k]) == encoded(result[k]) for k in ('control_rows', 'rule_rows', 'cp_rows')),
             'Feedback changed reference evidence')
    a = {(r['mode'], r['seed']): r for r in previous['training_runs']}
    b = {(r['mode'], r['seed']): r for r in result['training_runs']}
    _require(set(a) == set(b) == RUNS and len(result['training_runs']) == 4, 'Feedback training denominator differs')
    _require(all(a[k]['checkpoints']['initial']['state_sha256'] == b[k]['checkpoints']['initial']['state_sha256']
        and b[k]['episodes_completed'] == 64 and b[k]['training_steps'] == 384 for k in RUNS),
        'Feedback changed initialization or training budget')
    comparison = {}
    for mode in ('fixed', 'joint'):
        before = previous['decisions'][mode]['mean_validation_tardiness']['shared_scorer_v1']
        values = result['decisions'][mode]['mean_validation_tardiness']
        retained = values['shared_scorer_v1'] < min(before, values['none'])
        _require(result['decisions'][mode]['selected_method'] == ('shared_scorer_v1' if retained else 'none'),
                 'Feedback retention must beat both previous candidate and none')
        comparison[mode] = {'previous_candidate_mean': before, 'new_candidate_mean': values['shared_scorer_v1'],
            'none_mean': values['none'], 'change_from_previous': values['shared_scorer_v1']-before,
            'retained_development_candidate': retained}
    return {'only_changed_factor': 'learning_rate', 'same_initial_parameters': True,
        'previous_result_sha256': diagnosis['previous_result_sha256'],
        'diagnosis_report_sha256': sha((batch/'candidate_diagnosis/report.json').read_bytes()),
        'hypothesis_sha256': diagnosis['hypothesis_sha256'], 'total_training_steps': 3072,
        'comparisons': comparison, 'independent_generalization_claim': False}
