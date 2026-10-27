"""Tiny independent disjunctive-graph oracle for the static CP-SAT model."""

from copy import deepcopy
from itertools import permutations, product
import random

import pytest

from src.data.instance import FJSPInstance
from src.scheduling.feasibility import check_feasibility
from src.solvers.ortools_solver import ortools_solve


def exhaustive_makespan(jobs):
    """Enumerate machine choices and *all* orders on each chosen machine.

    A feasible schedule induces these machine orders. For each acyclic graph,
    longest-path completion times give its earliest schedule, so the minimum
    across all graphs is exact. No project decoder, heuristic, or solver is
    used here; the oracle consumes only the original nested array.
    """
    operations = [(j, o) for j, job in enumerate(jobs) for o in range(len(job))]
    best = None
    for choices in product(*(jobs[j][o] for j, o in operations)):
        assignment = dict(zip(operations, choices))
        machine_ops = {}
        for operation, (machine, _) in assignment.items():
            machine_ops.setdefault(machine, []).append(operation)
        for orders in product(*(permutations(group) for group in machine_ops.values())):
            predecessors = {
                (j, o): {(j, o - 1)} if o else set()
                for j, o in operations
            }
            for order in orders:
                for left, right in zip(order, order[1:]):
                    predecessors[right].add(left)

            completion = {}
            pending = set(operations)
            while pending:
                ready = [op for op in pending if predecessors[op] <= completion.keys()]
                if not ready:
                    break  # Cyclic machine/job order: no feasible schedule.
                for op in ready:
                    completion[op] = max(
                        (completion[pred] for pred in predecessors[op]), default=0
                    ) + assignment[op][1]
                    pending.remove(op)
            if not pending:
                makespan = max(completion.values())
                best = makespan if best is None else min(best, makespan)
    assert best is not None
    return best


def assert_proven_optimum(jobs, expected, num_machines=None):
    instance = FJSPInstance.from_jobs_array(jobs, num_machines=num_machines)
    result = ortools_solve(instance, time_limit=5.0)
    assert result.solver_status == "OPTIMAL"
    assert result.makespan == expected
    assert result.solver_objective_bound == expected
    assert result.solver_gap == 0.0
    feasible, violations = check_feasibility(result, expected_instance=instance)
    assert feasible, violations
    # Check the extracted assignment against raw data independently as well.
    records = {(r.job_id, r.op_id): r for r in result.records}
    assert len(records) == len(result.records) == sum(map(len, jobs))
    for j, job in enumerate(jobs):
        for o, options in enumerate(job):
            record = records[j, o]
            assert (record.machine_id, record.processing_time) in options
            assert record.start >= 0
            assert record.end == record.start + record.processing_time
            if o:
                assert records[j, o - 1].end <= record.start
    for left, right in permutations(result.records, 2):
        if left.machine_id == right.machine_id:
            assert left.end <= right.start or right.end <= left.start
    assert result.makespan == max(record.end for record in result.records)
    return result


@pytest.mark.parametrize(
    ("jobs", "expected"),
    [
        ([[[(0, 5)]]], 5),
        ([[[(0, 3), (1, 1)], [(0, 2), (1, 4)]]], 3),
        ([[[(0, 2)], [(1, 3)]], [[(1, 4)], [(0, 1)]]], 7),
        ([[[(0, 5)]], [[(1, 3)]]], 5),
        ([[[(0, 3), (1, 2)]], [[(0, 3), (1, 2)]]], 3),
    ],
)
def test_hand_checked_optima_agree_with_oracle_and_solver(jobs, expected):
    assert exhaustive_makespan(jobs) == expected
    assert_proven_optimum(jobs, expected)


def seeded_jobs(seed):
    rng = random.Random(seed)
    # Different job lengths, routing choices, ties, and machine counts while
    # retaining at most four operations to keep exhaustive enumeration tiny.
    num_machines = 2 + seed % 2
    lengths = (2, 2) if seed % 3 else (1, 2, 1)
    jobs = [
        [
            [(machine, rng.randint(1, 6)) for machine in
             rng.sample(range(num_machines), rng.randint(1, num_machines))]
            for _ in range(length)
        ]
        for length in lengths
    ]
    return jobs, num_machines


@pytest.mark.parametrize("seed", range(12))
def test_seeded_tiny_instances_match_exhaustive_optimum(seed):
    jobs, num_machines = seeded_jobs(seed)
    assert_proven_optimum(jobs, exhaustive_makespan(jobs), num_machines)


@pytest.mark.parametrize("seed", [1, 4, 9])
def test_scaling_and_renaming_preserve_expected_optimum(seed):
    jobs, num_machines = seeded_jobs(seed)
    optimum = exhaustive_makespan(jobs)
    scaled = [[[(m, p * 3) for m, p in op] for op in job] for job in jobs]
    assert exhaustive_makespan(scaled) == optimum * 3
    assert_proven_optimum(scaled, optimum * 3, num_machines)

    # Job order, option order, and machine labels have no scheduling meaning.
    renamed = [
        [[((m + 1) % num_machines, p) for m, p in reversed(op)] for op in job]
        for job in reversed(jobs)
    ]
    assert exhaustive_makespan(renamed) == optimum
    assert_proven_optimum(renamed, optimum, num_machines)


def test_translating_schedule_preserves_legality_but_increases_makespan():
    jobs, num_machines = seeded_jobs(7)
    optimum = exhaustive_makespan(jobs)
    result = assert_proven_optimum(jobs, optimum, num_machines)
    translated = deepcopy(result)
    for record in translated.records:
        record.start += 11
        record.end += 11
    translated.makespan += 11
    # This is a feasible translated plan, no longer the optimal solver output.
    translated.solver_status = None
    translated.solver_objective_bound = None
    translated.solver_gap = None
    assert translated.makespan == optimum + 11
    assert check_feasibility(translated, expected_instance=result.instance) == (True, [])
