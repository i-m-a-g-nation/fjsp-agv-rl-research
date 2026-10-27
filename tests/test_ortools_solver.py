import math

import pytest
from ortools.sat.python import cp_model

from src.data.instance import create_toy_instance, FJSPInstance
from src.scheduling.feasibility import check_feasibility
from src.scheduling.encoding import ScheduleResult
from src.solvers.ortools_solver import ortools_solve, OrtoolsSolverError


@pytest.mark.parametrize(
    "time_limit", [True, False, 0, -1, math.nan, math.inf, -math.inf, "1", None, 1j, 10**400]
)
def test_rejects_invalid_time_limit(time_limit):
    instance = FJSPInstance.from_jobs_array([[[(0, 1)]]])
    with pytest.raises(ValueError, match="time_limit"):
        ortools_solve(instance, time_limit=time_limit)


@pytest.mark.parametrize("num_workers", [True, False, -1, 1.5, 1.0, "1", None, 2**40])
def test_rejects_invalid_worker_count(num_workers):
    instance = FJSPInstance.from_jobs_array([[[(0, 1)]]])
    with pytest.raises(ValueError, match="num_workers"):
        ortools_solve(instance, num_workers=num_workers)


@pytest.mark.parametrize("seed", [True, False, -1, 1.5, 1.0, "42", None, 2**31])
def test_rejects_invalid_seed(seed):
    instance = FJSPInstance.from_jobs_array([[[(0, 1)]]])
    with pytest.raises(ValueError, match="seed"):
        ortools_solve(instance, seed=seed)


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, {"time_limit": 60.0, "num_workers": 1, "seed": 42}),
        ({"time_limit": 2, "num_workers": 0, "seed": 0},
         {"time_limit": 2.0, "num_workers": 0, "seed": 0}),
        ({"time_limit": 3.5, "num_workers": 2, "seed": 2**31 - 1},
         {"time_limit": 3.5, "num_workers": 2, "seed": 2**31 - 1}),
    ],
)
def test_records_configuration_actually_passed_to_solver(monkeypatch, kwargs, expected):
    # Observe the real solver boundary; all solving and extraction remain real.
    observed = []
    real_solver = cp_model.CpSolver

    class ObservedSolver(real_solver):
        def Solve(self, model):
            observed.append({
                "time_limit": self.parameters.max_time_in_seconds,
                "num_workers": self.parameters.num_search_workers,
                "seed": self.parameters.random_seed,
            })
            return super().Solve(model)

    monkeypatch.setattr(cp_model, "CpSolver", ObservedSolver)
    instance = FJSPInstance.from_jobs_array([[[(0, 2), (1, 1)]]])
    result = ortools_solve(instance, **kwargs)
    assert observed == [expected]
    assert result.solver_config == expected
    assert type(result.solver_config["time_limit"]) is float
    assert result.makespan == 1


@pytest.mark.parametrize("duration", [2**61, 2**62, 2**63, 10**100])
def test_unsupported_integer_horizon_is_clear_input_error(duration):
    instance = FJSPInstance.from_jobs_array([[[(0, duration)]]])
    with pytest.raises(ValueError, match="(?i)(horizon|overflow|integer range)"):
        ortools_solve(instance)


def test_aggregate_domain_overflow_is_clear_input_error():
    # Each individual time fits, but the model's combined domains do not.
    instance = FJSPInstance.from_jobs_array([
        [[(0, 2**58), (1, 2**58)]],
        [[(0, 2**58), (1, 2**58)]],
        [[(0, 2**58), (1, 2**58)]],
    ])
    with pytest.raises(ValueError, match="(?i)(horizon|overflow|integer range)"):
        ortools_solve(instance)


def test_revalidates_instance_at_solver_entry():
    instance = FJSPInstance.from_jobs_array([[[(0, 1)]]])
    # Bypass even frozen dataclass protection to exercise the public boundary.
    object.__setattr__(instance, "num_jobs", 9)
    with pytest.raises(ValueError):
        ortools_solve(instance)


def test_solver_validation_is_bound_to_original_instance(monkeypatch):
    import src.solvers.ortools_solver as solver_module

    original = FJSPInstance.from_jobs_array([[[(0, 2)]]])
    replacement = FJSPInstance.from_jobs_array([[[(0, 2)]]], num_machines=2)
    real_checker = check_feasibility

    def substitute_instance_before_check(result, *, expected_instance=None):
        result.instance = replacement
        return real_checker(result, expected_instance=expected_instance)

    monkeypatch.setattr(solver_module, "check_feasibility", substitute_instance_before_check)
    with pytest.raises(OrtoolsSolverError, match="infeasible"):
        ortools_solve(original)


def test_default_single_worker_reproduces_records():
    instance = create_toy_instance()
    first = ortools_solve(instance)
    second = ortools_solve(instance)
    assert first.records == second.records
    assert first.solver_config == second.solver_config == {
        "time_limit": 60.0, "num_workers": 1, "seed": 42,
    }


class TestOrtoolsSolver:

    def test_solve_toy_instance_returns_valid_schedule(self):
        instance = create_toy_instance()
        result = ortools_solve(instance, time_limit=30.0)
        feasible, violations = check_feasibility(result)
        assert feasible, f"Violations: {violations}"
        assert result.makespan > 0
        assert len(result.records) == instance.total_ops

    def test_solve_toy_instance_makespan_positive(self):
        instance = create_toy_instance()
        result = ortools_solve(instance, time_limit=30.0)
        assert result.makespan > 0

    def test_solve_toy_instance_all_ops_scheduled(self):
        instance = create_toy_instance()
        result = ortools_solve(instance, time_limit=30.0)
        scheduled = set((r.job_id, r.op_id) for r in result.records)
        expected = set()
        for j in range(instance.num_jobs):
            for o in range(instance.jobs[j].num_ops):
                expected.add((j, o))
        assert scheduled == expected

    def test_solve_toy_instance_no_overlap_on_machines(self):
        instance = create_toy_instance()
        result = ortools_solve(instance, time_limit=30.0)
        for m_id in range(instance.num_machines):
            ops = [r for r in result.records if r.machine_id == m_id]
            ops.sort(key=lambda r: r.start)
            for i in range(len(ops) - 1):
                assert ops[i].end <= ops[i + 1].start, \
                    f"Machine {m_id}: overlap between J{ops[i].job_id}O{ops[i].op_id} and J{ops[i+1].job_id}O{ops[i+1].op_id}"

    def test_solve_toy_instance_precedence_respected(self):
        instance = create_toy_instance()
        result = ortools_solve(instance, time_limit=30.0)
        for j_id in range(instance.num_jobs):
            job_ops = sorted(
                [r for r in result.records if r.job_id == j_id],
                key=lambda r: r.op_id,
            )
            for i in range(len(job_ops) - 1):
                assert job_ops[i].end <= job_ops[i + 1].start, \
                    f"Job {j_id}: precedence violation O{job_ops[i].op_id} -> O{job_ops[i+1].op_id}"

    def test_toy_instance_optimal_or_feasible(self):
        instance = create_toy_instance()
        result = ortools_solve(instance, time_limit=60.0)
        assert result.makespan >= 1
        assert result.makespan <= 50

    def test_solver_status_set(self):
        instance = create_toy_instance()
        result = ortools_solve(instance, time_limit=30.0)
        assert result.solver_status in ("OPTIMAL", "FEASIBLE"), \
            f"Expected OPTIMAL or FEASIBLE, got {result.solver_status}"

    def test_solver_metadata_set(self):
        instance = create_toy_instance()
        result = ortools_solve(instance, time_limit=30.0)
        assert result.solver_objective_bound is not None
        assert result.solver_objective_bound <= result.makespan
        assert result.solver_gap is not None
        assert result.solver_gap >= 0
        assert result.solver_wall_time is not None
        assert result.solver_wall_time >= 0

    def test_solver_status_feasible_after_check(self):
        instance = create_toy_instance()
        result = ortools_solve(instance, time_limit=30.0)
        feasible, _ = check_feasibility(result)
        assert feasible
        assert result.solver_status in ("OPTIMAL", "FEASIBLE")

    def test_end_equals_start_plus_pt(self):
        instance = create_toy_instance()
        result = ortools_solve(instance, time_limit=30.0)
        for rec in result.records:
            assert rec.end == rec.start + rec.processing_time, \
                f"Job {rec.job_id} Op {rec.op_id}: end={rec.end} != start={rec.start} + pt={rec.processing_time}"

    def test_single_job_single_op(self):
        jobs = [[[(0, 5)]]]
        instance = FJSPInstance.from_jobs_array(jobs)
        result = ortools_solve(instance, time_limit=10.0)
        feasible, _ = check_feasibility(result)
        assert feasible
        assert result.makespan == 5

    def test_single_job_multiple_ops(self):
        jobs = [[[(0, 2)], [(0, 3)], [(0, 4)]]]
        instance = FJSPInstance.from_jobs_array(jobs, num_machines=1)
        result = ortools_solve(instance, time_limit=30.0)
        feasible, _ = check_feasibility(result)
        assert feasible
        assert len(result.records) == 3
        assert result.makespan == 9

    def test_two_parallel_jobs(self):
        jobs = [
            [[(0, 5)], [(1, 3)]],
            [[(0, 3)], [(1, 5)]],
        ]
        instance = FJSPInstance.from_jobs_array(jobs, num_machines=2)
        result = ortools_solve(instance, time_limit=30.0)
        feasible, _ = check_feasibility(result)
        assert feasible

    def test_time_limit_short_returns_result(self):
        instance = create_toy_instance()
        result = ortools_solve(instance, time_limit=0.5)
        feasible, _ = check_feasibility(result)
        assert feasible
        assert result.makespan > 0


class TestSolverStatusDoesNotBreakHeuristics:

    def test_heuristic_result_has_no_solver_status_by_default(self):
        from src.data.instance import create_toy_instance as toy
        from src.scheduling.encoding import ScheduleResult
        result = ScheduleResult(instance=toy())
        assert result.solver_status is None
        assert result.solver_objective_bound is None
        assert result.solver_gap is None
        assert result.solver_wall_time is None

    def test_fifo_result_has_status_none(self):
        from src.data.instance import create_toy_instance as toy
        from src.solvers.heuristics import fifo_solve
        result = fifo_solve(toy())
        assert result.solver_status is None

    def test_spt_result_has_status_none(self):
        from src.data.instance import create_toy_instance as toy
        from src.solvers.heuristics import spt_solve
        result = spt_solve(toy())
        assert result.solver_status is None
