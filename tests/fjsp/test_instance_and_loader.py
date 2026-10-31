from pathlib import Path

import pytest

from fjsp_lab.fjsp import FJSPInstance, create_toy_instance, load_benchmark_instance, load_project_benchmark_file
from fjsp_lab.fjsp.benchmark import TOY_INSTANCES

ROOT = Path(__file__).resolve().parents[2]


def test_toy_instance_shape_and_lookup():
    instance = create_toy_instance()
    assert (instance.num_jobs, instance.num_machines, instance.total_ops) == (3, 3, 7)
    assert instance.get_processing_time(0, 0, 1) == 5
    assert instance.is_machine_eligible(1, 1, 1) and not instance.is_machine_eligible(1, 1, 0)
    with pytest.raises(ValueError):
        instance.get_processing_time(1, 1, 0)


def test_instance_is_immutable():
    instance = create_toy_instance()
    with pytest.raises(AttributeError):
        instance.num_jobs = 5
    assert isinstance(instance.jobs[0].operations[0].machine_options, tuple)


@pytest.mark.parametrize('jobs, message', [
    ([], 'at least one job'),
    ([[]], 'at least one operation'),
    ([[[]]], 'machine options'),
    ([[[(0, 0)]]], 'positive'),
    ([[[(0, 3), (0, 4)]]], 'duplicate'),
    ([[[(0, True)]]], 'integer'),
    ([[[(0, 2.0)]]], 'integer'),
])
def test_invalid_instance_data_is_rejected(jobs, message):
    with pytest.raises(ValueError, match=message):
        FJSPInstance.from_jobs_array(jobs)


def test_machine_id_must_fit_num_machines():
    with pytest.raises(ValueError, match='exceeds num_machines'):
        FJSPInstance.from_jobs_array([[[(2, 1)]]], num_machines=2)


def test_loader_normalizes_one_based_ids():
    instance = load_benchmark_instance('2 2 1\n1 1 2 5\n1 1 1 3\n', machine_index_base=1)
    assert instance.jobs[0].operations[0].machine_options == ((1, 5),)
    assert instance.jobs[1].operations[0].machine_options == ((0, 3),)


def test_loader_rejects_ambiguous_auto_base_and_trailing_tokens():
    with pytest.raises(ValueError, match='ambiguous'):
        load_benchmark_instance('1 2 1\n1 1 1 4\n')
    with pytest.raises(ValueError, match='trailing'):
        load_benchmark_instance('1 1 1\n1 1 0 4\n9\n')


def test_toy_text_matches_toy_instance():
    assert load_benchmark_instance(TOY_INSTANCES['toy_3x3']) == create_toy_instance()


def test_all_project_benchmarks_load():
    files = sorted((ROOT / 'instances/fjsplib').rglob('*.fjs'))
    assert len(files) == 30
    mk01 = load_project_benchmark_file(ROOT / 'instances/fjsplib/Brandimarte1993/mk01.fjs')
    assert (mk01.num_jobs, mk01.num_machines) == (10, 6)
    for path in files:
        assert load_project_benchmark_file(path).total_ops > 0
