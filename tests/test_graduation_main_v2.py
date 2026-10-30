import csv
import json

import pytest

from experiments import exp_035_graduation_main_v2 as experiment
from src.graduation.reference_main_protocol import build_main_cases


def _rows(path):
    with open(path, encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def test_smoke_keeps_order_rows_plans_and_pairs(tmp_path):
    cases = [c for c in build_main_cases() if c['factors']['num_tasks'] == 8][:2]
    manifest = experiment.run_experiment(tmp_path / 'out', cases)
    assert manifest['status'] == 'COMPLETED' and manifest['research_status'] == 'not_achieved'
    rows = _rows(tmp_path / 'out' / 'rows.csv')
    assert [(r['sequence'], r['mode']) for r in rows] == [('0', 'fixed'), ('1', 'joint'), ('2', 'fixed'), ('3', 'joint')]
    assert all(r['status'] == 'ACCEPTED' and int(r['total_tardiness']) <= float(r['solver_objective_value'])
               for r in rows)
    plans = json.loads((tmp_path / 'out' / 'plans.json').read_text(encoding='utf-8'))
    assert sorted(plans) == ['0', '1', '2', '3']
    pairs = _rows(tmp_path / 'out' / 'pairs.csv')
    assert [p['case_id'] for p in pairs] == [c['case_id'] for c in cases]
    assert manifest['summary']['status_counts'] == {'ACCEPTED': 4, 'NO_SCHEDULE': 0, 'ERROR': 0}
    with pytest.raises(FileExistsError):
        experiment.run_experiment(tmp_path / 'out', cases)


def _row(status='ACCEPTED', solver_status='OPTIMAL', total=10, bound=10.0):
    return {'status': status, 'solver_status': solver_status, 'total_tardiness': total,
            'solver_objective_bound': bound}


CASE = {'case_id': 'c', 'group': 'primary', 'factors': {'num_tasks': 8, 'num_machines': 2}}


def test_pair_definitions_match_reference_comparison():
    pair = experiment.compare(CASE, _row(total=10, bound=10.0), _row(total=4, bound=4.0))
    assert pair['status'] == 'COMPLETE' and pair['both_optimal']
    assert pair['observed_difference'] == 6 and pair['relative_improvement'] == 0.6
    assert pair['optimum_difference_lower'] == 6 and pair['optimum_difference_upper'] == 6
    zero = experiment.compare(CASE, _row(total=0, bound=0.0), _row(total=0, bound=0.0))
    assert zero['relative_improvement'] is None and zero['observed_difference'] == 0


def test_limited_search_keeps_negative_observation_but_rejects_impossible_claims():
    timed = experiment.compare(CASE, _row(solver_status='FEASIBLE', total=10, bound=0.0),
                               _row(solver_status='FEASIBLE', total=12, bound=0.0))
    assert timed['status'] == 'COMPLETE' and timed['observed_difference'] == -2
    proven = experiment.compare(CASE, _row(total=10, bound=10.0), _row(total=12, bound=12.0))
    assert proven['status'] == 'INTEGRITY_ERROR'
    incomplete = experiment.compare(CASE, _row(status='ERROR'), _row())
    assert incomplete['status'] == 'INCOMPLETE' and incomplete['observed_difference'] is None
