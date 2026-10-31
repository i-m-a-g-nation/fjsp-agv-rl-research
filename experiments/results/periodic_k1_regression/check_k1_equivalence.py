"""Compare the restructured fjsp_lab package with the pre-restructure code on identical inputs.

OLD_ROOT holds ``src/``, ``instances/`` and the exp_036 checkpoints of branch
archive/pre-restructure-2026-10-31, e.g.

    git archive archive/pre-restructure-2026-10-31 src instances         experiments/results/exp_036_scoring_policy_v1/checkpoints | tar -x -C OLD_ROOT

Usage (project environment): python check_equivalence.py OLD_ROOT NEW_ROOT
"""
import sys
from dataclasses import asdict
from pathlib import Path

OLD, NEW = Path(sys.argv[1]), Path(sys.argv[2])
sys.path[:0] = [str(OLD), str(NEW / 'src')]

import numpy as np

failures = []


def to_new(action, data):
    """Old fixed layout (job * 4 + machine, 96 + machine) -> size-dependent layout."""
    n, m = len(data.tasks), data.num_machines
    if action >= 96:
        return n * m + action - 96
    job, machine = divmod(action, 4)
    return job * m + machine


def check(name, ok, detail=''):
    print(('OK   ' if ok else 'FAIL ') + name + (f'  {detail}' if detail else ''), flush=True)
    if not ok:
        failures.append(name)


def plan(result):
    return (result.total_tardiness, sorted((r.job_id, r.machine_id, r.start, r.end) for r in result.records),
            sorted((r.machine_id, r.start, r.end) for r in result.maintenance_records))


# ---- maintenance: instances -------------------------------------------------
from src.graduation.reference_main_protocol import build_main_cases
from src.graduation.reference_main_results import _data
from src.graduation.scoring_training import make_instances
from fjsp_lab.maintenance import generator

old_cases, new_cases = build_main_cases(), generator.g3a_cases()
check('g3a: 240 cases, same ids/groups/data',
      len(old_cases) == len(new_cases) == 240 and all(
          o['case_id'] == n.case_id and o['group'] == n.group and asdict(_data(o)) == asdict(n.data)
          and o['factors']['fixed_policy'] == n.fixed_policy for o, n in zip(old_cases, new_cases)))
splits = {'train': ((10000, 12000), 1, False), 'validation': ((20000, 20200), 2, False),
          'test': ((30000, 30600), 3, True), 'teacher_train': ((100000, 120000), 11, False)}
sampled = {}
for name, (seeds, sampler, balanced) in splits.items():
    limit = 600 if name in ('train', 'teacher_train') else None
    old = make_instances(range(*seeds), sampler_seed=sampler, balanced=balanced)[:limit]
    new = generator.split_instances(name)[:limit]
    check(f'split {name}: same instances, modes and factors', len(old) == len(new) and all(
        asdict(o.data) == asdict(n.data) and (o.mode, o.num_tasks, o.num_machines, o.alpha_percent, o.beta_percent,
                                              o.tau_percent, o.seed) ==
        (n.mode, n.num_tasks, n.num_machines, n.alpha_percent, n.beta_percent, n.tau_percent, n.seed)
        for o, n in zip(old, new)), f'{len(new)} instances')
    sampled[name] = list(zip(old, new))

problems = [(_data(o), n.data, mode) for o, n in zip(old_cases, new_cases) for mode in ('fixed', 'joint')]
problems += [(o.data, n.data, n.mode) for o, n in sampled['validation'] + sampled['test']]

# ---- rules --------------------------------------------------------------------
from src.graduation import dispatch_rules as old_rules
from fjsp_lab.maintenance import rules as new_rules
same = all(plan(old_rules.solve_dispatch_rule(od, mode=mode, rule=rule, atc_k=k))
           == plan(new_rules.solve_dispatch_rule(nd, mode=mode, rule=rule, atc_k=k))
           for od, nd, mode in problems for rule, k in old_rules.RULE_PORTFOLIO)
check('dispatch rules: 9-rule portfolio, identical plans', same, f'{len(problems)} problems')

# ---- features -----------------------------------------------------------------
from src.graduation.action_features import action_candidates as old_features
from src.graduation.rl_environment import ParallelMaintenanceEnv as OldEnv
from fjsp_lab.maintenance.features import action_candidates as new_features
from fjsp_lab.maintenance.env import ParallelMaintenanceEnv as NewEnv
rng = np.random.default_rng(0)
same = True
for od, nd, mode in problems[::7]:
    old_env, new_env = OldEnv(od, mode=mode), NewEnv(nd, mode=mode)
    for _ in range(len(od.tasks) + od.num_machines):
        (ol, of), (nl, nf) = old_features(old_env), new_features(new_env)
        if [to_new(a, nd) for a in ol] != nl or not np.array_equal(of, nf):
            same = False
            break
        index = int(rng.integers(len(ol)))
        old_env.step(ol[index])
        step = new_env.step(nl[index])
    same = same and step.terminated
check('env + features: identical legal actions and feature rows on random trajectories', same)

# ---- scoring policy (archived exp_036 checkpoints) -----------------------------
from src.graduation.scoring_policy import ScoringPolicy as OldPolicy, best_of_rollouts as old_best
from fjsp_lab.maintenance.scoring_policy import ScoringPolicy as NewPolicy, best_of_rollouts as new_best
checkpoint = OLD / 'experiments/results/exp_036_scoring_policy_v1/checkpoints/policy_s0.npz'
op, np_ = OldPolicy.load(checkpoint), NewPolicy.load(checkpoint)
same = all(plan(old_best(op, od, mode=mode, samples=8, seed=3)) == plan(new_best(np_, nd, mode=mode, samples=8, seed=3))
           for od, nd, mode in problems[::3])
check('scoring policy s0: identical greedy+8-sample plans', same)

# ---- scoring policy training (short run) ---------------------------------------
from src.graduation.scoring_training import train as old_train
from fjsp_lab.maintenance.scoring_policy import train as new_train
tr = sampled['train'][:40]
va = sampled['validation'][:20]
a, ha = old_train([o for o, _ in tr], [o for o, _ in va], seed=0, bc_epochs=2, rl_epochs=1)
b, hb = new_train([n for _, n in tr], [n for _, n in va], seed=0, bc_epochs=2, rl_epochs=1)
check('scoring policy training: identical history and weights',
      ha == hb and all(np.array_equal(x, y) for x, y in zip(a.state_dict().values(), b.state_dict().values())))

# ---- metaheuristics ------------------------------------------------------------
from src.graduation.metaheuristics import solve_metaheuristic as old_meta
from src.graduation.seeded_search import solve_seeded_iga, plan_to_sequence as old_seq
from fjsp_lab.maintenance.metaheuristics import solve_metaheuristic as new_meta, plan_to_sequence as new_seq
same = True
for od, nd, mode in problems[::5]:
    for algorithm in ('GA', 'SA', 'IGA'):
        o = old_meta(od, mode=mode, algorithm=algorithm, evaluations=1000, seed=1)
        n = new_meta(nd, mode=mode, algorithm=algorithm, evaluations=1000, seed=1)
        same = same and (o.sequence, o.evaluations, o.best_evaluation, plan(o.result)) == \
            (n.sequence, n.evaluations, n.best_evaluation, plan(n.result))
check('GA/SA/IGA: identical sequences, budgets and plans', same)
same = True
for od, nd, mode in problems[::11]:
    seeds_old = [old_seq(old_rules.solve_dispatch_rule(od, mode=mode, rule='MDD'), od)]
    seeds_new = [new_seq(new_rules.solve_dispatch_rule(nd, mode=mode, rule='MDD'), nd)]
    o = solve_seeded_iga(od, mode=mode, seeds=seeds_old, evaluations=800, seed=2)
    n = new_meta(nd, mode=mode, algorithm='IGA', evaluations=800, seed=2, initial_sequences=seeds_new)
    same = same and seeds_old == seeds_new and o.sequence == n.sequence and plan(o.result) == plan(n.result)
check('seeded IGA: identical to initial_sequences', same)

# ---- teacher replay ------------------------------------------------------------
from src.graduation.teacher_data import plan_to_actions
from fjsp_lab.maintenance.env import actions_for_plan
same = all([to_new(a, nd) for a in plan_to_actions(old_meta(od, mode=mode, algorithm='IGA', evaluations=500).result, od, mode)]
           == actions_for_plan(new_meta(nd, mode=mode, algorithm='IGA', evaluations=500).result, nd, mode)
           for od, nd, mode in problems[::13])
check('teacher actions: identical replay sequences', same)

# ---- exact methods -------------------------------------------------------------
from src.graduation.enumeration import enumerate_parallel_maintenance as old_enum
from src.graduation.solver_v2 import solve_parallel_maintenance_v2 as old_cpsat
from fjsp_lab.maintenance.enumeration import enumerate_parallel_maintenance as new_enum
from fjsp_lab.maintenance.cpsat import solve_cpsat
tiny = [generator.build_instance(3, 2, a, b, t, s) for a in (10, 30) for b in (25, 75) for t in (75, 125) for s in (1, 2)]
same = True
from src.graduation.data import MaintenanceRequirement as OR, ParallelMaintenanceInstance as OI, ProductionTask as OT
for data in tiny:
    old_data = OI(tuple(OT(*vars(t).values()) for t in data.tasks), data.num_machines,
                  tuple(OR(*vars(m).values()) for m in data.maintenance))
    for mode in ('fixed', 'joint'):
        o, n = old_enum(old_data, mode=mode), new_enum(data, mode=mode)
        c = solve_cpsat(data, mode=mode, time_limit=10)
        same = same and o.total_tardiness == n.total_tardiness == c.total_tardiness and c.solver_status == 'OPTIMAL'
check('enumeration = old enumeration = CP-SAT optimum on 32 tiny problems', same)
same = True
for od, nd, mode in problems[:160:8]:
    o = old_cpsat(od, mode=mode, time_limit=30, max_deterministic_time=2.0)
    n = solve_cpsat(nd, mode=mode, time_limit=30, max_deterministic_time=2.0)
    same = same and plan(o) == plan(n) and o.solver_status == n.solver_status
check('CP-SAT (deterministic time): identical plans and status', same)

# ---- static FJSP and Phase 2A ---------------------------------------------------
from src.data.loader import load_project_benchmark_file as old_load
from src.solvers import dispatching as old_dispatch
from fjsp_lab.fjsp.benchmark import load_project_benchmark_file as new_load
from fjsp_lab.fjsp.rules import RULES
names = {'FIFO': 'dispatch_fifo_solve', 'SPT': 'dispatch_spt_solve', 'EAM': 'dispatch_eam_solve',
         'EFT': 'dispatch_eft_solve', 'MWKR': 'dispatch_mwkr_solve', 'MOPNR': 'dispatch_mopnr_solve',
         'Random': 'dispatch_random_solve'}
files = sorted((NEW / 'instances/fjsplib').rglob('*.fjs'))
same = True
for path in files:
    oi, ni = old_load(OLD / path.relative_to(NEW)), new_load(path)
    same = same and [[op.machine_options for op in j.operations] for j in oi.jobs] == \
        [[op.machine_options for op in j.operations] for j in ni.jobs]
    for rule, fn in names.items():
        o, n = getattr(old_dispatch, fn)(oi), RULES[rule](ni)
        same = same and [asdict(r) for r in o.records] == [asdict(r) for r in n.records] and o.makespan == n.makespan
check('FJSP: same parsed benchmarks and identical rule schedules', same, f'{len(files)} files x 7 rules')

from src.research.protocol import build_case as old_case
from src.dynamic import reschedule_from_state as old_res
from fjsp_lab.dynamic.perturbation import build_case as new_case
from fjsp_lab.dynamic import reschedule_from_state as new_res
same = True
for rel in ('instances/fjsplib/FattahiMehrabadJolai2007/fattahi1.fjs', 'instances/fjsplib/KacemHammadiBorne2002/kacem1.fjs',
            'instances/fjsplib/Brandimarte1993/mk01.fjs'):
    oi, ni = old_load(OLD / rel), new_load(NEW / rel)
    for event in ('machine_breakdown', 'job_arrival', 'processing_time_change'):
        for seed in (42, 43, 44):
            oc, nc = old_case(oi, event, seed), new_case(ni, event, seed)
            same = same and oc.event_spec == nc.event_spec
            for rule in ('fifo', 'spt', 'eft'):
                o, n = old_res(oc.state, oc.frozen, rule=rule), new_res(nc.state, nc.frozen, rule=rule)
                same = same and [asdict(r) for r in o.records] == [asdict(r) for r in n.records]
check('Phase 2A protocol: same cases and identical rescheduled plans', same, '27 cases x 3 rules')

print('\nFAILED: ' + ', '.join(failures) if failures else '\nALL EQUIVALENT')
sys.exit(1 if failures else 0)
