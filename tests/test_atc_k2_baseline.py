import copy
import csv

import pytest

from experiments import exp_039_atc_k2_baseline as experiment


def test_smoke_reproduces_archived_rules_and_adds_k2_baselines(tmp_path):
    manifest = experiment.run_experiment(tmp_path / 'out', limit=6)
    assert manifest['instances'] == {'exp_037_test': 6, 'g3_grid': 6}
    for name in ('exp_037_test_rows.csv', 'g3_rows.csv'):
        with open(tmp_path / 'out' / name, encoding='utf-8', newline='') as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            edd, mdd, atc, k2 = (int(row[c]) for c in ('EDD', 'MDD', 'ATC', 'ATC_k2'))
            assert int(row['best_of_3_rules_k2']) == min(edd, mdd, k2)
            assert int(row['best_of_3_rules']) == min(edd, mdd, atc)
            assert int(row['best_of_9_rules']) <= min(edd, mdd, atc, k2, int(row['ATC_k3']))
    assert 'case_id' in rows[0] and 'group' in rows[0]
    with pytest.raises(FileExistsError):
        experiment.run_experiment(tmp_path / 'out', limit=6)


def test_mismatch_with_archived_rules_stops_the_run():
    instances = experiment.make_instances(range(40000, 40600), sampler_seed=4, balanced=True)[:1]
    archived = experiment._read(experiment.TEST_RAW)[:1]
    tampered = copy.deepcopy(archived)
    tampered[0]['MDD'] = str(int(tampered[0]['MDD']) + 1)
    experiment.build_rows(instances, archived, [{}])
    with pytest.raises(ValueError, match='MDD rerun'):
        experiment.build_rows(instances, tampered, [{}])


def test_summary_pairs_every_policy_with_each_baseline():
    rows = experiment.test_split(limit=12)
    summary = experiment.summarize(rows, ('num_tasks', 'num_machines'))['all']
    pairs = {(p['method'], p['baseline']) for p in summary['policy_vs_rule']}
    assert ('policy_s0_r1', 'ATC_k2') in pairs and ('policy_s2_r3', 'best_of_3_rules_k2') in pairs
    assert len(pairs) == 3 * 5
