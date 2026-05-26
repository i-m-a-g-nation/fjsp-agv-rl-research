import pytest

from src.data.instance import (
    FJSPInstance,
    Job,
    Operation,
    MachineOption,
    create_toy_instance,
)
from src.data.loader import (
    parse_brandimarte_line,
    parse_fjsplib_text,
    load_benchmark_instance,
    load_benchmark_file,
    TOY_INSTANCES,
)


class TestFJSPInstance:

    def test_create_toy_instance_has_correct_counts(self):
        instance = create_toy_instance()
        assert instance.num_jobs == 3
        assert instance.num_machines == 3
        assert instance.total_ops == 7

    def test_create_toy_instance_from_jobs_array(self):
        jobs = [
            [[(0, 5)], [(1, 10)]],
            [[(0, 7)]],
        ]
        instance = FJSPInstance.from_jobs_array(jobs)
        assert instance.num_jobs == 2
        assert instance.num_machines == 2
        assert instance.total_ops == 3

    def test_get_processing_time(self):
        instance = create_toy_instance()
        pt = instance.get_processing_time(job_id=0, op_id=0, machine_id=0)
        assert pt == 3

    def test_get_processing_time_invalid_machine(self):
        instance = create_toy_instance()
        with pytest.raises(ValueError):
            instance.get_processing_time(job_id=0, op_id=0, machine_id=99)

    def test_is_machine_eligible(self):
        instance = create_toy_instance()
        assert instance.is_machine_eligible(0, 0, 0) is True
        assert instance.is_machine_eligible(0, 0, 1) is True
        assert instance.is_machine_eligible(0, 0, 2) is False

    def test_operation_frozen(self):
        op = Operation(op_id=0, machine_options=((0, 3), (1, 5)))
        assert op.op_id == 0
        assert op.machine_options == ((0, 3), (1, 5))

    def test_job_num_ops(self):
        job = Job(job_id=0, operations=(
            Operation(op_id=0, machine_options=((0, 3),)),
            Operation(op_id=1, machine_options=((1, 5),)),
        ))
        assert job.num_ops == 2


class TestLoader:

    def test_parse_brandimarte_line(self):
        line = "3 3 2.0  2 2 0 3 1 5 2 1 4 2 6  2 2 0 2 2 4 1 1 3  3 1 0 5 2 1 3 2 2 2 0 1 1 2"
        jobs, num_machines, mean = parse_brandimarte_line(line)
        assert num_machines == 3
        assert len(jobs) == 3
        assert len(jobs[0]) == 2
        assert len(jobs[2]) == 3

    def test_load_toy_benchmark(self):
        text = TOY_INSTANCES["toy_3x3"]
        instance = load_benchmark_instance(text)
        assert instance.num_jobs == 3
        assert instance.num_machines == 3
        assert instance.total_ops == 7

    def test_parse_fjsplib_text_with_comments(self):
        text = """
        # tiny 0-based FJSP instance
        2 2 1.5
        1 2 0 3 1 5
        1 1 1 4
        """
        parsed = parse_fjsplib_text(text)
        assert parsed.num_jobs == 2
        assert parsed.num_machines == 2
        assert parsed.mean_machines_per_op == 1.5
        assert parsed.jobs == [[[(0, 3), (1, 5)]], [[(1, 4)]]]

    def test_parse_one_based_machine_ids_are_normalized(self):
        text = "2 2 1.5 1 2 1 3 2 5 1 1 2 4"
        instance = load_benchmark_instance(text)
        assert instance.is_machine_eligible(0, 0, 0)
        assert instance.is_machine_eligible(0, 0, 1)
        assert instance.is_machine_eligible(1, 0, 1)
        assert instance.get_processing_time(1, 0, 1) == 4

    def test_parse_rejects_trailing_tokens(self):
        text = "1 1 1.0 1 1 0 3 999"
        with pytest.raises(ValueError, match="Unexpected trailing tokens"):
            load_benchmark_instance(text, machine_index_base=0)

    def test_parse_rejects_incomplete_machine_option(self):
        text = "1 1 1.0 1 1 0"
        with pytest.raises(ValueError, match="Incomplete machine option"):
            load_benchmark_instance(text, machine_index_base=0)

    def test_parse_rejects_non_positive_processing_time(self):
        text = "1 1 1.0 1 1 0 0"
        with pytest.raises(ValueError, match="Processing time must be positive"):
            load_benchmark_instance(text, machine_index_base=0)

    def test_load_benchmark_file(self, tmp_path):
        path = tmp_path / "tiny.fjs"
        path.write_text("1 1 1.0\n1 1 0 3\n", encoding="utf-8")
        instance = load_benchmark_file(path, machine_index_base=0)
        assert instance.num_jobs == 1
        assert instance.num_machines == 1
        assert instance.total_ops == 1
