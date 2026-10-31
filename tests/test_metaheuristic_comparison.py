import copy
import csv

import pytest

from experiments import exp_040_metaheuristics as experiment
from src.graduation.reference_main_protocol import build_main_cases


def _protocol():
    protocol = copy.deepcopy(experiment.PROTOCOL)
    protocol.update(budgets=[50, 200], seeds=[0, 1], parallel_processes=2)
    return protocol


def _subset():
    cases = build_main_cases()
    return [next(c for c in cases if c['factors']['num_tasks'] == 8),
            next(c for c in cases if c['factors']['num_tasks'] == 24)]


def test_smoke_merges_archived_references_and_summarizes(tmp_path):
    manifest = experiment.run_experiment(tmp_path / 'out', _protocol(), _subset())
    assert manifest['instances'] == 4 and manifest['runs'] == 4 * 3 * 2 * 2
    with open(tmp_path / 'out' / 'rows.csv', encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        best = float(row['best_known'])
        assert best <= float(row['best_known_exp_038'])
        for algorithm in ('GA', 'SA', 'IGA'):
            for budget in (50, 200):
                name = f'{algorithm}_{budget}'
                assert float(row[f'{name}_best']) <= float(row[name]) <= float(row[f'{name}_worst'])
                assert float(row[f'{name}_best']) >= best
    summary = manifest['summary']['all']
    assert all(gap >= 0 for gap in summary['mean_gap_to_best_known'].values())
    assert manifest['joint_gain']['all']['pairs'] == 2
    with pytest.raises(FileExistsError):
        experiment.run_experiment(tmp_path / 'out', _protocol(), _subset())


def test_value_below_a_proven_optimum_stops_the_run():
    protocol = _protocol()
    case = _subset()[0]
    result = experiment.run_instance((case, 'fixed', protocol))
    rows = experiment.build_rows([case], [result], protocol)
    assert rows[0]['best_known_proven_optimal']
    forged = dict(result, **{'GA_50_best': rows[0]['best_known_exp_038'] - 1})
    with pytest.raises(ValueError, match='beats a proven optimum'):
        experiment.build_rows([case], [forged], protocol)
