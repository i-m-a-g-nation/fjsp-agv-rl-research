"""Every L1 algorithm returns a checker-accepted schedule; deadlocks are reported, not hidden."""

from pathlib import Path

import pytest

from fjsp_lab.fjsp import FJSPInstance, create_toy_instance, load_project_benchmark_file
from fjsp_lab.fjsp.cpsat import solve_cpsat as solve_fjsp
from fjsp_lab.logistics import LogisticsInstance, check_logistics_feasibility
from fjsp_lab.logistics.cpsat import solve_cpsat
from fjsp_lab.logistics.rules import RULES, solve_rule
from fjsp_lab.logistics.simulator import Candidate, LogisticsSimulator, SimulationDeadlock, simulate

MK01 = Path(__file__).resolve().parents[2] / 'instances' / 'fjsplib' / 'Brandimarte1993' / 'mk01.fjs'


def layout(m, scale=3):
    """Line layout: L/U and machines on a line, travel grows with distance."""
    return [[0 if a == b else scale * (1 + abs(a - b)) for b in range(m + 1)] for a in range(m + 1)]


def cases():
    for name, production in (('toy', create_toy_instance()), ('mk01', load_project_benchmark_file(MK01))):
        for buffer in (None, 2):
            for back in (False, True):
                yield name, LogisticsInstance.create(production, layout(production.num_machines), num_vehicles=2,
                                                     buffer_capacity=buffer, return_to_lu=back)


@pytest.mark.parametrize('rule', RULES)
def test_every_rule_returns_an_accepted_schedule(rule):
    for name, data in cases():
        plan = solve_rule(data, rule, seed=3)
        assert check_logistics_feasibility(plan, data) == (True, []), name


def test_rules_are_deterministic():
    _, data = next(cases())
    for rule in RULES:
        assert solve_rule(data, rule, seed=5) == solve_rule(data, rule, seed=5)


def test_tight_buffers_either_schedule_feasibly_or_report_deadlock():
    production = load_project_benchmark_file(MK01)
    for buffer in (0, 1):
        data = LogisticsInstance.create(production, layout(production.num_machines), num_vehicles=2,
                                        buffer_capacity=buffer)
        for rule in RULES:
            try:
                plan = solve_rule(data, rule, seed=1)
            except SimulationDeadlock:
                continue
            assert check_logistics_feasibility(plan, data)[0] is True


def test_crossing_routes_without_buffers_deadlock():
    # Job 0 goes M0 -> M1, job 1 goes M1 -> M0; each blocks the station the other needs.
    production = FJSPInstance.from_jobs_array([[[(0, 2)], [(1, 2)]], [[(1, 2)], [(0, 2)]]], num_machines=2)
    data = LogisticsInstance.create(production, layout(2, 1), num_vehicles=2, buffer_capacity=0)
    for rule in RULES:
        with pytest.raises(SimulationDeadlock):
            solve_rule(data, rule, seed=0)
    # One buffer place breaks the cycle.
    relaxed = LogisticsInstance.create(production, layout(2, 1), num_vehicles=2, buffer_capacity=1)
    assert check_logistics_feasibility(solve_rule(relaxed, 'EFT'), relaxed)[0] is True


def test_staying_on_the_same_machine_needs_no_vehicle():
    production = FJSPInstance.from_jobs_array([[[(0, 2)], [(0, 3), (1, 1)]]], num_machines=2)
    data = LogisticsInstance.create(production, layout(2, 10), num_vehicles=1, return_to_lu=False)
    assert all(c.vehicle is not None for c in LogisticsSimulator(data).candidates())   # at L/U every move needs one

    def prefer_stay(sim, options):
        return min(options, key=lambda c: (c.vehicle is not None, c.machine))
    plan = simulate(data, prefer_stay)
    assert [t.leg for t in plan.transports] == [0]           # only the trip from L/U
    assert plan.makespan == data.travel[data.lu][0] + 2 + 3


def test_simulator_rejects_decisions_it_did_not_offer():
    _, data = next(cases())
    invented = Candidate(0, 0, 0, 0, 0, 0, 1, 0)
    with pytest.raises(ValueError):
        simulate(data, lambda sim, options: invented)


def route_lower_bound(data):
    """Longest job when it alone uses the shop: best machine route incl. trips (independent of CP-SAT)."""
    best = 0
    for job in data.production.jobs:
        cost = {data.lu: 0}
        for op in job.operations:
            cost = {machine: min(c + (0 if here == machine else data.loaded_time(here, machine)) for here, c in cost.items()) + p
                    for machine, p in op.machine_options}
        if data.return_to_lu:
            cost = {data.lu: min(c + data.loaded_time(here, data.lu) for here, c in cost.items())}
        best = max(best, min(cost.values()))
    return best


def test_cpsat_with_free_transport_matches_the_phase1_optimum():
    production = create_toy_instance()
    zero = [[0] * (production.num_machines + 1) for _ in range(production.num_machines + 1)]
    data = LogisticsInstance.create(production, zero, num_vehicles=1, return_to_lu=False)
    plan, reference = solve_cpsat(data, time_limit=20), solve_fjsp(production, time_limit=20)
    assert plan.solver_status == reference.solver_status == 'OPTIMAL'
    assert plan.makespan == reference.makespan


def test_cpsat_optimum_is_bracketed_by_rules_and_bounds():
    production = create_toy_instance()
    optimum = {}
    for back in (False, True):
        for buffer in (None, 1, 0):
            data = LogisticsInstance.create(production, layout(production.num_machines), num_vehicles=2,
                                            buffer_capacity=buffer, return_to_lu=back)
            plan = solve_cpsat(data, time_limit=30)
            assert plan.solver_status == 'OPTIMAL' and check_logistics_feasibility(plan, data)[0] is True
            assert route_lower_bound(data) <= plan.makespan
            for rule in RULES:
                try:
                    assert plan.makespan <= solve_rule(data, rule, seed=1).makespan
                except SimulationDeadlock:
                    pass
            optimum[back, buffer] = plan.makespan
    for back in (False, True):                       # fewer places can only hurt
        assert optimum[back, None] <= optimum[back, 1] <= optimum[back, 0]
    assert all(optimum[False, b] <= optimum[True, b] for b in (None, 1, 0))


def test_cpsat_finds_a_schedule_where_non_delay_rules_deadlock():
    production = FJSPInstance.from_jobs_array([[[(0, 2)], [(1, 2)]], [[(1, 2)], [(0, 2)]]], num_machines=2)
    data = LogisticsInstance.create(production, layout(2, 1), num_vehicles=2, buffer_capacity=0)
    plan = solve_cpsat(data, time_limit=10)
    assert plan.solver_status == 'OPTIMAL' and check_logistics_feasibility(plan, data)[0] is True


EXTERNAL = Path(__file__).resolve().parents[2] / 'instances' / 'external' / 'FJSPT'


@pytest.mark.skipif(not (EXTERNAL / 'Deroussi').is_dir(), reason='FJSPT benchmark files not downloaded (instances/external)')
def test_published_reference_solutions_replay_to_their_reported_makespans():
    """Deroussi & Norre instances under the benchmark conventions (L/U first, no return, no blocking)."""
    from fjsp_lab.logistics import load_fjspt
    from fjsp_lab.logistics.sequences import decode_sequences, parse_reference_solution
    for i in range(1, 11):
        data = load_fjspt(EXTERNAL / 'DeroussiNorre' / f'fjsp{i}.txt', EXTERNAL / 'DeroussiNorre_layout.txt')
        machines, vehicles, reported = parse_reference_solution(
            (EXTERNAL / 'Deroussi' / f'fjsp{i}.txt').read_text(encoding='utf-8'), data)
        assert decode_sequences(data, machines, vehicles).makespan == reported, f'fjsp{i}'


def test_rules_and_cpsat_without_blocking():
    production = create_toy_instance()
    for buffer in (None, 1):
        free = LogisticsInstance.create(production, layout(production.num_machines), num_vehicles=2,
                                        buffer_capacity=buffer, blocking=False)
        blocked = LogisticsInstance.create(production, layout(production.num_machines), num_vehicles=2,
                                           buffer_capacity=buffer)
        for rule in RULES:
            assert check_logistics_feasibility(solve_rule(free, rule, seed=2), free)[0] is True
        relaxed, strict = solve_cpsat(free, time_limit=30), solve_cpsat(blocked, time_limit=30)
        assert relaxed.solver_status == strict.solver_status == 'OPTIMAL'
        assert check_logistics_feasibility(relaxed, free)[0] is True
        assert relaxed.makespan <= strict.makespan                  # blocking can only hurt


def test_fixed_machine_plan_is_kept_and_contradictions_are_proven():
    from fjsp_lab.logistics.cpsat import LogisticsCpSatError
    crossing = FJSPInstance.from_jobs_array([[[(0, 2)], [(1, 2)]], [[(1, 2)], [(0, 2)]]], num_machines=2)
    data = LogisticsInstance.create(crossing, layout(2, 1), num_vehicles=1, buffer_capacity=0)
    # Both jobs first, then each other's machine: with blocking, no buffer and a single vehicle
    # the jobs cannot swap (two vehicles could pick both up at the same instant).
    with pytest.raises(LogisticsCpSatError) as caught:
        solve_cpsat(data, time_limit=10, machine_plan=[[(0, 0), (1, 1)], [(1, 0), (0, 1)]])
    assert caught.value.status == 'INFEASIBLE'
    two = LogisticsInstance.create(crossing, layout(2, 1), num_vehicles=2, buffer_capacity=0)
    assert solve_cpsat(two, time_limit=10, machine_plan=[[(0, 0), (1, 1)], [(1, 0), (0, 1)]]).solver_status == 'OPTIMAL'
    serial = [[(1, 1), (0, 0)], [(1, 0), (0, 1)]]      # job 1 runs M1 then M0 before job 0 starts
    result = solve_cpsat(data, time_limit=10, machine_plan=serial)
    by_machine = {}
    for r in sorted(result.production.records, key=lambda r: r.start):
        by_machine.setdefault(r.machine_id, []).append((r.job_id, r.op_id))
    assert [by_machine[0], by_machine[1]] == serial
    with pytest.raises(ValueError):
        solve_cpsat(data, time_limit=10, machine_plan=[[(0, 0)], [(1, 0), (0, 1)]])


def test_decoupled_never_beats_the_joint_optimum():
    from fjsp_lab.logistics.decoupled import DecoupledPlanInfeasible, solve_decoupled
    production = create_toy_instance()
    for blocking, buffer in ((False, None), (True, None), (True, 0)):
        data = LogisticsInstance.create(production, layout(production.num_machines), num_vehicles=2,
                                        buffer_capacity=buffer, blocking=blocking)
        joint = solve_cpsat(data, time_limit=30)
        assert joint.solver_status == 'OPTIMAL'
        for lags in (False, True):
            try:
                schedule, plan = solve_decoupled(data, transport_lags=lags, time_limit=30)
            except DecoupledPlanInfeasible:
                continue
            assert check_logistics_feasibility(schedule, data)[0] is True
            assert schedule.makespan >= joint.makespan and plan.estimate <= schedule.makespan


def test_decoupling_costs_nothing_when_transport_is_free():
    from fjsp_lab.logistics.decoupled import solve_decoupled
    production = create_toy_instance()
    zero = [[0] * (production.num_machines + 1) for _ in range(production.num_machines + 1)]
    data = LogisticsInstance.create(production, zero, num_vehicles=1, return_to_lu=False)
    schedule, _ = solve_decoupled(data, transport_lags=False, time_limit=30)
    assert schedule.makespan == solve_cpsat(data, time_limit=30).makespan


def test_deadlock_avoidance_finishes_where_plain_rules_deadlock():
    from fjsp_lab.logistics.simulator import is_safe
    crossing = FJSPInstance.from_jobs_array([[[(0, 2)], [(1, 2)]], [[(1, 2)], [(0, 2)]]], num_machines=2)
    data = LogisticsInstance.create(crossing, layout(2, 1), num_vehicles=2, buffer_capacity=0)
    for rule in RULES:
        plan = solve_rule(data, rule, seed=0, avoid_deadlock=True)
        assert check_logistics_feasibility(plan, data)[0] is True
    # After job 0 is sent to M0, also sending job 1 to M1 dooms the system (no swap in the simulator).
    sim = LogisticsSimulator(data)
    first = next(c for c in sim.candidates() if (c.job, c.machine) == (0, 0))
    assert is_safe(sim, first)
    sim.apply(first)
    second = next(c for c in sim.candidates() if (c.job, c.machine) == (1, 1))
    assert not is_safe(sim, second)


def test_deadlock_avoidance_changes_nothing_when_no_deadlock_threatens():
    for name, data in cases():
        for rule in ('EFT', 'MWKR+NV', 'RANDOM'):
            assert solve_rule(data, rule, seed=4, avoid_deadlock=True) == solve_rule(data, rule, seed=4), (name, rule)


def test_deadlock_avoidance_on_tight_buffers():
    production = load_project_benchmark_file(MK01)
    for buffer in (0, 1):
        data = LogisticsInstance.create(production, layout(production.num_machines), num_vehicles=2,
                                        buffer_capacity=buffer)
        for rule in RULES:
            plan = solve_rule(data, rule, seed=1, avoid_deadlock=True)
            assert check_logistics_feasibility(plan, data)[0] is True


def test_clone_is_independent():
    _, data = next(cases())
    sim = LogisticsSimulator(data)
    twin = sim.clone()
    twin.apply(twin.candidates()[0])
    assert sim.transports == [] and sim.vehicle_free == [0] * data.num_vehicles and len(sim.awaiting) == data.num_jobs
