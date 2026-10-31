import copy
import csv

import pytest

from experiments import exp_041_seeded_iga as experiment
from src.graduation.reference_main_protocol import build_main_cases


def _protocol():
    protocol = copy.deepcopy(experiment.PROTOCOL)
    protocol.update(budgets=[60, 200], seeds=[0, 1], parallel_processes=2)
    return protocol


def _subset():
    cases = build_main_cases()
    return [next(c for c in cases if c['factors']['num_tasks'] == 8),
            next(c for c in cases if c['factors']['num_tasks'] == 24)]


def test_smoke_runs_all_variants_and_reports_seed_fidelity(tmp_path):
    manifest = experiment.run_experiment(tmp_path / 'out', _protocol(), _subset())
    assert manifest['instances'] == 4
    with open(tmp_path / 'out' / 'rows.csv', encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        assert int(row['rl9_seed_count']) == 9 and int(row['rule9_seed_count']) == 9
        assert 0 <= int(row['rl9_reproduced']) <= 9
        assert int(row['rl9_plan_best']) <= int(row['rl1_plan'])
        for variant in experiment.PROTOCOL['variants']:
            for budget in (60, 200):
                assert float(row[f'{variant}_{budget}']) >= float(row['best_known'])
    summary = manifest['summary']['all']
    assert 0 <= summary['seed_reproduction_rate']['rl9'] <= 1
    assert summary['mean_seconds']['IGA+RL9_60'] > summary['mean_seconds']['IGA_60']
    with pytest.raises(FileExistsError):
        experiment.run_experiment(tmp_path / 'out', _protocol(), _subset())


def test_value_below_a_proven_optimum_stops_the_run():
    protocol = _protocol()
    case = _subset()[0]
    result = experiment.run_instance((case, 'fixed', protocol))
    rows = experiment.build_rows([result], protocol)
    assert rows[0]['best_known_proven_optimal']
    forged = dict(result, **{'IGA_60_best': rows[0]['best_known_exp_040'] - 1})
    with pytest.raises(ValueError, match='beats a proven optimum'):
        experiment.build_rows([forged], protocol)
    drifted = dict(result, rl1_plan=result['rl1_plan'] + 1)
    with pytest.raises(ValueError, match='archived policy_s0_r1'):
        experiment.build_rows([drifted], protocol)
