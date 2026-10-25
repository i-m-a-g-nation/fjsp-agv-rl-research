import pytest

from src.data.instance import FJSPInstance
from src.scheduling.feasibility import check_feasibility


@pytest.mark.parametrize('options', [[(0, 9), (1, 2)], [(1, 2), (0, 9)]])
def test_eam_ties_use_machine_id_and_do_not_alias_earliest_finish(options):
    from src.solvers.dispatching import dispatch_eam_solve, dispatch_eft_solve
    instance = FJSPInstance.from_jobs_array([[options]], num_machines=2)
    eam, eft = dispatch_eam_solve(instance), dispatch_eft_solve(instance)
    assert (eam.records[0].machine_id, eam.makespan) == (0, 9)
    assert (eft.records[0].machine_id, eft.makespan) == (1, 2)
    assert check_feasibility(eam)[0]


def test_eam_chooses_the_earlier_start_even_when_that_machine_finishes_later():
    from src.solvers.dispatching import dispatch_eam_solve
    instance = FJSPInstance.from_jobs_array([[[ (0, 4) ]], [[(0, 1), (1, 8)]]], num_machines=2)
    result = dispatch_eam_solve(instance)
    records = {(r.job_id, r.op_id): r for r in result.records}
    assert (records[(0, 0)].machine_id, records[(0, 0)].start, records[(0, 0)].end) == (0, 0, 4)
    assert (records[(1, 0)].machine_id, records[(1, 0)].start, records[(1, 0)].end) == (1, 0, 8)
    assert check_feasibility(result)[0]


def test_eam_ties_on_feasible_start_after_precedence_use_machine_id():
    from src.solvers.dispatching import dispatch_eam_solve
    instance = FJSPInstance.from_jobs_array([[[(0, 6)], [(1, 3), (0, 1)]]], num_machines=2)
    result = dispatch_eam_solve(instance)
    record = next(r for r in result.records if r.op_id == 1)
    assert (record.machine_id, record.start, record.end) == (0, 6, 7)
    assert check_feasibility(result)[0]


def test_eam_public_facades_return_uniform_legal_schedules():
    from src.solvers import earliest_available_machine_solve
    from src.solvers.heuristics import dispatch_eam_solve
    from src.scheduling.encoding import ScheduleResult
    instance = FJSPInstance.from_jobs_array([[[(0, 3), (1, 1)]]], num_machines=2)
    for solve in (earliest_available_machine_solve, dispatch_eam_solve):
        result = solve(instance)
        assert isinstance(result, ScheduleResult) and result.instance == instance
        assert result.makespan == 3
        assert check_feasibility(result)[0]
