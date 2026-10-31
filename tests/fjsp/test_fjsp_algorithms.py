"""Every static FJSP algorithm returns a schedule that passes the checker."""

from pathlib import Path

import pytest

from fjsp_lab.fjsp import RULES, check_feasibility, create_toy_instance, load_project_benchmark_file, solve_rule
from fjsp_lab.fjsp.cpsat import solve_cpsat
from fjsp_lab.fjsp.gantt import plot_gantt

ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = ['Brandimarte1993/mk01.fjs', 'KacemHammadiBorne2002/kacem1.fjs', 'FattahiMehrabadJolai2007/fattahi5.fjs']


@pytest.mark.parametrize('rule', list(RULES))
@pytest.mark.parametrize('name', ['toy', *BENCHMARKS])
def test_every_rule_returns_a_feasible_schedule(rule, name):
    instance = create_toy_instance() if name == 'toy' else load_project_benchmark_file(ROOT / 'instances/fjsplib' / name)
    result = solve_rule(instance, rule)
    passed, violations = check_feasibility(result, expected_instance=instance)
    assert passed is True, violations
    assert result.makespan == max(r.end for r in result.records)


def test_rules_are_deterministic_and_random_uses_its_seed():
    instance = load_project_benchmark_file(ROOT / 'instances/fjsplib/Brandimarte1993/mk01.fjs')
    assert solve_rule(instance, 'SPT').records == solve_rule(instance, 'SPT').records
    assert solve_rule(instance, 'Random', seed=3).records == solve_rule(instance, 'Random', seed=3).records
    with pytest.raises(ValueError):
        solve_rule(instance, 'LPT')


def test_toy_rule_makespans_are_stable():
    makespans = {rule: solve_rule(create_toy_instance(), rule).makespan for rule in RULES}
    assert makespans == {'FIFO': 11, 'SPT': 13, 'EAM': 11, 'EFT': 13, 'MWKR': 12, 'MOPNR': 12, 'Random': 14}


def test_cpsat_proves_toy_optimum_and_beats_no_rule():
    instance = create_toy_instance()
    result = solve_cpsat(instance, time_limit=10)
    passed, violations = check_feasibility(result, expected_instance=instance)
    assert passed is True, violations
    assert (result.solver_status, result.makespan, result.solver_gap) == ('OPTIMAL', 11, 0.0)
    assert all(result.makespan <= solve_rule(instance, rule).makespan for rule in RULES)


def test_cpsat_time_limited_result_is_only_labelled_feasible():
    instance = load_project_benchmark_file(ROOT / 'instances/fjsplib/Brandimarte1993/mk10.fjs')
    result = solve_cpsat(instance, time_limit=0.5)
    assert check_feasibility(result, expected_instance=instance)[0] is True
    assert result.solver_status in ('OPTIMAL', 'FEASIBLE')
    if result.solver_status == 'FEASIBLE':
        assert result.solver_objective_bound <= result.makespan


@pytest.mark.parametrize('kwargs', [{'time_limit': 0}, {'time_limit': float('nan')}, {'num_workers': -1}, {'seed': True}])
def test_cpsat_rejects_invalid_settings(kwargs):
    with pytest.raises(ValueError):
        solve_cpsat(create_toy_instance(), **kwargs)


def test_gantt_writes_png(tmp_path):
    path = tmp_path / 'toy.png'
    plot_gantt(solve_rule(create_toy_instance(), 'FIFO'), save_path=path)
    assert path.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n'
