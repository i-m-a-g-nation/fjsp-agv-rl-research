"""Development-only row evidence; no formal G3 main-grid solve is performed."""

from copy import deepcopy
from dataclasses import asdict

import pytest

from src.ai_workflow.graduation_backend import METRICS
from src.graduation import reference_main_results as main
from src.graduation.reference_protocol import digest
from src.graduation.solver import GraduationSolverError
from tests.graduation_helpers import one_machine


def case_and_result(*, fixed=True, due_dates=(2, 4)):
    data, result = one_machine(fixed=fixed, due_dates=due_dates)
    result.total_tardiness = sum(max(0, record.end - due_dates[record.job_id])
                                 for record in result.records)
    result.solver_status = 'FEASIBLE'
    result.solver_objective_value = float(result.total_tardiness)
    result.solver_objective_bound = 0.0
    result.solver_gap = result.total_tardiness / max(1, result.total_tardiness)
    result.solver_wall_time = 0.01
    case = {'case_id': 'DEVTEST-main-row', 'group': 'primary', 'data': asdict(data)}
    return case, result


def accepted_row(monkeypatch, *, fixed=True, due_dates=(2, 4)):
    case, result = case_and_result(fixed=fixed, due_dates=due_dates)
    monkeypatch.setattr(main, 'solve_parallel_maintenance', lambda *a, **k: result)
    return case, main.evaluate_row(case, 'fixed' if fixed else 'joint')


def test_feasible_row_rechecks_full_plan_without_promoting_status(monkeypatch):
    case, result = case_and_result()
    calls = []
    def solve(data, **settings):
        calls.append(settings)
        return result
    monkeypatch.setattr(main, 'solve_parallel_maintenance', solve)
    row = main.evaluate_row(case, 'fixed')
    assert calls == [{'mode': 'fixed', 'time_limit': 1.0, 'num_workers': 1, 'seed': 42}]
    assert set(row) == {'case_id', 'mode', 'input_sha256', 'status', 'solver_status',
                        'metrics', 'payload', 'error', 'solver'}
    assert row['status'] == 'ACCEPTED' and row['solver_status'] == 'FEASIBLE'
    assert row['input_sha256'] == digest(case['data'])
    assert set(row['metrics']) == set(METRICS)
    assert set(row['payload']) == {*METRICS, 'records', 'maintenance_records'}
    assert main.recheck_row(case, 'fixed', row) == row['metrics']


@pytest.mark.parametrize('status', ['UNKNOWN', 'INFEASIBLE', 'MODEL_INVALID'])
def test_known_no_schedule_status_has_no_metrics_or_payload(monkeypatch, status):
    case, _ = case_and_result()
    def solve(*args, **kwargs):
        raise GraduationSolverError(f'CP-SAT returned {status}; no accepted schedule')
    monkeypatch.setattr(main, 'solve_parallel_maintenance', solve)
    row = main.evaluate_row(case, 'joint')
    assert row['status'] == 'NO_SCHEDULE' and row['solver_status'] == status
    assert row['metrics'] is row['payload'] is None
    assert main.recheck_row(case, 'joint', row) is None


def test_no_schedule_record_cannot_be_relabelled_or_change_its_exception(monkeypatch):
    case, _ = case_and_result()
    def solve(*a, **k):
        raise GraduationSolverError('CP-SAT returned UNKNOWN; no accepted schedule')
    monkeypatch.setattr(main, 'solve_parallel_maintenance', solve)
    row = main.evaluate_row(case, 'joint')
    forged = {**row, 'status': 'ERROR', 'solver_status': None}
    with pytest.raises(ValueError): main.recheck_row(case, 'joint', forged)
    forged = {**row, 'solver_status': 'INFEASIBLE'}
    with pytest.raises(ValueError): main.recheck_row(case, 'joint', forged)


@pytest.mark.parametrize('error', [
    RuntimeError('CP-SAT returned UNKNOWN; no accepted schedule'),
    GraduationSolverError('CP-SAT returned UNKNOWN; no accepted schedule suffix'),
    GraduationSolverError('CP-SAT model invalid: diagnostic'),
    GraduationSolverError('Solution extraction/validation failed: UNKNOWN'),
    ValueError('ordinary failure'),
])
def test_arbitrary_exception_cannot_invent_a_solver_status(monkeypatch, error):
    case, _ = case_and_result()
    def solve(*args, **kwargs):
        raise error
    monkeypatch.setattr(main, 'solve_parallel_maintenance', solve)
    row = main.evaluate_row(case, 'fixed')
    assert row['status'] == 'ERROR' and row['solver_status'] is None
    assert row['metrics'] is row['payload'] is None
    assert main.recheck_row(case, 'fixed', row) is None


@pytest.mark.parametrize('fault', ['total', 'makespan', 'overlap', 'bound', 'gap', 'time', 'status'])
def test_rejected_solver_candidate_never_exposes_accepted_metrics(monkeypatch, fault):
    case, result = case_and_result()
    if fault == 'total': result.total_tardiness += 1
    elif fault == 'makespan': result.makespan += 1
    elif fault == 'overlap': result.maintenance_records[0].start += 1
    elif fault == 'bound': result.solver_objective_bound = float('nan')
    elif fault == 'gap': result.solver_gap = 0
    elif fault == 'time': result.solver_wall_time = -1
    else: result.solver_status = 'UNKNOWN'
    monkeypatch.setattr(main, 'solve_parallel_maintenance', lambda *a, **k: result)
    row = main.evaluate_row(case, 'fixed')
    assert row['status'] == 'ERROR'
    assert row['metrics'] is row['payload'] is None


@pytest.mark.parametrize('fault', [
    'case', 'mode', 'input', 'config', 'config_bool', 'config_extra', 'metric', 'metric_bool',
    'payload_total', 'records', 'maintenance', 'status', 'solver_status', 'error', 'extra',
])
def test_accepted_row_identity_and_plan_tampering_is_rejected(monkeypatch, fault):
    case, row = accepted_row(monkeypatch)
    row = deepcopy(row)
    if fault == 'case': row['case_id'] += '-changed'
    elif fault == 'mode': row['mode'] = 'joint'
    elif fault == 'input': row['input_sha256'] = '0' * 64
    elif fault == 'config': row['solver']['seed'] = 43
    elif fault == 'config_bool': row['solver']['num_workers'] = True
    elif fault == 'config_extra': row['solver']['timing_repetitions'] = 1
    elif fault == 'metric': row['metrics']['total_tardiness'] += 1
    elif fault == 'metric_bool': row['metrics']['solver_gap'] = True
    elif fault == 'payload_total': row['payload']['total_tardiness'] += 1
    elif fault == 'records': row['payload']['records'].pop()
    elif fault == 'maintenance': row['payload']['maintenance_records'].clear()
    elif fault == 'status': row['status'] = 'NO_SCHEDULE'
    elif fault == 'solver_status': row['solver_status'] = 'OPTIMAL'
    elif fault == 'error': row['error'] = 'failure'
    else: row['extra'] = 1
    with pytest.raises(ValueError):
        main.recheck_row(case, 'fixed', row)


def test_changed_complete_input_cannot_reuse_row(monkeypatch):
    case, row = accepted_row(monkeypatch)
    changed = deepcopy(case)
    changed['data']['tasks'][0]['due_date'] += 1
    with pytest.raises(ValueError): main.recheck_row(changed, 'fixed', row)
    with pytest.raises(ValueError): main.recheck_row(case, 'wrong', row)


@pytest.mark.parametrize('fault', ['metrics', 'payload', 'empty_error', 'status', 'invented_status'])
def test_failed_rows_cannot_carry_metrics_or_forged_status(monkeypatch, fault):
    case, _ = case_and_result()
    def solve(*a, **k): raise RuntimeError('not solved')
    monkeypatch.setattr(main, 'solve_parallel_maintenance', solve)
    row = main.evaluate_row(case, 'fixed')
    if fault == 'metrics': row['metrics'] = dict.fromkeys(METRICS)
    elif fault == 'payload': row['payload'] = {}
    elif fault == 'empty_error': row['error'] = ''
    elif fault == 'status': row['status'] = 'NO_SCHEDULE'
    else: row['solver_status'] = 'UNKNOWN'
    with pytest.raises(ValueError): main.recheck_row(case, 'fixed', row)


def test_negative_observed_difference_is_valid_for_limited_search(monkeypatch):
    case, fixed_result = case_and_result()
    _, joint_result = case_and_result()
    # Legal joint schedule with idle production, worse than the fixed incumbent.
    for record in joint_result.records:
        record.start += 1
        record.end += 1
    joint_result.compute_makespan()
    joint_result.total_tardiness = 6
    joint_result.solver_objective_value = 6.0
    monkeypatch.setattr(main, 'solve_parallel_maintenance', lambda *a, mode, **k:
                        fixed_result if mode == 'fixed' else joint_result)
    fixed, joint = (main.evaluate_row(case, mode) for mode in ('fixed', 'joint'))
    pair = main.compare_pair(case, fixed, joint)
    assert pair['status'] == 'COMPLETE'
    assert pair['observed_difference'] == -2 and pair['relative_improvement'] == -0.5
    assert pair['optimum_difference_lower'] == 0 and pair['optimum_difference_upper'] == 4
    assert pair['both_optimal'] is False


def test_pair_interval_zero_denominator_and_actual_optimal_claim(monkeypatch):
    case, fixed = accepted_row(monkeypatch)
    _, joint = accepted_row(monkeypatch, fixed=False)
    pair = main.compare_pair(case, fixed, joint)
    assert pair['status'] == 'COMPLETE' and pair['observed_difference'] == 4
    assert pair['optimum_difference_lower'] == 0 and pair['optimum_difference_upper'] == 4
    case, fixed = accepted_row(monkeypatch, due_dates=(10, 10))
    _, joint = accepted_row(monkeypatch, fixed=False, due_dates=(10, 10))
    assert main.compare_pair(case, fixed, joint)['relative_improvement'] is None
    for row in (fixed, joint):
        row['solver_status'] = row['metrics']['solver_status'] = row['payload']['solver_status'] = 'OPTIMAL'
    assert main.compare_pair(case, fixed, joint)['both_optimal'] is True


def test_feasible_bound_can_support_strict_improvement_without_claiming_optimality(monkeypatch):
    case, fixed = accepted_row(monkeypatch)
    _, joint = accepted_row(monkeypatch, fixed=False)
    for values in (fixed['metrics'], fixed['payload']):
        values.update(solver_objective_bound=3, solver_gap=0.25)
    pair = main.compare_pair(case, fixed, joint)
    assert pair['status'] == 'COMPLETE' and pair['both_optimal'] is False
    assert pair['optimum_difference_lower'] == 3
    assert pair['optimum_difference_upper'] == 4


def test_optimal_metadata_requires_bound_to_equal_the_plan_objective(monkeypatch):
    case, result = case_and_result()
    result.solver_status = 'OPTIMAL'
    monkeypatch.setattr(main, 'solve_parallel_maintenance', lambda *a, **k: result)
    row = main.evaluate_row(case, 'fixed')
    assert row['status'] == 'ERROR' and row['metrics'] is None


@pytest.mark.parametrize('fault', ['optimal_inversion', 'negative_upper', 'reversed_interval'])
def test_impossible_optimum_comparisons_are_integrity_errors(monkeypatch, fault):
    case, fixed = accepted_row(monkeypatch)
    _, joint = accepted_row(monkeypatch, fixed=False)
    if fault == 'optimal_inversion':
        # Independently legal plans can carry incompatible claimed optima.
        for mode, row in (('fixed', fixed), ('joint', joint)):
            if mode == 'joint':
                for record in row['payload']['records']:
                    record['start'] += 4
                    record['end'] += 4
                # Move maintenance too, to keep the delayed plan legal.
                row['payload']['maintenance_records'][0].update(start=0, end=2)
                row['payload']['makespan'] = row['metrics']['makespan'] = 8
                row['payload']['total_tardiness'] = row['metrics']['total_tardiness'] = 8
            for values in (row['metrics'], row['payload']):
                values.update(solver_status='OPTIMAL', solver_objective_value=values['total_tardiness'],
                              solver_objective_bound=values['total_tardiness'], solver_gap=0)
            row['solver_status'] = 'OPTIMAL'
    elif fault == 'negative_upper':
        # Use the fixed plan as a legal joint plan with a claimed LB above fixed UB.
        joint = deepcopy(fixed)
        joint['mode'] = 'joint'
        for record in joint['payload']['records']:
            record['start'] += 1
            record['end'] += 1
        for values in (joint['metrics'], joint['payload']):
            values.update(makespan=7, total_tardiness=6, solver_objective_value=6,
                          solver_objective_bound=5, solver_gap=1/6)
    else:
        # fixed LB - joint UB = 4, fixed UB - joint LB = 3.
        for values in (fixed['metrics'], fixed['payload']):
            values.update(solver_objective_bound=4, solver_gap=0)
        for values in (joint['metrics'], joint['payload']):
            values.update(solver_objective_bound=1)  # invalid row metadata must also reject
    assert main.compare_pair(case, fixed, joint)['status'] == 'INTEGRITY_ERROR'


def test_missing_schedule_preserves_incomplete_pair_and_bad_row_is_integrity_error(monkeypatch):
    case, fixed = accepted_row(monkeypatch)
    def solve(*a, **k): raise GraduationSolverError('CP-SAT returned UNKNOWN; no accepted schedule')
    monkeypatch.setattr(main, 'solve_parallel_maintenance', solve)
    joint = main.evaluate_row(case, 'joint')
    pair = main.compare_pair(case, fixed, joint)
    assert pair['case_id'] == case['case_id'] and pair['group'] == 'primary'
    assert pair['status'] == 'INCOMPLETE'
    assert all(pair[name] is None for name in ('observed_difference', 'relative_improvement',
                                             'optimum_difference_lower', 'optimum_difference_upper'))
    fixed['input_sha256'] = '0' * 64
    assert main.compare_pair(case, fixed, joint)['status'] == 'INTEGRITY_ERROR'


def test_two_tiny_original_g2_solver_modes_only():
    case, _ = case_and_result()
    rows = [main.evaluate_row(case, mode) for mode in ('fixed', 'joint')]
    assert [row['solver_status'] for row in rows] == ['OPTIMAL', 'OPTIMAL']
    assert [row['metrics']['total_tardiness'] for row in rows] == [4, 0]
    pair = main.compare_pair(case, *rows)
    assert pair['status'] == 'COMPLETE' and pair['both_optimal']
    assert pair['optimum_difference_lower'] == pair['optimum_difference_upper'] == 4
    case.update(workload_hash='a' * 64, core_model_hash='b' * 64)
    summary = main.summarize_rows([case], rows)
    assert summary['completed_pairs'] == summary['groups']['primary']['both_optimal_pairs'] == 1


def planned_row(case, mode, status='NOT_RUN'):
    return {'case_id': case['case_id'], 'mode': mode, 'input_sha256': digest(case['data']),
            'status': status, 'solver_status': None, 'metrics': None, 'payload': None,
            'error': '' if status == 'NOT_RUN' else 'Development worker interrupted',
            'solver': {'time_limit': 1.0, 'num_workers': 1, 'seed': 42}}


def summary_case_rows(monkeypatch, *, name='one', group='primary', fixed=True):
    case, fixed_row = accepted_row(monkeypatch)
    _, joint_row = accepted_row(monkeypatch, fixed=not fixed)
    case.update(case_id=f'DEVTEST-{name}', group=group, workload_hash='a' * 64,
                core_model_hash='b' * 64)
    for mode, row in zip(('fixed', 'joint'), (fixed_row, joint_row)):
        row.update(case_id=case['case_id'], mode=mode)
    return case, [fixed_row, joint_row]


def test_summary_retains_planned_denominator_and_aliases_without_mutating_rows(monkeypatch):
    first, complete = summary_case_rows(monkeypatch)
    second = {**deepcopy(first), 'case_id': 'DEVTEST-two', 'group': 'sensitivity'}
    third = {**deepcopy(first), 'case_id': 'DEVTEST-three', 'workload_hash': 'c' * 64,
             'core_model_hash': 'd' * 64}
    rows = complete + [planned_row(second, 'fixed', 'INTERRUPTED'), planned_row(second, 'joint')]
    rows += [planned_row(third, 'fixed'), planned_row(third, 'joint')]
    before = deepcopy(rows)
    summary = main.summarize_rows([first, second, third], rows)
    assert rows == before and rows[0]['payload']['records']
    assert summary['planned_pairs'] == 3 and summary['planned_calls'] == 6
    assert summary['accepted_runs'] == 2 and summary['completed_pairs'] == 1
    assert summary['base_workloads'] == summary['unique_core_models'] == 2
    assert summary['status_counts'] == {'ACCEPTED': 2, 'NO_SCHEDULE': 0, 'ERROR': 0,
                                         'NOT_RUN': 3, 'INTERRUPTED': 1}
    assert [pair['status'] for pair in summary['pairs']] == ['COMPLETE', 'INCOMPLETE', 'INCOMPLETE']
    assert summary['groups']['primary'] == {
        'planned_pairs': 2, 'complete_pairs': 1, 'both_optimal_pairs': 0,
        'strict_positive_observed': 1, 'ties': 0, 'negative_observed': 0,
        'incomplete_pairs': 1, 'integrity_errors': 0}
    assert summary['groups']['sensitivity']['planned_pairs'] == 1
    assert summary['groups']['sensitivity']['incomplete_pairs'] == 1
    assert summary['research_status'] == 'not_achieved'


def test_summary_counts_ties_negative_observations_and_incomplete_statuses(monkeypatch):
    case, rows = summary_case_rows(monkeypatch)
    # The fixed schedule is a legal joint schedule too, giving a tie.
    rows[1] = {**deepcopy(rows[0]), 'mode': 'joint'}
    tie = main.summarize_rows([case], rows)
    assert tie['groups']['primary']['ties'] == 1
    for record in rows[1]['payload']['records']:
        record['start'] += 1
        record['end'] += 1
    for metrics in (rows[1]['metrics'], rows[1]['payload']):
        metrics.update(makespan=7, total_tardiness=6, solver_objective_value=6)
    negative = main.summarize_rows([case], rows)
    assert negative['groups']['primary']['negative_observed'] == 1
    assert negative['pairs'][0]['observed_difference'] == -2
    for status, error, solver_status in (
        ('NO_SCHEDULE', 'GraduationSolverError: CP-SAT returned UNKNOWN; no accepted schedule', 'UNKNOWN'),
        ('ERROR', 'RuntimeError: development failure', None)):
        rows[1] = {**planned_row(case, 'joint'), 'status': status, 'error': error,
                   'solver_status': solver_status}
        failed = main.summarize_rows([case], rows)
        assert failed['accepted_runs'] == 1 and failed['completed_pairs'] == 0
        assert failed['status_counts'][status] == 1
        assert failed['groups']['primary']['incomplete_pairs'] == 1
        assert failed['pairs'][0]['observed_difference'] is None


def test_summary_retains_integrity_errors_without_counting_an_improvement(monkeypatch):
    case, rows = summary_case_rows(monkeypatch)
    rows[1] = {**deepcopy(rows[0]), 'mode': 'joint'}
    for record in rows[1]['payload']['records']:
        record['start'] += 1
        record['end'] += 1
    for metrics in (rows[1]['metrics'], rows[1]['payload']):
        metrics.update(makespan=7, total_tardiness=6, solver_objective_value=6,
                       solver_objective_bound=5, solver_gap=1/6)
    summary = main.summarize_rows([case], rows)
    assert summary['accepted_runs'] == 2 and summary['completed_pairs'] == 0
    assert summary['pairs'][0]['status'] == 'INTEGRITY_ERROR'
    assert summary['groups']['primary']['integrity_errors'] == 1
    assert summary['groups']['primary']['negative_observed'] == 0


def test_unstarted_rows_may_preserve_the_batch_stop_diagnostic(monkeypatch):
    case, _ = summary_case_rows(monkeypatch)
    rows = [planned_row(case, mode) for mode in ('fixed', 'joint')]
    rows[1]['error'] = 'Batch budget exhausted before this request'
    summary = main.summarize_rows([case], rows)
    assert summary['status_counts']['NOT_RUN'] == 2
    assert summary['accepted_runs'] == summary['completed_pairs'] == 0


@pytest.mark.parametrize('fault', ['missing', 'extra', 'order', 'case', 'duplicate_case',
                                   'case_order', 'data', 'group', 'group_list', 'hash', 'payload',
                                   'interrupted_payload', 'not_run_metrics', 'running'])
def test_summary_rejects_changed_denominator_order_case_or_unfinished_evidence(monkeypatch, fault):
    case, rows = summary_case_rows(monkeypatch)
    cases = [case]
    if fault == 'missing': rows.pop()
    elif fault == 'extra': rows.append(deepcopy(rows[0]))
    elif fault == 'order': rows.reverse()
    elif fault == 'case': rows[0]['case_id'] = 'wrong'
    elif fault == 'duplicate_case': cases.append(deepcopy(case)); rows += deepcopy(rows)
    elif fault == 'case_order':
        other = {**deepcopy(case), 'case_id': 'DEVTEST-other'}
        rows += [planned_row(other, mode) for mode in ('fixed', 'joint')]
        cases = [other, case]
    elif fault == 'data': case['data']['maintenance'][0]['fixed_start'] += 1
    elif fault == 'group': case['group'] = 'unrecognized'
    elif fault == 'group_list': case['group'] = []
    elif fault == 'hash': case['workload_hash'] = ''
    elif fault == 'payload': rows[0]['payload']['records'].clear()
    elif fault == 'interrupted_payload': rows[0]['status'] = 'INTERRUPTED'
    elif fault == 'not_run_metrics': rows[0]['status'] = 'NOT_RUN'
    else: rows[0]['status'] = 'RUNNING'
    with pytest.raises(ValueError): main.summarize_rows(cases, rows)
