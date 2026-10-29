"""Deterministic G3A pilot inputs for development validation only.

This module neither solves cases nor authorizes the draft's formal/main grid.
It preserves every factor label, including labels with identical physical data.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
from itertools import product
import json
import platform
import random

from src.graduation.data import MaintenanceRequirement, ParallelMaintenanceInstance, ProductionTask


def encoded(value) -> bytes:
    """Return sorted, compact UTF-8 JSON; nonfinite values are not admissible."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def digest(value) -> str:
    """Hash the canonical JSON representation rather than Python object order."""
    return hashlib.sha256(encoded(value)).hexdigest()


def pilot_protocol() -> dict:
    """Return a fresh versioned protocol for the 12-pair development pilot."""
    return {
        'schema_version': 1,
        'protocol_id': 'graduation-g3a-pilot-development-v1',
        'scope': 'pilot_development_validation',
        'purpose': 'paired_reference_model_comparison_development_validation',
        'formal_approval': False,
        'research_status': 'not_achieved',
        'main_grid_execution_authorized': False,
        'rl_training_authorized': False,
        'model': 'graduation_g2_identical_singleop_v1',
        'generator': {
            'id': 'g3a-integer-generator-v1',
            'rng': 'python_random_Random_randint',
            'python_version': platform.python_version(),
            'seed_key_template': 'graduation-g3a-v1|n={n}|seed={instance_seed}|field={field}',
            'seed_derivation': 'sha256_utf8_first_8_bytes_big_endian_unsigned',
            'processing_time_range': [1, 4],
            'due_quantile_percent_range': [50, 150],
            'maintenance_start_quantile_percent_range': [0, 25],
            'maintenance_start_draw_count': 4,
            'base_load': 'W=ceil(sum(p)/m)',
            'maintenance_duration': 'q_i=max(1,ceil(alpha_percent*W/100))',
            'maintenance_slack': 's_i=ceil(beta_percent*W/100)',
            'window_start': 'L_i=floor(start_quantile_i*W/100)',
            'window_end': 'U_i=L_i+q_i+s_i',
            'due_date': 'd_j=ceil(tau_percent*W*due_quantile_j/10000)',
            'fixed_start': 'f_i=L_i+floor(s_i/2)',
        },
        'pilot': {
            'num_tasks': [3], 'num_machines': [2], 'processing_time_range': [1, 4],
            'alpha_percent': [10, 30], 'beta_percent': [25, 75], 'tau_percent': [100],
            'instance_seeds': [11, 22, 33], 'fixed_policies': ['window_midpoint'],
            'modes': ['fixed', 'joint'], 'paired_requests': 12, 'solver_calls': 24,
            'oracle_max_states': 200000, 'oracle_per_case_state_upper_bound': 9504,
            'max_active_seconds': 90, 'provider_calls': 0, 'output_tokens': 0,
        },
        'solver': {'time_limit': 1.0, 'num_workers': 1, 'seed': 42, 'timing_repetitions': 1},
    }


def _base_workload(n: int, seed: int, generator: dict) -> dict:
    values = {}
    for field, range_key, count in (
        ('processing', 'processing_time_range', n),
        ('due', 'due_quantile_percent_range', n),
        ('maintenance_start', 'maintenance_start_quantile_percent_range', 4),
    ):
        key = generator['seed_key_template'].format(n=n, instance_seed=seed, field=field)
        rng_seed = int.from_bytes(hashlib.sha256(key.encode('utf-8')).digest()[:8], 'big')
        rng = random.Random(rng_seed)
        low, high = generator[range_key]
        values[field] = [rng.randint(low, high) for _ in range(count)]
    return {'generator': generator, 'n': n, 'seed': seed, 'p': values['processing'],
            'u': values['due'], 'v': values['maintenance_start']}


def build_pilot_cases() -> list[dict]:
    """Build all 12 paired inputs in alpha/beta/seed declaration order.

    workload_hash binds n/seed/p/u/all four v plus generator identity/config.
    core_model_hash binds typed physical data after removing fixed_start only.
    request_hash binds complete data, factors and solver settings. Neither core
    collisions nor shared workloads remove labels or trigger additional draws.
    """
    protocol = pilot_protocol()
    pilot, generator = protocol['pilot'], protocol['generator']
    n, m, tau = pilot['num_tasks'][0], pilot['num_machines'][0], pilot['tau_percent'][0]
    workloads = {seed: _base_workload(n, seed, generator) for seed in pilot['instance_seeds']}
    cases = []
    for alpha, beta, seed in product(pilot['alpha_percent'], pilot['beta_percent'], pilot['instance_seeds']):
        workload = workloads[seed]
        p, u, v = workload['p'], workload['u'], workload['v']
        w = (sum(p) + m - 1) // m
        q = max(1, (alpha * w + 99) // 100)
        slack = (beta * w + 99) // 100
        tasks = tuple(ProductionTask(j, p[j], (tau * w * u[j] + 9999) // 10000)
                      for j in range(n))
        maintenance = []
        for machine in range(m):
            start = v[machine] * w // 100
            maintenance.append(MaintenanceRequirement(machine, q, start, start + q + slack,
                                                       start + slack // 2))
        data = asdict(ParallelMaintenanceInstance(tasks, m, tuple(maintenance)))
        factors = {
            'num_tasks': n, 'num_machines': m, 'alpha_percent': alpha, 'beta_percent': beta,
            'tau_percent': tau, 'instance_seed': seed, 'fixed_policy': 'window_midpoint',
            'base_load': w, 'p': list(p), 'u': list(u), 'v': list(v),
        }
        core = {
            'tasks': data['tasks'], 'num_machines': m,
            'maintenance': [{key: value for key, value in item.items() if key != 'fixed_start'}
                            for item in data['maintenance']],
        }
        cases.append({
            'case_id': f'g3a-pilot-n{n}-m{m}-a{alpha}-b{beta}-t{tau}-s{seed}-midpoint',
            'data': data,
            'factors': factors,
            'workload_hash': digest(workload),
            'core_model_hash': digest(core),
            'request_hash': digest({'data': data, 'factors': factors, 'solver': protocol['solver']}),
        })
    return cases
