"""Checked G3A row evidence and paired bounds, without batch authorization.

These helpers do not prepare inputs, grant approval, retry a solve, or claim
scientific success. The caller owns review gates, budgets and persistence.
"""

from dataclasses import asdict
import re

from src.ai_workflow.graduation_backend import METRICS, _checked_metrics, _restore
from src.graduation.data import (MaintenanceRequirement, ParallelMaintenanceInstance,
                                 ProductionTask)
from src.graduation.metrics import calculate_total_tardiness
from src.graduation.reference_protocol import digest, encoded
from src.graduation.solver import GraduationSolverError, solve_parallel_maintenance


_ROW_KEYS = {'case_id', 'mode', 'input_sha256', 'status', 'solver_status',
             'metrics', 'payload', 'error', 'solver'}
_NO_SCHEDULE = re.compile(r'CP-SAT returned (UNKNOWN|INFEASIBLE|MODEL_INVALID); no accepted schedule')


def _solver_settings():
    return {'time_limit': 1.0, 'num_workers': 1, 'seed': 42}


def _identity(case, mode):
    if mode not in ('fixed', 'joint'):
        raise ValueError('Main row mode must be fixed or joint')
    if (not isinstance(case, dict) or not isinstance(case.get('case_id'), str)
            or not case['case_id'] or 'data' not in case):
        raise ValueError('Main row requires an identified case with complete data')
    return {'case_id': case['case_id'], 'mode': mode, 'input_sha256': digest(case['data'])}


def _data(case):
    raw = case['data']
    if not isinstance(raw, dict) or set(raw) != {'tasks', 'num_machines', 'maintenance'}:
        raise ValueError('Malformed main G1 data snapshot')
    try:
        data = ParallelMaintenanceInstance(
            tuple(ProductionTask(**task) for task in raw['tasks']), raw['num_machines'],
            tuple(MaintenanceRequirement(**item) for item in raw['maintenance']))
    except (TypeError, KeyError) as exc:
        raise ValueError('Malformed main G1 data fields') from exc
    if any(item.fixed_start is None for item in data.maintenance):
        raise ValueError('Paired main input requires fixed_start on every machine')
    return data


def _snapshot(result):
    return {**{key: getattr(result, key) for key in METRICS},
            'records': [asdict(item) for item in result.records],
            'maintenance_records': [asdict(item) for item in result.maintenance_records]}


def evaluate_row(case, mode) -> dict:
    """Solve one request once with the original solver and recheck its schedule.

    Only the original solver's precise no-solution exception carries a known
    nonaccepting CP-SAT status. Arbitrary failures cannot manufacture that status.
    Invalid case/mode arguments raise ValueError before invoking the solver.
    """
    identity, data = _identity(case, mode), _data(case)
    row = {**identity, 'status': 'ERROR', 'solver_status': None, 'metrics': None,
           'payload': None, 'error': '', 'solver': _solver_settings()}
    try:
        result = solve_parallel_maintenance(data, mode=mode, **_solver_settings())
        metrics = _checked_metrics(data, result, mode)
        if metrics['total_tardiness'] != calculate_total_tardiness(data, result):
            raise ValueError('Main row total tardiness differs from the actual plan')
        accepted = {**row, 'status': 'ACCEPTED', 'solver_status': metrics['solver_status'],
                    'metrics': metrics, 'payload': _snapshot(result)}
        recheck_row(case, mode, accepted)
        return accepted
    except Exception as exc:
        match = _NO_SCHEDULE.fullmatch(str(exc)) if type(exc) is GraduationSolverError else None
        if match:
            row.update(status='NO_SCHEDULE', solver_status=match.group(1))
        row['error'] = f'{type(exc).__name__}: {str(exc)[:1000]}'
        return row


def recheck_row(case, mode, row) -> dict | None:
    """Read-only restoration; recompute accepted metrics or reject the evidence.

    NO_SCHEDULE/ERROR rows return None and must contain no metrics or plan. Row
    identity includes the complete shared input and exact fixed solver settings.
    """
    try:
        identity, data = _identity(case, mode), _data(case)
        if not isinstance(row, dict) or set(row) != _ROW_KEYS:
            raise ValueError('Malformed main result row')
        if any(row[key] != value for key, value in identity.items()):
            raise ValueError('Main result case, mode or complete input identity changed')
        if encoded(row['solver']) != encoded(_solver_settings()):
            raise ValueError('Main result fixed solver configuration changed')
        if not isinstance(row['error'], str):
            raise ValueError('Main result error must be a string')
        if row['status'] == 'ACCEPTED':
            if row['error'] or row['solver_status'] not in ('OPTIMAL', 'FEASIBLE'):
                raise ValueError('Accepted main row has an error or unaccepted solver status')
            if not isinstance(row['metrics'], dict) or set(row['metrics']) != set(METRICS):
                raise ValueError('Accepted main row requires all metrics')
            result = _restore(data, row['payload'])
            metrics = _checked_metrics(data, result, mode)
            if (metrics['total_tardiness'] != calculate_total_tardiness(data, result)
                    or row['solver_status'] != metrics['solver_status']
                    or encoded(row['metrics']) != encoded(metrics)):
                raise ValueError('Accepted main metrics disagree with the restored schedule')
            return metrics
        if (row['status'] not in ('NO_SCHEDULE', 'ERROR') or not row['error']
                or row['metrics'] is not None or row['payload'] is not None):
            raise ValueError('Failed main row must carry an error and null metrics/plan')
        if row['status'] == 'NO_SCHEDULE':
            status = row['solver_status']
            if (status not in ('UNKNOWN', 'INFEASIBLE', 'MODEL_INVALID')
                    or row['error'] != f'GraduationSolverError: CP-SAT returned {status}; no accepted schedule'):
                raise ValueError('No-schedule status does not match the original solver exception')
        elif (row['solver_status'] is not None
              or row['error'].startswith('GraduationSolverError: ')
              and _NO_SCHEDULE.fullmatch(row['error'][len('GraduationSolverError: '):])):
            raise ValueError('Error row claims or mislabels an original CP-SAT status')
        return None
    except (TypeError, KeyError, AttributeError, OverflowError) as exc:
        raise ValueError(f'Malformed main result evidence: {type(exc).__name__}') from exc


def compare_pair(case, fixed, joint) -> dict:
    """Compare valid incumbents separately from claims about the model optima.

    The optimum interval uses valid solver lower bounds and schedule upper bounds.
    A negative observed difference from limited search remains a valid observation.
    """
    pair = {'case_id': case['case_id'], 'group': case['group'], 'status': 'INCOMPLETE',
            'observed_difference': None, 'relative_improvement': None,
            'optimum_difference_lower': None, 'optimum_difference_upper': None,
            'both_optimal': False, 'error': ''}
    try:
        fixed_metrics = recheck_row(case, 'fixed', fixed)
        joint_metrics = recheck_row(case, 'joint', joint)
        if fixed_metrics is None or joint_metrics is None:
            pair['error'] = 'One or both rows have no accepted schedule'
            return pair
        fixed_t, joint_t = fixed_metrics['total_tardiness'], joint_metrics['total_tardiness']
        observed = fixed_t - joint_t
        lower = max(0, fixed_metrics['solver_objective_bound'] - joint_t)
        upper = fixed_t - joint_metrics['solver_objective_bound']
        both_optimal = fixed_metrics['solver_status'] == joint_metrics['solver_status'] == 'OPTIMAL'
        pair.update(status='COMPLETE', observed_difference=observed,
                    relative_improvement=None if fixed_t == 0 else observed/fixed_t,
                    optimum_difference_lower=lower, optimum_difference_upper=upper,
                    both_optimal=both_optimal)
        if both_optimal and joint_t > fixed_t:
            raise ValueError('Proven joint optimum exceeds proven fixed optimum')
        if upper < 0 or upper < lower:
            raise ValueError('Solver bounds imply an impossible optimum-difference interval')
    except ValueError as exc:
        pair.update(status='INTEGRITY_ERROR', error=str(exc)[:1000])
    return pair


def _recheck_unfinished(case, mode, row):
    identity = _identity(case, mode)
    if (not isinstance(row, dict) or set(row) != _ROW_KEYS
            or any(row[key] != value for key, value in identity.items())
            or encoded(row['solver']) != encoded(_solver_settings())):
        raise ValueError('Unfinished main row identity, schema or solver settings changed')
    if (row['status'] not in ('NOT_RUN', 'INTERRUPTED')
            or any(row[key] is not None for key in ('solver_status', 'metrics', 'payload'))
            or not isinstance(row['error'], str)
            or row['status'] == 'INTERRUPTED' and not row['error']):
        raise ValueError('Unfinished main row cannot carry accepted metrics or a schedule')


def summarize_rows(cases, rows) -> dict:
    """Recheck the complete planned denominator in declared fixed/joint order.

    This read-only summary is not replacement schedule evidence. Callers must
    retain all raw rows and plans, including failures and unfinished requests.
    Repeated physical models and workloads retain their labels; unique hashes
    describe dependence rather than turn repeated joint solves into samples.
    """
    if (not isinstance(cases, (list, tuple)) or not isinstance(rows, (list, tuple))
            or len(rows) != 2 * len(cases)):
        raise ValueError('Main summary requires exactly two planned rows per case')
    group_fields = ('planned_pairs', 'complete_pairs', 'both_optimal_pairs',
                    'strict_positive_observed', 'ties', 'negative_observed',
                    'incomplete_pairs', 'integrity_errors')
    groups = {name: dict.fromkeys(group_fields, 0) for name in ('primary', 'sensitivity')}
    statuses = dict.fromkeys(('ACCEPTED', 'NO_SCHEDULE', 'ERROR', 'NOT_RUN', 'INTERRUPTED'), 0)
    pairs, case_ids, workloads, cores = [], set(), set(), set()
    for index, case in enumerate(cases):
        if (not isinstance(case, dict) or not isinstance(case.get('group'), str)
                or case['group'] not in groups):
            raise ValueError('Main summary case group must be primary or sensitivity')
        _identity(case, 'fixed')
        _data(case)
        if case['case_id'] in case_ids:
            raise ValueError('Main summary cannot duplicate a planned case')
        case_ids.add(case['case_id'])
        for field, target in (('workload_hash', workloads), ('core_model_hash', cores)):
            value = case.get(field)
            if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
                raise ValueError('Main summary requires workload and core-model identities')
            target.add(value)
        pair_rows = rows[2 * index:2 * index + 2]
        unfinished = False
        for mode, row in zip(('fixed', 'joint'), pair_rows):
            if not isinstance(row, dict) or not isinstance(row.get('status'), str):
                raise ValueError('Malformed planned main row')
            if row['status'] in ('NOT_RUN', 'INTERRUPTED'):
                _recheck_unfinished(case, mode, row)
                unfinished = True
            else:
                recheck_row(case, mode, row)
            statuses[row['status']] += 1
        if unfinished:
            pair = {'case_id': case['case_id'], 'group': case['group'], 'status': 'INCOMPLETE',
                    'observed_difference': None, 'relative_improvement': None,
                    'optimum_difference_lower': None, 'optimum_difference_upper': None,
                    'both_optimal': False, 'error': 'One or both planned rows remain unfinished'}
        else:
            pair = compare_pair(case, *pair_rows)
        pairs.append(pair)
        group = groups[case['group']]
        group['planned_pairs'] += 1
        if pair['status'] == 'COMPLETE':
            group['complete_pairs'] += 1
            group['both_optimal_pairs'] += int(pair['both_optimal'])
            difference = pair['observed_difference']
            group['strict_positive_observed' if difference > 0 else
                  'negative_observed' if difference < 0 else 'ties'] += 1
        elif pair['status'] == 'INTEGRITY_ERROR':
            group['integrity_errors'] += 1
        else:
            group['incomplete_pairs'] += 1
    return {'planned_pairs': len(cases), 'planned_calls': len(rows),
            'accepted_runs': statuses['ACCEPTED'], 'status_counts': statuses,
            'completed_pairs': sum(group['complete_pairs'] for group in groups.values()),
            'pairs': pairs, 'groups': groups, 'base_workloads': len(workloads),
            'unique_core_models': len(cores), 'research_status': 'not_achieved'}
