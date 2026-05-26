# Experiments

This directory contains Phase 1 experiment scripts and tracked outputs.

## `exp_001_toy_instance.py`

Runs heuristic baselines on the toy 3 jobs x 3 machines FJSP instance.

Algorithms:

- FIFO
- SPT
- EarliestFinishTime
- Random with seeds 42, 123, and 999

Run:

```powershell
.\.conda-env\python.exe experiments\exp_001_toy_instance.py
```

Expected output:

| Algorithm | Makespan |
|---|---:|
| FIFO | 14 |
| SPT | 13 |
| EarliestFinishTime | 13 |
| Random(s=42) | 14 |
| Random(s=123) | 14 |
| Random(s=999) | 20 |

Artifacts:

- `exp_001_gantt_latest.png`: fixed Gantt output, overwritten on each run
- `exp_001_gantt_*.png`: historical Gantt outputs retained for traceability
- `results/exp_001_toy_instance.csv`: normalized experiment records

Exit code: `0` when all schedules pass feasibility checking, `1` otherwise.

## `exp_002_solver_check.py`

Compares heuristic baselines with the OR-Tools CP-SAT baseline on the same toy instance.

Run:

```powershell
.\.conda-env\python.exe experiments\exp_002_solver_check.py
```

Expected output:

| Algorithm | Makespan | Note |
|---|---:|---|
| FIFO | 14 | HEURISTIC |
| SPT | 13 | HEURISTIC |
| EarliestFinishTime | 13 | HEURISTIC |
| Random(42) | 14 | HEURISTIC |
| CP-SAT(tl=30s) | 11 | CP-SAT optimal |

If CP-SAT returns `FEASIBLE` rather than `OPTIMAL`, the experiment reports it as a feasible reference solution, not as an optimum.

CSV artifact:

- `results/exp_002_solver_check.csv`

Exit code: `0` when all algorithms pass feasibility checking and no solver errors occur, `1` otherwise.

## `exp_003_dispatching_rules.py`

Runs the strict dispatching-rule variants on the same toy instance.

Algorithms:

- DispatchFIFO: choose the earliest ready operation, then choose its earliest-finish eligible machine
- DispatchSPT: choose the ready operation-machine pair with the shortest processing time
- DispatchEFT: choose the ready operation-machine pair with the earliest finish time
- DispatchMWKR: choose the ready job with most remaining route work, then choose its earliest-finish eligible machine
- DispatchRandom(42): choose a ready operation-machine pair with a reproducible random seed

Run:

```powershell
.\.conda-env\python.exe experiments\exp_003_dispatching_rules.py
```

Expected output:

| Algorithm | Feasible |
|---|---|
| DispatchFIFO | PASS |
| DispatchSPT | PASS |
| DispatchEFT | PASS |
| DispatchMWKR | PASS |
| DispatchRandom(42) | PASS |

CSV artifact:

- `results/exp_003_dispatching_rules.csv`

Exit code: `0` when all strict dispatching rules pass feasibility checking, `1` otherwise.

## `exp_004_benchmark_smoke.py`

Loads small benchmark-format instances from `instances/` and runs selected
simple baselines, strict dispatching rules, and CP-SAT.

Input files:

- `instances/toy_3x3_0based.fjs`
- `instances/tiny_2x2_1based.fjs`

Run:

```powershell
.\.conda-env\python.exe experiments\exp_004_benchmark_smoke.py
```

Expected behavior:

- both files load successfully
- 1-based machine ids are normalized to 0-based ids
- every algorithm result passes `check_feasibility()`
- CP-SAT reports `OPTIMAL` or `FEASIBLE` through `ScheduleResult.solver_status`

CSV artifact:

- `results/exp_004_benchmark_smoke.csv`

Exit code: `0` when all benchmark smoke schedules pass feasibility checking, `1` otherwise.

## General Requirements

- Every experiment result must pass `check_feasibility()`.
- Infeasible schedules must not be reported as valid schedules.
- Feasibility constraints must not be weakened to make tests pass.
