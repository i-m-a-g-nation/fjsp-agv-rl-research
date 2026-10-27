import pytest

from src.data.instance import FJSPInstance, create_toy_instance
from src.scheduling.decoding import decode_schedule
from src.scheduling.feasibility import check_feasibility


class TestDecoding:

    def test_decode_simple_assignment(self):
        instance = create_toy_instance()
        assignment = [(0, 0, 0), (0, 1, 1), (1, 0, 0), (1, 1, 1),
                       (2, 0, 0), (2, 1, 2), (2, 2, 1)]
        result = decode_schedule(assignment, instance)
        assert len(result.records) == 7
        assert result.makespan > 0

    def test_decode_preserves_sequence(self):
        instance = FJSPInstance.from_jobs_array([[[(0, 3)], [(1, 4)]]])
        assignment = [(0, 0, 0), (0, 1, 1)]
        result = decode_schedule(assignment, instance)
        recs = sorted(result.records, key=lambda r: r.op_id)
        assert recs[0].start < recs[1].start or recs[0].start == recs[1].start

    def test_decode_all_feasible(self):
        instance = create_toy_instance()
        assignment = [
            (0, 0, 0), (0, 1, 1),
            (1, 0, 0), (1, 1, 1),
            (2, 0, 0), (2, 1, 2), (2, 2, 1),
        ]
        result = decode_schedule(assignment, instance)
        feasible, violations = check_feasibility(result)
        assert feasible, f"Violations: {violations}"


@pytest.mark.parametrize(
    "assignment",
    [[], [(0, 0, 0)], [(0, 0, 0), (0, 0, 0)], [(0, 1, 1), (0, 0, 0)]],
    ids=["empty", "missing", "duplicate", "out_of_order"],
)
def test_decoder_rejects_incomplete_duplicate_or_out_of_order_assignment(assignment):
    instance = FJSPInstance.from_jobs_array([[[(0, 2)], [(1, 3)]]])
    with pytest.raises(ValueError):
        decode_schedule(assignment, instance)


@pytest.mark.parametrize("assignment", [None, {}, "assignment", 42, iter([(0, 0, 0)])])
def test_decoder_rejects_malformed_assignment_container(assignment):
    instance = FJSPInstance.from_jobs_array([[[(0, 3)]]])
    with pytest.raises((TypeError, ValueError)):
        decode_schedule(assignment, instance)


@pytest.mark.parametrize("row", [None, {}, "000", 3, (0, 0), (0, 0, 0, 0)])
def test_decoder_rejects_malformed_assignment_row(row):
    instance = FJSPInstance.from_jobs_array([[[(0, 3)]]])
    with pytest.raises((TypeError, ValueError)):
        decode_schedule([row], instance)


@pytest.mark.parametrize("column", [0, 1, 2])
@pytest.mark.parametrize("bad_id", [True, False, 0.0, "0", None, [], float("nan"), float("inf"), -1, 99])
def test_decoder_rejects_invalid_identifiers(column, bad_id):
    instance = FJSPInstance.from_jobs_array([[[(0, 3)]]])
    row = [0, 0, 0]
    row[column] = bad_id
    with pytest.raises((TypeError, ValueError)):
        decode_schedule([row], instance)


def test_decoder_rejects_ineligible_machine():
    instance = FJSPInstance.from_jobs_array([[[(0, 3)]]], num_machines=2)
    with pytest.raises(ValueError):
        decode_schedule([(0, 0, 1)], instance)


def test_decoder_revalidates_instance_before_building_schedule():
    instance = FJSPInstance.from_jobs_array([[[(0, 3)]]])
    object.__setattr__(instance, "num_jobs", 2)
    with pytest.raises((TypeError, ValueError)):
        decode_schedule([(0, 0, 0)], instance)


def test_decoder_preserves_interleaved_assignment_and_exact_times():
    instance = FJSPInstance.from_jobs_array([[[(0, 2)], [(1, 3)]], [[(1, 2)], [(0, 1)]]])
    assignment = [(0, 0, 0), (1, 0, 1), (1, 1, 0), (0, 1, 1)]
    result = decode_schedule(assignment, instance)
    assert [(r.job_id, r.op_id, r.machine_id, r.start, r.end) for r in result.records] == [
        (0, 0, 0, 0, 2), (1, 0, 1, 0, 2), (1, 1, 0, 2, 3), (0, 1, 1, 2, 5),
    ]
    assert result.makespan == 5
    assert check_feasibility(result) == (True, [])
