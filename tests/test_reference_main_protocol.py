"""Formal G3A scope inputs only: no solver or approval is exercised here."""

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict
import hashlib
from itertools import product
import json
import platform
import re

from src.graduation.data import MaintenanceRequirement, ParallelMaintenanceInstance, ProductionTask


def _typed(raw):
    return ParallelMaintenanceInstance(
        tuple(ProductionTask(**task) for task in raw['tasks']), raw['num_machines'],
        tuple(MaintenanceRequirement(**item) for item in raw['maintenance']))


def _sha(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                     separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def _label(case):
    factors = case['factors']
    return tuple(factors[key] for key in (
        'num_tasks', 'num_machines', 'alpha_percent', 'beta_percent',
        'tau_percent', 'instance_seed', 'fixed_policy'))


def test_main_scope_is_unreviewed_nonexecuting_and_returns_fresh_configuration():
    from src.graduation.reference_main_protocol import main_protocol

    protocol = main_protocol()
    assert protocol['schema_version'] == 1
    assert protocol['protocol_id'] == 'graduation-g3a-main-scope-v1'
    assert protocol['scope'] == 'main_scope_preparation'
    assert protocol['approval_status'] == 'unreviewed'
    assert protocol['execution_supported'] is False
    assert protocol['formal_approval'] is False
    assert protocol['research_status'] == 'not_achieved'
    assert protocol['main_grid_execution_authorized'] is False
    assert protocol['rl_training_authorized'] is False
    assert protocol['required_review_gates'] == ['scope', 'evidence', 'conclusion']
    assert protocol['generator'] == {
        'id': 'g3a-integer-generator-v1',
        'rng': 'python_random_Random_randint',
        'python_version': platform.python_version(),
        'seed_key_template': 'graduation-g3a-v1|n={n}|seed={instance_seed}|field={field}',
        'seed_derivation': 'sha256_utf8_first_8_bytes_big_endian_unsigned',
        'processing_time_range': [1, 20],
        'due_quantile_percent_range': [50, 150],
        'maintenance_start_quantile_percent_range': [0, 25],
        'maintenance_start_draw_count': 4,
        'base_load': 'W=ceil(sum(p)/m)',
        'maintenance_duration': 'q_i=max(1,ceil(alpha_percent*W/100))',
        'maintenance_slack': 's_i=ceil(beta_percent*W/100)',
        'window_start': 'L_i=floor(start_quantile_i*W/100)',
        'window_end': 'U_i=L_i+q_i+s_i',
        'due_date': 'd_j=ceil(tau_percent*W*due_quantile_j/10000)',
        'fixed_start': {
            'window_midpoint': 'f_i=L_i+floor(s_i/2)',
            'window_earliest': 'f_i=L_i',
            'window_latest': 'f_i=L_i+s_i',
        },
    }
    original = deepcopy(protocol)
    protocol['primary']['instance_seeds'].clear()
    protocol['generator']['processing_time_range'][0] = 99
    protocol['generator']['fixed_start'].clear()
    protocol['required_review_gates'].clear()
    protocol['main_budget']['solver_calls'] = 0
    assert main_protocol() == original


def test_declared_primary_sensitivity_and_budget_preserve_all_480_planned_requests():
    from src.graduation.reference_main_protocol import build_main_cases, main_protocol

    protocol = main_protocol()
    assert protocol['primary'] == {
        'num_tasks': [8, 24], 'num_machines': [2, 4],
        'alpha_percent': [10, 30], 'beta_percent': [25, 75], 'tau_percent': [75, 125],
        'instance_seeds': [101, 202, 303, 404, 505],
        'fixed_policies': ['window_midpoint'], 'modes': ['fixed', 'joint'],
        'condition_cells': 32, 'paired_requests': 160, 'solver_calls': 320,
    }
    assert protocol['sensitivity'] == {
        'subset': {'num_tasks': [8], 'num_machines': [2]},
        'other_factors': 'inherit_primary_alpha_beta_tau_and_seeds',
        'additional_fixed_policies': ['window_earliest', 'window_latest'],
        'modes': ['fixed', 'joint'], 'base_cases': 40,
        'paired_requests': 80, 'solver_calls': 160,
    }
    assert protocol['solver'] == {
        'time_limit': 1.0, 'num_workers': 1, 'seed': 42, 'timing_repetitions': 1,
    }
    assert protocol['main_budget'] == {
        'paired_requests': 240, 'solver_calls': 480, 'solver_seconds_ceiling_sum': 480,
        'max_active_seconds': 600, 'provider_calls': 0, 'output_tokens': 0,
        'retry_failed_runs': False,
        'timeout_status': 'BUDGET_EXHAUSTED_with_unfinished_rows_NOT_RUN',
    }
    cases = build_main_cases()
    assert Counter(case['group'] for case in cases) == {'primary': 160, 'sensitivity': 80}
    assert len(cases) == protocol['main_budget']['paired_requests']
    planned = [(case['case_id'], mode) for case in cases for mode in ('fixed', 'joint')]
    assert len(planned) == len(set(planned)) == protocol['main_budget']['solver_calls']


def test_seed101_matches_independently_derived_sha8_stream_and_physical_fixture():
    from src.graduation.reference_main_protocol import build_main_cases

    # Independently derived with hashlib/random before production implementation:
    # processing=14526847696379388700, due=11612616183611720726,
    # maintenance_start=5743356841203291116 (SHA256 first 8 bytes, big-endian).
    case = build_main_cases()[0]
    assert case['factors'] == {
        'num_tasks': 8, 'num_machines': 2, 'alpha_percent': 10, 'beta_percent': 25,
        'tau_percent': 75, 'instance_seed': 101, 'fixed_policy': 'window_midpoint',
        'base_load': 46,
        'p': [18, 18, 1, 10, 10, 20, 9, 6],
        'u': [51, 80, 103, 63, 94, 137, 67, 60],
        'v': [2, 24, 5, 3],
    }
    assert case['data'] == asdict(ParallelMaintenanceInstance(
        (ProductionTask(0, 18, 18), ProductionTask(1, 18, 28),
         ProductionTask(2, 1, 36), ProductionTask(3, 10, 22),
         ProductionTask(4, 10, 33), ProductionTask(5, 20, 48),
         ProductionTask(6, 9, 24), ProductionTask(7, 6, 21)), 2,
        (MaintenanceRequirement(0, 5, 0, 17, 6),
         MaintenanceRequirement(1, 5, 11, 28, 17))))


def test_primary_then_parent_ordered_sensitivity_keeps_safe_unique_labels():
    from src.graduation.reference_main_protocol import build_main_cases

    cases = build_main_cases()
    primary_labels = [(*values, 'window_midpoint') for values in product(
        (8, 24), (2, 4), (10, 30), (25, 75), (75, 125), (101, 202, 303, 404, 505))]
    sensitivity_labels = [(*label[:-1], policy) for label in primary_labels
                          if label[:2] == (8, 2)
                          for policy in ('window_earliest', 'window_latest')]
    assert [_label(case) for case in cases] == primary_labels + sensitivity_labels
    assert cases[0]['case_id'] == 'g3a-main-n8-m2-a10-b25-t75-s101-midpoint'
    assert cases[159]['case_id'] == 'g3a-main-n24-m4-a30-b75-t125-s505-midpoint'
    assert cases[160]['case_id'] == 'g3a-main-n8-m2-a10-b25-t75-s101-earliest'
    assert cases[161]['case_id'] == 'g3a-main-n8-m2-a10-b25-t75-s101-latest'
    assert cases[-1]['case_id'] == 'g3a-main-n8-m2-a30-b75-t125-s505-latest'
    assert len({case['case_id'] for case in cases}) == 240
    assert all(re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', case['case_id']) for case in cases)
    assert build_main_cases() == cases


def test_ten_complete_random_workloads_are_shared_across_all_factor_variants():
    from src.graduation.reference_main_protocol import build_main_cases

    groups = defaultdict(list)
    for case in build_main_cases():
        factors = case['factors']
        groups[factors['num_tasks'], factors['instance_seed']].append(case)
    assert set(groups) == set(product((8, 24), (101, 202, 303, 404, 505)))
    assert sorted(Counter(case['workload_hash'] for cases in groups.values()
                          for case in cases).values()) == [16] * 5 + [32] * 5
    for (n, _), cases in groups.items():
        first = cases[0]['factors']
        assert len(first['p']) == len(first['u']) == n
        assert len(first['v']) == 4
        assert all(1 <= value <= 20 for value in first['p'])
        assert all(50 <= value <= 150 for value in first['u'])
        assert all(0 <= value <= 25 for value in first['v'])
        assert {case['factors']['num_machines'] for case in cases} == {2, 4}
        assert len({case['workload_hash'] for case in cases}) == 1
        for case in cases:
            assert all(case['factors'][field] == first[field] for field in ('p', 'u', 'v'))


def test_every_generated_input_is_typed_valid_and_uses_exact_integer_formulas():
    from src.graduation.reference_main_protocol import build_main_cases

    for case in build_main_cases():
        data, factors = _typed(case['data']), case['factors']
        n, m = factors['num_tasks'], factors['num_machines']
        assert len(data.tasks) == n and data.num_machines == m
        assert [task.job_id for task in data.tasks] == list(range(n))
        assert [item.machine_id for item in data.maintenance] == list(range(m))
        w = -(-sum(factors['p']) // m)
        q = max(1, -(-factors['alpha_percent'] * w // 100))
        slack = -(-factors['beta_percent'] * w // 100)
        assert factors['base_load'] == w
        for task, p, u in zip(data.tasks, factors['p'], factors['u']):
            assert task.processing_time == p
            assert task.due_date == -(-factors['tau_percent'] * w * u // 10000)
        for item, v in zip(data.maintenance, factors['v'][:m]):
            assert item.duration == q
            assert item.window_start == v * w // 100
            assert item.window_end == item.window_start + q + slack
            offset = {'window_midpoint': slack // 2,
                      'window_earliest': 0, 'window_latest': slack}[factors['fixed_policy']]
            assert item.fixed_start == item.window_start + offset
            assert item.window_start <= item.fixed_start
            assert item.fixed_start + item.duration <= item.window_end


def test_all_40_sensitivity_parents_keep_identical_workload_and_core_for_three_policies():
    from src.graduation.reference_main_protocol import build_main_cases

    families = defaultdict(list)
    for case in build_main_cases():
        if _label(case)[:2] == (8, 2):
            families[_label(case)[:-1]].append(case)
    assert len(families) == 40
    for family in families.values():
        assert [case['factors']['fixed_policy'] for case in family] == [
            'window_midpoint', 'window_earliest', 'window_latest']
        assert [case['group'] for case in family] == ['primary', 'sensitivity', 'sensitivity']
        assert len({case['workload_hash'] for case in family}) == 1
        assert len({case['core_model_hash'] for case in family}) == 1
        assert len({case['request_hash'] for case in family}) == 3
        assert all(case['data']['tasks'] == family[0]['data']['tasks'] for case in family)


def test_hashes_bind_complete_generator_workload_physical_core_and_solver_request():
    from src.graduation.reference_main_protocol import build_main_cases, main_protocol

    protocol = main_protocol()
    for case in build_main_cases():
        factors = case['factors']
        workload = {
            'generator': protocol['generator'], 'n': factors['num_tasks'],
            'seed': factors['instance_seed'], 'p': factors['p'],
            'u': factors['u'], 'v': factors['v'],
        }
        assert case['workload_hash'] == _sha(workload)
        changed = deepcopy(workload)
        changed['v'][-1] += 1
        assert _sha(changed) != case['workload_hash']
        changed = deepcopy(workload)
        changed['generator']['python_version'] = 'another-runtime'
        assert _sha(changed) != case['workload_hash']
        core = deepcopy(case['data'])
        core['maintenance'] = [{key: value for key, value in item.items() if key != 'fixed_start'}
                               for item in core['maintenance']]
        assert case['core_model_hash'] == _sha(core)
        request = {'data': case['data'], 'factors': factors, 'solver': protocol['solver']}
        assert case['request_hash'] == _sha(request)
        for field in ('solver', 'data', 'factors'):
            changed = deepcopy(request)
            if field == 'solver':
                changed[field]['seed'] += 1
            elif field == 'data':
                changed[field]['maintenance'][0]['fixed_start'] += 1
            else:
                changed[field]['alpha_percent'] += 1
            assert _sha(changed) != case['request_hash']


def test_returned_case_values_do_not_mutate_other_labels_or_future_calls():
    from src.graduation.reference_main_protocol import build_main_cases

    cases = build_main_cases()
    original = deepcopy(cases)
    cases[0]['factors']['p'][0] = 1000
    cases[0]['factors']['v'][-1] = 1000
    cases[0]['data']['tasks'][0]['due_date'] = 1000
    cases[0]['data']['maintenance'][0]['fixed_start'] = 1000
    assert cases[1:] == original[1:]
    assert build_main_cases() == original


def test_quantized_physical_aliases_keep_every_label_and_request(monkeypatch):
    from src.graduation import reference_protocol
    from src.graduation.reference_main_protocol import build_main_cases

    class LowestDraws:
        def __init__(self, seed):
            pass

        def randint(self, lower, upper):
            return lower

    # Controlled valid streams make n8/m4 alpha10 and alpha30 both round to q=1.
    # The public builder must retain both labels, rather than deduplicating inputs.
    monkeypatch.setattr(reference_protocol.random, 'Random', LowestDraws)
    cases = build_main_cases()
    assert len(cases) == len({case['case_id'] for case in cases}) == 240
    assert len({case['request_hash'] for case in cases}) == 240
    low, high = [next(case for case in cases if _label(case) ==
                     (8, 4, alpha, 25, 75, 101, 'window_midpoint')) for alpha in (10, 30)]
    assert low['data'] == high['data']
    assert low['core_model_hash'] == high['core_model_hash']
    assert low['request_hash'] != high['request_hash']
    assert low['case_id'] != high['case_id']
