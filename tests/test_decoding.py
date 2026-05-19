from src.data.instance import create_toy_instance
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
        instance = create_toy_instance()
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
