"""Deterministic formal G3A scope inputs, prepared for review only.

This module does not solve cases, create approvals, or authorize execution.
Every factor label is retained even when integer quantization creates aliases.
"""

from __future__ import annotations

from dataclasses import asdict
from itertools import product
import platform

from src.graduation.data import MaintenanceRequirement, ParallelMaintenanceInstance, ProductionTask
from src.graduation.reference_protocol import _base_workload, digest


def main_protocol() -> dict:
    """Return fresh, unreviewed scope settings for the 240-pair main proposal."""
    return {
        'schema_version': 1,
        'protocol_id': 'graduation-g3a-main-scope-v1',
        'scope': 'main_scope_preparation',
        'purpose': 'paired_reference_model_comparison_not_final_algorithm_evaluation',
        'approval_status': 'unreviewed',
        'execution_supported': False,
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
        },
        'primary': {
            'num_tasks': [8, 24], 'num_machines': [2, 4],
            'alpha_percent': [10, 30], 'beta_percent': [25, 75], 'tau_percent': [75, 125],
            'instance_seeds': [101, 202, 303, 404, 505],
            'fixed_policies': ['window_midpoint'], 'modes': ['fixed', 'joint'],
            'condition_cells': 32, 'paired_requests': 160, 'solver_calls': 320,
        },
        'sensitivity': {
            'subset': {'num_tasks': [8], 'num_machines': [2]},
            'other_factors': 'inherit_primary_alpha_beta_tau_and_seeds',
            'additional_fixed_policies': ['window_earliest', 'window_latest'],
            'modes': ['fixed', 'joint'], 'base_cases': 40,
            'paired_requests': 80, 'solver_calls': 160,
        },
        'solver': {'time_limit': 1.0, 'num_workers': 1, 'seed': 42, 'timing_repetitions': 1},
        'main_budget': {
            'paired_requests': 240, 'solver_calls': 480, 'solver_seconds_ceiling_sum': 480,
            'max_active_seconds': 600, 'provider_calls': 0, 'output_tokens': 0,
            'retry_failed_runs': False,
            'timeout_status': 'BUDGET_EXHAUSTED_with_unfinished_rows_NOT_RUN',
        },
        'required_review_gates': ['scope', 'evidence', 'conclusion'],
    }


def _build_case(n, m, alpha, beta, tau, seed, policy, group, workload, solver):
    p, u, v = workload['p'], workload['u'], workload['v']
    w = (sum(p) + m - 1) // m
    q = max(1, (alpha * w + 99) // 100)
    slack = (beta * w + 99) // 100
    offset = {'window_midpoint': slack // 2,
              'window_earliest': 0, 'window_latest': slack}[policy]
    tasks = tuple(ProductionTask(job, p[job], (tau * w * u[job] + 9999) // 10000)
                  for job in range(n))
    maintenance = []
    for machine in range(m):
        start = v[machine] * w // 100
        maintenance.append(MaintenanceRequirement(machine, q, start, start + q + slack,
                                                   start + offset))
    data = asdict(ParallelMaintenanceInstance(tasks, m, tuple(maintenance)))
    factors = {
        'num_tasks': n, 'num_machines': m, 'alpha_percent': alpha, 'beta_percent': beta,
        'tau_percent': tau, 'instance_seed': seed, 'fixed_policy': policy,
        'base_load': w, 'p': list(p), 'u': list(u), 'v': list(v),
    }
    core = {
        'tasks': data['tasks'], 'num_machines': m,
        'maintenance': [{key: value for key, value in item.items() if key != 'fixed_start'}
                        for item in data['maintenance']],
    }
    return {
        'case_id': f'g3a-main-n{n}-m{m}-a{alpha}-b{beta}-t{tau}-s{seed}-{policy.removeprefix("window_")}',
        'group': group,
        'data': data,
        'factors': factors,
        'workload_hash': digest(workload),
        'core_model_hash': digest(core),
        'request_hash': digest({'data': data, 'factors': factors, 'solver': solver}),
    }


def build_main_cases() -> list[dict]:
    """Prepare all labels in declared order without solving or deduplicating.

    The first 160 entries follow n/m/alpha/beta/tau/seed order with midpoint
    starts. Each of the 40 n8/m2 parents then contributes earliest and latest
    entries in parent order. Workloads bind n/seed/p/u/all four v plus the
    generator configuration. Physical core hashes omit only fixed_start;
    request hashes include complete input, factor labels, and solver settings.
    These 240 pairs are planned requests, not independent random workloads.
    """
    protocol = main_protocol()
    primary, sensitivity = protocol['primary'], protocol['sensitivity']
    workloads = {
        (n, seed): _base_workload(n, seed, protocol['generator'])
        for n, seed in product(primary['num_tasks'], primary['instance_seeds'])
    }
    cases = []
    for n, m, alpha, beta, tau, seed in product(
        primary['num_tasks'], primary['num_machines'], primary['alpha_percent'],
        primary['beta_percent'], primary['tau_percent'], primary['instance_seeds'],
    ):
        cases.append(_build_case(n, m, alpha, beta, tau, seed, 'window_midpoint',
                                 'primary', workloads[n, seed], protocol['solver']))
    for parent in cases[:]:
        factors = parent['factors']
        n, m = factors['num_tasks'], factors['num_machines']
        if n not in sensitivity['subset']['num_tasks'] or m not in sensitivity['subset']['num_machines']:
            continue
        for policy in sensitivity['additional_fixed_policies']:
            cases.append(_build_case(
                n, m, factors['alpha_percent'], factors['beta_percent'], factors['tau_percent'],
                factors['instance_seed'], policy, 'sensitivity',
                workloads[n, factors['instance_seed']], protocol['solver']))
    return cases
