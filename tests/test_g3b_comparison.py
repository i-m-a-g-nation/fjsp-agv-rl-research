import copy
import csv

import pytest

from experiments import exp_038_g3b_comparison as experiment
from src.graduation.reference_main_protocol import build_main_cases


def test_final_model_is_chosen_by_validation_only():
    assert experiment.final_model_name() == 'policy_s0'


def test_smoke_combines_rules_policies_and_both_cp_references(tmp_path):
    cases = build_main_cases()
    subset = [next(c for c in cases if c['factors']['num_tasks'] == 8),
              next(c for c in cases if c['factors']['num_tasks'] == 24)]
    protocol = copy.deepcopy(experiment.PROTOCOL)
    protocol['cp_sat_long'].update(time_limit=1.0, num_workers=1, parallel_processes=2)
    manifest = experiment.run_experiment(tmp_path / 'out', protocol, subset)
    assert manifest['instances'] == 4 and manifest['cp_sat_long']['solves'] == 2
    assert manifest['cp_sat_long']['status_counts'] == {'ACCEPTED': 2, 'ERROR': 0}
    with open(tmp_path / 'out' / 'rows.csv', encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        values = [int(row[k]) for k in ('EDD', 'MDD', 'ATC', 'cp_sat_1s', 'policy_s0_r1', 'policy_s0_r9')]
        assert int(row['best_known']) == min(values + ([int(row['cp_sat_60s'])] if row['cp_sat_60s'] else []))
        assert (row['cp_sat_60s'] != '') == (row['num_tasks'] == '24')
    summary = manifest['summary']['all']
    assert all(v >= 0 for v in summary['mean_gap_to_best_known'].values())
    with pytest.raises(FileExistsError):
        experiment.run_experiment(tmp_path / 'out', protocol, subset)


def test_long_solve_returns_a_plan_and_rejects_malformed_input():
    case = build_main_cases()[0]
    bad = copy.deepcopy(case)
    bad['data']['tasks'][0]['processing_time'] = 0
    with pytest.raises(ValueError):
        experiment.solve_long((bad, 'fixed', experiment.PROTOCOL['cp_sat_long']))
    row = experiment.solve_long((case, 'fixed', {'time_limit': 1.0, 'num_workers': 1, 'seed': 42}))
    assert row['status'] == 'ACCEPTED' and row['plan']['records']
