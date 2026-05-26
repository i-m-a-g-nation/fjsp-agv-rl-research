from __future__ import annotations

from typing import Tuple

from ortools.sat.python import cp_model

from src.data.instance import FJSPInstance
from src.scheduling.encoding import ScheduleResult
from src.scheduling.feasibility import check_feasibility


class OrtoolsSolverError(Exception):
    """Raised when CP-SAT cannot produce a validated schedule."""

    pass


def _compute_horizon(instance: FJSPInstance) -> int:
    """Compute a conservative time horizon for the CP-SAT model."""

    total = 0
    for job in instance.jobs:
        for op in job.operations:
            total += max(pt for _m, pt in op.machine_options)
    return total


def ortools_solve(
    instance: FJSPInstance,
    time_limit: float = 60.0,
    num_workers: int = 0,
) -> ScheduleResult:
    """Solve a static FJSP instance with an OR-Tools CP-SAT baseline model."""

    model = cp_model.CpModel()
    horizon = _compute_horizon(instance)

    start_vars: dict[Tuple[int, int, int], cp_model.IntVar] = {}
    end_vars: dict[Tuple[int, int, int], cp_model.IntVar] = {}
    interval_vars: dict[Tuple[int, int, int], cp_model.IntervalVar] = {}
    presence_vars: dict[Tuple[int, int, int], cp_model.IntVar] = {}

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
            machine_presences = [
                presence_vars[(j_id, o_id, m_id)]
                for m_id, _pt in op.machine_options
            ]
            model.AddExactlyOne(machine_presences)

        for o_id in range(job.num_ops - 1):
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

    makespan_var = model.NewIntVar(0, horizon, "makespan")
    for j_id, job in enumerate(instance.jobs):
        last_o = job.num_ops - 1
        for m_id, _pt in job.operations[last_o].machine_options:
            model.Add(makespan_var >= end_vars[(j_id, last_o, m_id)]).OnlyEnforceIf(
                presence_vars[(j_id, last_o, m_id)]
            )

    model.Minimize(makespan_var)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    if num_workers > 0:
        solver.parameters.num_search_workers = num_workers
    solver.parameters.log_search_progress = False

    status = solver.Solve(model)
    status_name = solver.StatusName(status)

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
        )

    raise OrtoolsSolverError(f"CP-SAT returned unexpected status: {status_name}")


def _extract_result(
    instance: FJSPInstance,
    solver: cp_model.CpSolver,
    start_vars: dict,
    end_vars: dict,
    presence_vars: dict,
    status_name: str,
) -> ScheduleResult:
    """Extract and validate a ScheduleResult from a CP-SAT solution."""

    solver_status = "OPTIMAL" if status_name == "OPTIMAL" else "FEASIBLE"
    result = ScheduleResult(instance=instance, solver_status=solver_status)

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

    feasible, violations = check_feasibility(result)
    if not feasible:
        raise OrtoolsSolverError(
            f"CP-SAT ({solver_status}) produced infeasible schedule: {violations}"
        )

    return result
