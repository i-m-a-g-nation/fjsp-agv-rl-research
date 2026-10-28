"""Reproducible development pilot inputs, independent of the solver backend."""

from collections import Counter
from copy import deepcopy
from dataclasses import asdict
import hashlib
from itertools import product
import json
from math import factorial, prod
import re

import pytest

from src.graduation.data import MaintenanceRequirement, ParallelMaintenanceInstance, ProductionTask


def _typed(raw):
    return ParallelMaintenanceInstance(
        tuple(ProductionTask(**task) for task in raw['tasks']), raw['num_machines'],
        tuple(MaintenanceRequirement(**item) for item in raw['maintenance']))


def _sha(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                     separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def test_encoding_is_order_independent_utf8_and_digest_binds_the_complete_value():
    from src.graduation.reference_protocol import digest, encoded
    value = {'z': [3, {'研究': True}], 'a': 2}
    expected = '{"a":2,"z":[3,{"研究":true}]}'.encode('utf-8')
    assert encoded(value) == expected
    assert encoded({'a': 2, 'z': [3, {'研究': True}]}) == expected
    assert digest(value) == hashlib.sha256(expected).hexdigest()
    assert digest({'a': 3, 'z': value['z']}) != digest(value)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf')])
def test_encoding_refuses_nonfinite_values_even_when_nested(value):
    from src.graduation.reference_protocol import digest, encoded
    with pytest.raises(ValueError):
        encoded({'nested': [value]})
    with pytest.raises(ValueError):
        digest({'nested': [value]})


def test_pilot_has_development_scope_bounded_settings_and_fresh_nested_values():
    from src.graduation.reference_protocol import pilot_protocol
    protocol = pilot_protocol()
    assert protocol['scope'] == 'pilot_development_validation'
    assert protocol['formal_approval'] is False
    assert protocol['research_status'] == 'not_achieved'
    assert protocol['main_grid_execution_authorized'] is False
    assert protocol['rl_training_authorized'] is False
    pilot = protocol['pilot']
    assert pilot == {
        'num_tasks': [3], 'num_machines': [2], 'processing_time_range': [1, 4],
        'alpha_percent': [10, 30], 'beta_percent': [25, 75], 'tau_percent': [100],
        'instance_seeds': [11, 22, 33], 'fixed_policies': ['window_midpoint'],
        'modes': ['fixed', 'joint'], 'paired_requests': 12, 'solver_calls': 24,
        'oracle_max_states': 200000, 'oracle_per_case_state_upper_bound': 9504,
        'max_active_seconds': 90, 'provider_calls': 0, 'output_tokens': 0,
    }
    assert protocol['solver'] == {
        'time_limit': 1.0, 'num_workers': 1, 'seed': 42, 'timing_repetitions': 1}
    original = deepcopy(protocol)
    protocol['pilot']['instance_seeds'].clear()
    protocol['generator']['processing_time_range'][0] = 99
    protocol['solver']['time_limit'] = 99
    assert pilot_protocol() == original


def test_seed11_matches_independently_derived_rng_and_integer_input_fixture():
    from src.graduation.reference_protocol import build_pilot_cases
    # Before implementing the generator, SHA256 first-8-byte big-endian stream
    # seeds were independently derived as processing=17811538752767706530,
    # due=9211009596260443212 and maintenance_start=10123677307659771540.
    case = build_pilot_cases()[0]
    assert case['factors']['instance_seed'] == 11
    assert case['factors']['p'] == [1, 3, 3]
    assert case['factors']['u'] == [81, 137, 96]
    assert case['factors']['v'] == [12, 10, 19, 4]
    assert case['factors']['base_load'] == 4
    assert case['data'] == asdict(ParallelMaintenanceInstance(
        (ProductionTask(0, 1, 4), ProductionTask(1, 3, 6), ProductionTask(2, 3, 4)), 2,
        (MaintenanceRequirement(0, 1, 0, 2, 0), MaintenanceRequirement(1, 1, 0, 2, 0))))


def test_declared_order_keeps_three_shared_workloads_and_all_twelve_case_labels():
    from src.graduation.reference_protocol import build_pilot_cases
    cases = build_pilot_cases()
    assert [(case['factors']['alpha_percent'], case['factors']['beta_percent'],
             case['factors']['instance_seed']) for case in cases] == list(product(
                 (10, 30), (25, 75), (11, 22, 33)))
    assert len({case['case_id'] for case in cases}) == 12
    assert all(re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', case['case_id']) for case in cases)
    assert sorted(Counter(case['workload_hash'] for case in cases).values()) == [4, 4, 4]
    expected = {
        11: ([1, 3, 3], [81, 137, 96], [12, 10, 19, 4]),
        22: ([4, 4, 3], [59, 88, 59], [2, 15, 25, 15]),
        33: ([3, 4, 2], [65, 63, 120], [16, 8, 1, 10]),
    }
    for case in cases:
        factors = case['factors']
        assert (factors['p'], factors['u'], factors['v']) == expected[factors['instance_seed']]
    assert build_pilot_cases() == cases
    cases[0]['factors']['p'][0] = 1000
    cases[0]['data']['tasks'][0]['due_date'] = 1000
    assert build_pilot_cases()[0]['factors']['p'] == [1, 3, 3]
    assert build_pilot_cases()[0]['data']['tasks'][0]['due_date'] == 4


def test_hash_layers_bind_their_declared_payload_and_ignore_fixed_start_only_in_core():
    from src.graduation.reference_protocol import build_pilot_cases, pilot_protocol
    protocol = pilot_protocol()
    for case in build_pilot_cases():
        factors = case['factors']
        workload = {'generator': protocol['generator'], 'n': 3,
                    'seed': factors['instance_seed'], 'p': factors['p'],
                    'u': factors['u'], 'v': factors['v']}
        assert case['workload_hash'] == _sha(workload)
        changed = deepcopy(workload)
        changed['v'][-1] += 1
        assert _sha(changed) != case['workload_hash']
        core = deepcopy(case['data'])
        core['maintenance'] = [{key: value for key, value in item.items() if key != 'fixed_start'}
                               for item in core['maintenance']]
        assert case['core_model_hash'] == _sha(core)
        request = {'data': case['data'], 'factors': factors, 'solver': protocol['solver']}
        assert case['request_hash'] == _sha(request)
        changed = deepcopy(request)
        changed['solver']['seed'] += 1
        assert _sha(changed) != case['request_hash']
        changed = deepcopy(request)
        changed['data']['maintenance'][0]['fixed_start'] += 1
        assert _sha(changed) != case['request_hash']


def test_all_cases_are_typed_valid_with_complete_windows_and_bounded_oracle_domain():
    from src.graduation.reference_protocol import build_pilot_cases
    # Sum over assignments and all six job orders of the product of cut counts:
    # 6 * (4 + 3*6 + 3*6 + 4) = 264 states per maintenance-start combination.
    per_combination = factorial(3) * sum(
        (assignment.count(0) + 1) * (assignment.count(1) + 1)
        for assignment in product(range(2), repeat=3))
    assert per_combination == 264
    for case in build_pilot_cases():
        data, factors = _typed(case['data']), case['factors']
        assert len(data.tasks) == 3 and data.num_machines == 2
        w = (sum(task.processing_time for task in data.tasks) + 1) // 2
        assert w <= 6
        q = max(1, (factors['alpha_percent'] * w + 99) // 100)
        slack = (factors['beta_percent'] * w + 99) // 100
        for task, u in zip(data.tasks, factors['u']):
            assert task.due_date == (100 * w * u + 9999) // 10000
        for item, v in zip(data.maintenance, factors['v']):
            assert item.duration == q
            assert item.window_start == v * w // 100
            assert item.window_end == item.window_start + q + slack
            assert item.fixed_start == item.window_start + slack // 2
            assert item.fixed_start + q <= item.window_end
        combinations = prod(item.window_end - item.duration - item.window_start + 1
                            for item in data.maintenance)
        assert combinations * per_combination <= 9504 < 200000


def test_quantization_aliases_are_retained_without_relabeling_as_independent_inputs(monkeypatch):
    from src.graduation import reference_protocol as module

    class LowestDraws:
        def __init__(self, seed):
            pass

        def randint(self, lower, upper):
            return lower

    # A controlled valid random stream makes both alpha values quantize to q=1.
    # Keep the real case assembler and hashing: collisions must remain visible.
    monkeypatch.setattr(module.random, 'Random', LowestDraws)
    cases = module.build_pilot_cases()
    assert len(cases) == len({case['case_id'] for case in cases}) == 12
    assert len({case['core_model_hash'] for case in cases}) == 2
    assert len({case['request_hash'] for case in cases}) == 12
    assert sorted(Counter(case['core_model_hash'] for case in cases).values()) == [6, 6]
