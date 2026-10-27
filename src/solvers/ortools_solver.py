from __future__ import annotations

import math
from numbers import Real
from typing import Tuple

from ortools.sat.python import cp_model

from src.data.instance import FJSPInstance, validate_instance
from src.scheduling.encoding import ScheduleResult
from src.scheduling.feasibility import check_feasibility


class OrtoolsSolverError(Exception):
    """Raised when CP-SAT cannot produce a validated schedule."""

    pass


def _compute_horizon(instance: FJSPInstance) -> int:
    """Compute a conservative time horizon for the CP-SAT model."""

    # Sum of worst eligible processing times is a safe upper bound for all
    # start/end variables because a serial schedule can always fit inside it.
    total = 0
    for job in instance.jobs:
        for op in job.operations:
            total += max(pt for _m, pt in op.machine_options)
    return total


def ortools_solve(
    instance: FJSPInstance,
    time_limit: float = 60.0,
    num_workers: int = 1,
    *,
    seed: int = 42,
) -> ScheduleResult:
    """Solve static FJSP with reproducible single-worker defaults.

    ``num_workers=0`` explicitly requests OR-Tools' automatic worker selection.
    Multiple workers and wall-clock stopping can affect reproducibility.
    """

    validate_instance(instance)
    if isinstance(time_limit, bool) or not isinstance(time_limit, Real):
        raise ValueError("time_limit must be a finite positive real number")
    try:
        time_limit = float(time_limit)
    except (OverflowError, ValueError) as exc:
        raise ValueError("time_limit must be a finite positive real number") from exc
    if not math.isfinite(time_limit) or time_limit <= 0:
        raise ValueError("time_limit must be a finite positive real number")
    # Both OR-Tools parameters are represented by signed 32-bit integers.
    if type(num_workers) is not int or not 0 <= num_workers <= 2**31 - 1:
        raise ValueError("num_workers must be an integer in [0, 2**31 - 1] (0 means auto)")
    if type(seed) is not int or not 0 <= seed <= 2**31 - 1:
        raise ValueError("seed must be an integer in [0, 2**31 - 1]")
    solver_config = {"time_limit": time_limit, "num_workers": num_workers, "seed": seed}

    model = cp_model.CpModel()
    horizon = _compute_horizon(instance)
    # CP-SAT domains are limited to half the signed 64-bit integer range.
    # Its validator below also checks interval arithmetic and aggregate domains.
    if horizon > cp_model.INT_MAX // 2:
        raise ValueError("CP-SAT horizon exceeds its supported integer range")

    start_vars: dict[Tuple[int, int, int], cp_model.IntVar] = {}
    end_vars: dict[Tuple[int, int, int], cp_model.IntVar] = {}
    interval_vars: dict[Tuple[int, int, int], cp_model.IntervalVar] = {}
    presence_vars: dict[Tuple[int, int, int], cp_model.IntVar] = {}

    # Optional intervals represent the machine choice for each operation.
    # If presence is false, the interval is ignored by precedence and NoOverlap.
    for j_id, job in enumerate(instance.jobs):
        for o_id, op in enumerate(job.operations):
            for m_id, pt in op.machine_options:
                suffix = f"j{j_id}_o{o_id}_m{m_id}"
                start = model.NewIntVar(0, horizon, f"start_{suffix}")
                end = model.NewIntVar(0, horizon, f"end_{suffix}")
                presence = model.NewBoolVar(f"presence_{suffix}")
                interval = model.NewOptionalIntervalVar(
                    start, pt, end, presence, f"interval_{suffix}",
                )
                start_vars[(j_id, o_id, m_id)] = start
                end_vars[(j_id, o_id, m_id)] = end
                interval_vars[(j_id, o_id, m_id)] = interval
                presence_vars[(j_id, o_id, m_id)] = presence

    for j_id, job in enumerate(instance.jobs):
        for o_id, op in enumerate(job.operations):
            # Exactly one eligible machine must be selected for every operation.
            machine_presences = [
                presence_vars[(j_id, o_id, m_id)]
                for m_id, _pt in op.machine_options
            ]
            model.AddExactlyOne(machine_presences)

        for o_id in range(job.num_ops - 1):
            # Precedence is conditional because each operation has multiple
            # optional machine intervals, but only one is active in a solution.
            cur_machines = job.operations[o_id].machine_options
            next_machines = job.operations[o_id + 1].machine_options
            for m_cur, _ptc in cur_machines:
                for m_next, _ptn in next_machines:
                    p_cur = presence_vars[(j_id, o_id, m_cur)]
                    p_next = presence_vars[(j_id, o_id + 1, m_next)]
                    end_cur = end_vars[(j_id, o_id, m_cur)]
                    start_next = start_vars[(j_id, o_id + 1, m_next)]
                    model.Add(end_cur <= start_next).OnlyEnforceIf([p_cur, p_next])

    for m_id in range(instance.num_machines):
        # NoOverlap enforces single capacity for each physical machine.
        machine_intervals: list[cp_model.IntervalVar] = []
        for j_id, job in enumerate(instance.jobs):
            for o_id, op in enumerate(job.operations):
                for op_m_id, _pt in op.machine_options:
                    if op_m_id == m_id:
                        machine_intervals.append(
                            interval_vars[(j_id, o_id, m_id)]
                        )
        if machine_intervals:
            model.AddNoOverlap(machine_intervals)

    # Makespan is the maximum completion time of each job's final operation.
    makespan_var = model.NewIntVar(0, horizon, "makespan")
    for j_id, job in enumerate(instance.jobs):
        last_o = job.num_ops - 1
        for m_id, _pt in job.operations[last_o].machine_options:
            model.Add(makespan_var >= end_vars[(j_id, last_o, m_id)]).OnlyEnforceIf(
                presence_vars[(j_id, last_o, m_id)]
            )

    model.Minimize(makespan_var)
    validation_error = model.Validate()
    if validation_error:
        raise ValueError(
            "CP-SAT model exceeds its supported integer range: " + validation_error
        )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = num_workers
    solver.parameters.random_seed = seed
    solver.parameters.log_search_progress = False

    status = solver.Solve(model)
    status_name = solver.StatusName(status)

    # Only OPTIMAL and FEASIBLE contain extractable schedules. Other statuses
    # are treated as errors so callers cannot mistake them for valid results.
    if status == cp_model.INFEASIBLE:
        raise OrtoolsSolverError("CP-SAT returned INFEASIBLE")

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return _extract_result(
            instance,
            solver,
            start_vars,
            end_vars,
            presence_vars,
            status_name,
            solver_config,
        )

    raise OrtoolsSolverError(f"CP-SAT returned unexpected status: {status_name}")


def _extract_result(
    instance: FJSPInstance,
    solver: cp_model.CpSolver,
    start_vars: dict,
    end_vars: dict,
    presence_vars: dict,
    status_name: str,
    solver_config: dict,
) -> ScheduleResult:
    """Extract and validate a ScheduleResult from a CP-SAT solution."""

    solver_status = "OPTIMAL" if status_name == "OPTIMAL" else "FEASIBLE"
    result = ScheduleResult(
        instance=instance,
        solver_status=solver_status,
        solver_objective_bound=float(solver.BestObjectiveBound()),
        solver_wall_time=float(solver.WallTime()),
        solver_config=solver_config,
    )

    # Extract exactly the active interval for each operation and convert it to
    # the common ScheduleResult representation used by all solvers.
    for j_id, job in enumerate(instance.jobs):
        for o_id, op in enumerate(job.operations):
            assigned = False
            for m_id, pt in op.machine_options:
                if solver.Value(presence_vars[(j_id, o_id, m_id)]) == 1:
                    start_val = solver.Value(start_vars[(j_id, o_id, m_id)])
                    end_val = solver.Value(end_vars[(j_id, o_id, m_id)])
                    if end_val != start_val + pt:
                        raise OrtoolsSolverError(
                            f"Job {j_id} Op {o_id} Machine {m_id}: "
                            f"end={end_val} != start={start_val} + pt={pt}"
                        )
                    result.add_record(j_id, o_id, m_id, start=start_val, processing_time=pt)
                    assigned = True
                    break
            if not assigned:
                raise OrtoolsSolverError(
                    f"Job {j_id} Op {o_id}: no machine assigned by solver"
                )

    result.compute_makespan()
    if result.solver_objective_bound is not None and math.isfinite(result.solver_objective_bound):
        gap = (float(result.makespan) - result.solver_objective_bound) / max(1.0, abs(float(result.makespan)))
        result.solver_gap = max(0.0, gap)

    # CP-SAT constraints and the independent feasibility checker should agree.
    # Keeping both checks makes model mistakes visible during development.
    feasible, violations = check_feasibility(result, expected_instance=instance)
    if not feasible:
        raise OrtoolsSolverError(
            f"CP-SAT ({solver_status}) produced infeasible schedule: {violations}"
        )

    return result
