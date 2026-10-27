"""Behavioral guards for the immutable Phase 1 instance input contract."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from src.data import instance as instance_module
from src.data.instance import FJSPInstance, Job, Operation
from src.data.loader import load_benchmark_instance, parse_fjsplib_text


@pytest.mark.parametrize("value", [True, False, 1.5, 1.0, "1", None])
@pytest.mark.parametrize("field", ["machine_id", "processing_time"])
def test_factory_rejects_non_integer_machine_and_duration(value, field):
    option = (value, 2) if field == "machine_id" else (0, value)
    with pytest.raises(ValueError, match=field):
        FJSPInstance.from_jobs_array([[[option]]], num_machines=2)


@pytest.mark.parametrize("num_machines", [True, False, 1.0, 1.5, "2"])
def test_factory_rejects_non_integer_machine_count(num_machines):
    with pytest.raises(ValueError, match="num_machines"):
        FJSPInstance.from_jobs_array([[[(0, 2)]]], num_machines=num_machines)


@pytest.mark.parametrize("options", [[(0, 2), (0, 2)], [(0, 2), (0, 3)]])
def test_duplicate_machine_options_are_rejected_before_solver(options):
    with pytest.raises(ValueError, match="duplicate machine"):
        FJSPInstance.from_jobs_array([[options]])


@pytest.mark.parametrize("options", [None, "01", [0], [(0,)], [(0, 2, 3)]])
def test_malformed_options_are_rejected_as_invalid_input(options):
    with pytest.raises(ValueError, match="machine option"):
        FJSPInstance.from_jobs_array([[options]])


@pytest.mark.parametrize("jobs", [None, "jobs", [None], ["ops"]])
def test_factory_rejects_malformed_job_containers(jobs):
    with pytest.raises(ValueError):
        FJSPInstance.from_jobs_array(jobs)


@pytest.mark.parametrize("op_id", [-1, True, 0.0])
def test_direct_operation_rejects_invalid_identifier(op_id):
    with pytest.raises(ValueError, match="op_id"):
        Operation(op_id, ((0, 2),))


@pytest.mark.parametrize("options", [(), ((-1, 2),), ((0, 0),), ((0, 1.5),), ((True, 2),), ((0, 2), (0, 2))])
def test_direct_operation_validates_its_options(options):
    with pytest.raises(ValueError):
        Operation(0, options)


@pytest.mark.parametrize("job_id", [-1, True, 0.0])
def test_direct_job_rejects_invalid_identifier(job_id):
    with pytest.raises(ValueError, match="job_id"):
        Job(job_id, (Operation(0, ((0, 2),)),))


@pytest.mark.parametrize("operations", [(), (object(),), (Operation(1, ((0, 2),)),), (Operation(0, ((0, 2),)), Operation(0, ((0, 3),)))])
def test_direct_job_requires_nonempty_contiguous_operations(operations):
    with pytest.raises(ValueError):
        Job(0, operations)


@pytest.mark.parametrize(
    ("num_jobs", "num_machines", "jobs"),
    [
        (1, 1, []),
        (True, 1, [Job(0, (Operation(0, ((0, 2),)),))]),
        (1.0, 1, [Job(0, (Operation(0, ((0, 2),)),))]),
        (1, True, [Job(0, (Operation(0, ((0, 2),)),))]),
        (1, 1.5, [Job(0, (Operation(0, ((0, 2),)),))]),
        (2, 1, [Job(0, (Operation(0, ((0, 2),)),))]),
        (1, 1, [Job(1, (Operation(0, ((0, 2),)),))]),
        (1, 1, [Job(0, (Operation(0, ((1, 2),)),))]),
        (1, 1, [object()]),
    ],
)
def test_direct_instance_validates_counts_ids_and_machine_range(num_jobs, num_machines, jobs):
    with pytest.raises(ValueError):
        FJSPInstance(num_jobs, num_machines, jobs)


def test_factory_copies_every_mutable_input_level_and_accepts_tuples():
    option = [0, 2]
    options = [option]
    operations = [options]
    jobs = [operations]
    instance = FJSPInstance.from_jobs_array(jobs)
    option[1] = 99
    options.append((0, 99))
    operations.clear()
    jobs.clear()
    assert instance.num_jobs == 1
    assert instance.total_ops == 1
    assert instance.get_op_options(0, 0) == ((0, 2),)
    assert instance == FJSPInstance.from_jobs_array(((((0, 2),),),))


def test_direct_constructors_copy_mutable_containers():
    option = [0, 2]
    options = [option]
    operation = Operation(0, options)
    operations = [operation]
    job = Job(0, operations)
    jobs = [job]
    instance = FJSPInstance(1, 1, jobs)
    option[1] = 99
    options.clear()
    operations.clear()
    jobs.clear()
    assert instance.get_processing_time(0, 0, 0) == 2
    assert instance.total_ops == 1
    assert isinstance(instance.jobs, tuple)
    assert isinstance(job.operations, tuple)
    assert isinstance(operation.machine_options, tuple)
    assert isinstance(operation.machine_options[0], tuple)


def test_instance_rejects_normal_attribute_and_nested_mutation():
    instance = FJSPInstance.from_jobs_array([[[(0, 2)]]])
    with pytest.raises(FrozenInstanceError):
        instance.num_machines = 4
    with pytest.raises(FrozenInstanceError):
        instance.jobs = ()
    with pytest.raises(TypeError):
        instance.jobs[0] = Job(0, (Operation(0, ((0, 3),)),))
    with pytest.raises(TypeError):
        instance.jobs[0].operations[0].machine_options[0][1] = 5


def test_validation_is_public_and_accepts_valid_instances():
    validator = getattr(instance_module, "validate_instance", None)
    assert callable(validator), "validate_instance is required at trust boundaries"
    assert validator(FJSPInstance.from_jobs_array([[[(0, 2)]]])) is None


@pytest.mark.parametrize(
    ("level", "field", "value"),
    [
        ("instance", "num_jobs", 2),
        ("instance", "num_machines", True),
        ("instance", "jobs", []),
        ("job", "job_id", 1),
        ("job", "operations", []),
        ("operation", "op_id", 1),
        ("operation", "machine_options", ((0, 1.5),)),
        ("operation", "machine_options", ((0, 2), (0, 2))),
        ("operation", "machine_options", [[0, 2]]),
        ("operation", "machine_options", ((1, 2),)),
    ],
)
def test_public_validation_detects_forged_instance_fields(level, field, value):
    validator = getattr(instance_module, "validate_instance", None)
    assert callable(validator), "validate_instance is required at trust boundaries"
    instance = FJSPInstance.from_jobs_array([[[(0, 2)]]])
    targets = {"instance": instance, "job": instance.jobs[0], "operation": instance.jobs[0].operations[0]}
    object.__setattr__(targets[level], field, value)
    with pytest.raises(ValueError):
        validator(instance)


@pytest.mark.parametrize("value", [None, object(), object.__new__(FJSPInstance)])
def test_public_validation_rejects_wrong_or_missing_structure(value):
    validator = getattr(instance_module, "validate_instance", None)
    assert callable(validator), "validate_instance is required at trust boundaries"
    with pytest.raises(ValueError):
        validator(value)


@pytest.mark.parametrize("machine_id", [1, 2])
def test_loader_auto_rejects_ambiguous_base(machine_id):
    text = f"1 3 1.0 1 1 {machine_id} 2"
    with pytest.raises(ValueError, match="ambiguous.*machine_index_base"):
        load_benchmark_instance(text)
    assert load_benchmark_instance(text, machine_index_base=0).get_op_options(0, 0) == ((machine_id, 2),)
    assert load_benchmark_instance(text, machine_index_base=1).get_op_options(0, 0) == ((machine_id - 1, 2),)


def test_loader_auto_infers_one_based_from_upper_boundary_without_machine_one():
    instance = load_benchmark_instance("1 3 1.0 1 1 3 2")
    assert instance.get_op_options(0, 0) == ((2, 2),)


@pytest.mark.parametrize("ids", [(0, 3), (-1, 2), (1, 4)])
def test_loader_auto_rejects_ranges_invalid_for_both_bases(ids):
    text = f"1 3 2.0 1 2 {ids[0]} 2 {ids[1]} 3"
    with pytest.raises(ValueError, match="range"):
        load_benchmark_instance(text)


@pytest.mark.parametrize("base", [True, False, 0.0, 1.0, "1"])
def test_loader_rejects_non_integer_explicit_base(base):
    with pytest.raises(ValueError, match="machine_index_base"):
        load_benchmark_instance("1 1 1.0 1 1 0 2", machine_index_base=base)


@pytest.mark.parametrize("mean", ["nan", "inf", "-inf", "0", "-1"])
def test_loader_rejects_nonfinite_or_nonpositive_header_mean(mean):
    with pytest.raises(ValueError, match="mean.*finite.*positive"):
        load_benchmark_instance(f"1 1 {mean} 1 1 0 2")


def test_parser_rejects_duplicate_machine_options():
    with pytest.raises(ValueError, match="duplicate machine"):
        parse_fjsplib_text("1 1 2.0 1 2 0 2 0 2")


def test_all_tracked_fjsplib_instances_still_load():
    root = Path(__file__).resolve().parents[1] / "instances" / "fjsplib"
    paths = sorted(root.rglob("*.fjs"))
    assert len(paths) == 30
    for path in paths:
        # FJSPLib declares 1-based machine IDs; mk06/mk10 do not contain a
        # boundary ID that permits auto detection from their data alone.
        instance = load_benchmark_instance(
            path.read_text(encoding="utf-8"), machine_index_base=1
        )
        assert instance.total_ops > 0, str(path)
def test_project_loader_uses_declared_base_only_inside_known_dataset(tmp_path):
    from pathlib import Path
    from src.data.loader import load_project_benchmark_file
    known = Path(__file__).resolve().parents[1] / 'instances/fjsplib/Brandimarte1993/mk06.fjs'
    assert load_project_benchmark_file(known).num_machines == 15
    outside = tmp_path / 'mk06.fjs'
    outside.write_bytes(known.read_bytes())
    with pytest.raises(ValueError, match='[Aa]mbigu|explicit'):
        load_project_benchmark_file(outside)


@pytest.mark.parametrize('job,op', [(-1, 0), (0, -1), (True, 0), (0, False), (0.0, 0)])
def test_instance_queries_reject_invalid_ids(job, op):
    data = FJSPInstance.from_jobs_array([[[(0, 5)]]])
    with pytest.raises(ValueError):
        data.get_op_options(job, op)


@pytest.mark.parametrize('machine', [True, False, 0.0, -1])
def test_instance_queries_reject_noninteger_or_negative_machine(machine):
    data = FJSPInstance.from_jobs_array([[[(0, 5)]]])
    with pytest.raises(ValueError):
        data.is_machine_eligible(0, 0, machine)
