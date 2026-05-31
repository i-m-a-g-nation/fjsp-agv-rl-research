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
- DispatchMOPNR: choose the ready job with most operations remaining, then choose its earliest-finish eligible machine
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
| DispatchMOPNR | PASS |
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

## `exp_005_benchmark_batch.py`

Recursively discovers benchmark files and runs the Phase 1 static FJSP suite.
Unlike the fixed smoke experiment, this entry point is intended to scale to
tracked benchmark collections with nested directories.

Run:

```powershell
.\.conda-env\python.exe experiments\exp_005_benchmark_batch.py
```

Useful controls:

```powershell
.\.conda-env\python.exe experiments\exp_005_benchmark_batch.py --max-files 10
.\.conda-env\python.exe experiments\exp_005_benchmark_batch.py --skip-cp-sat
.\.conda-env\python.exe experiments\exp_005_benchmark_batch.py --cp-sat-time-limit 30
```

Behavior:

- recursively discovers `*.fjs` files in stable path order
- records loader failures as `LOAD` rows instead of silently dropping files
- runs FIFO, SPT, DispatchFIFO, DispatchSPT, DispatchEFT, DispatchMWKR, and DispatchMOPNR
- runs CP-SAT by default with a configurable per-instance time limit
- writes `results/exp_005_benchmark_batch.csv`

The default batch currently includes the repository-local smoke files and the
tracked FJSPLib subset documented in `instances/README.md`:

| Upstream instance | Size | CP-SAT result | FJSPLib BKS |
|---|---:|---:|---:|
| Fattahi `fattahi1` | 2 x 2 | 66 `OPTIMAL` | 66 |
| Hurink edata `ft06` | 6 x 6 | 55 `OPTIMAL` | 55 |
| Brandimarte `mk01` | 10 x 6 | 40 `OPTIMAL` | 40 |
| Brandimarte `mk03` | 15 x 8 | 204 `FEASIBLE` | 204 |

`mk03` intentionally exercises time-limited solver semantics: matching the
upstream BKS does not become a local optimality proof unless CP-SAT reports
`OPTIMAL`.

Exit code: `0` when all files load and all schedules pass feasibility checking,
`1` when a loader or solver run fails, and `2` for invalid configuration or an
empty discovery result.

## `exp_006_cpsat_time_limit_sweep.py`

Runs tracked Brandimarte `mk03` under several CP-SAT time limits and records
status, objective bound, relative gap, and solver wall time. The sweep defaults
to one worker to reduce parallel-search noise during comparisons.

Run:

```powershell
.\.conda-env\python.exe experiments\exp_006_cpsat_time_limit_sweep.py
```

Useful controls:

```powershell
.\.conda-env\python.exe experiments\exp_006_cpsat_time_limit_sweep.py --time-limits 1 5 30
.\.conda-env\python.exe experiments\exp_006_cpsat_time_limit_sweep.py --num-workers 4
```

Tracked default result:

| Time limit | Makespan | Status | Bound | Relative gap |
|---:|---:|---|---:|---:|
| 1s | 417 | `FEASIBLE` | 20 | 0.952038 |
| 3s | 285 | `FEASIBLE` | 20 | 0.929825 |
| 10s | 220 | `FEASIBLE` | 20 | 0.909091 |

CSV artifact:

- `results/exp_006_cpsat_time_limit_sweep.csv`

Exit code: `0` when every returned schedule passes feasibility checking, `1`
for solver or schedule failures, and `2` for invalid configuration.

## `exp_007_cpsat_worker_sweep.py`

Runs tracked Brandimarte `mk03` with a fixed 10-second time limit and varies the
CP-SAT worker configuration. Worker count `0` means the solver's automatic
configuration.

Run:

```powershell
.\.conda-env\python.exe experiments\exp_007_cpsat_worker_sweep.py
```

Useful controls:

```powershell
.\.conda-env\python.exe experiments\exp_007_cpsat_worker_sweep.py --worker-counts 1 2 4 0
.\.conda-env\python.exe experiments\exp_007_cpsat_worker_sweep.py --time-limit 30
```

Tracked default result:

| Workers | Makespan | Status | Bound | Relative gap |
|---:|---:|---|---:|---:|
| 1 | 220 | `FEASIBLE` | 20 | 0.909091 |
| 2 | 207 | `FEASIBLE` | 20 | 0.903382 |
| 4 | 207 | `FEASIBLE` | 20 | 0.903382 |
| auto | 209 | `FEASIBLE` | 75 | 0.641148 |

CSV artifact:

- `results/exp_007_cpsat_worker_sweep.csv`

Every returned schedule must pass feasibility checking. These values are one
timed observation, not a stable ranking of worker configurations.

## `exp_008_cpsat_worker_repeats.py`

Repeats each tracked `mk03` worker-count configuration under the same
10-second limit. Every raw schedule is independently feasibility checked
before the script reports aggregate statistics.

Run:

```powershell
.\.conda-env\python.exe experiments\exp_008_cpsat_worker_repeats.py
```

Useful controls:

```powershell
.\.conda-env\python.exe experiments\exp_008_cpsat_worker_repeats.py --repeats 5
.\.conda-env\python.exe experiments\exp_008_cpsat_worker_repeats.py --time-limit 30 --worker-counts 1 4 0
```

Tracked default aggregate result:

| Workers | Feasible runs | Best makespan | Mean makespan | Population std. dev. | Best bound | Best gap |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3 / 3 | 220 | 220.000000 | 0.000000 | 20 | 0.909091 |
| 2 | 3 / 3 | 204 | 204.000000 | 0.000000 | 20 | 0.901961 |
| 4 | 3 / 3 | 204 | 204.000000 | 0.000000 | 21 | 0.897059 |
| auto | 3 / 3 | 204 | 204.000000 | 0.000000 | 88 | 0.568627 |

CSV artifacts:

- `results/exp_008_cpsat_worker_repeats_runs.csv`
- `results/exp_008_cpsat_worker_repeats_summary.csv`

All 12 tracked schedules passed feasibility checking. Matching the FJSPLib BKS
does not become a local optimality proof while CP-SAT reports `FEASIBLE`.

## `exp_009_cpsat_benchmark_matrix.py`

Recursively discovers the tracked static FJSPLib subset and runs a controlled
repeated CP-SAT matrix. The defaults compare one worker with the solver's
automatic configuration, repeat each configuration twice, and use a 3-second
per-run limit.

Run:

```powershell
.\.conda-env\python.exe experiments\exp_009_cpsat_benchmark_matrix.py
```

Useful controls:

```powershell
.\.conda-env\python.exe experiments\exp_009_cpsat_benchmark_matrix.py --max-files 2
.\.conda-env\python.exe experiments\exp_009_cpsat_benchmark_matrix.py --repeats 3 --time-limit 10 --worker-counts 1 4 0
```

Tracked default aggregate result:

| Instance | Workers | Feasible runs | Best makespan | Mean makespan | Status | Best bound |
|---|---:|---:|---:|---:|---|---:|
| `mk01` | 1 | 2 / 2 | 40 | 40.000000 | `OPTIMAL` | 40 |
| `mk01` | auto | 2 / 2 | 40 | 40.000000 | `OPTIMAL` | 40 |
| `mk03` | 1 | 2 / 2 | 286 | 286.000000 | `FEASIBLE` | 20 |
| `mk03` | auto | 2 / 2 | 236 | 238.500000 | `FEASIBLE` | 82 |
| `fattahi1` | 1 / auto | 4 / 4 | 66 | 66.000000 | `OPTIMAL` | 66 |
| edata `ft06` | 1 / auto | 4 / 4 | 55 | 55.000000 | `OPTIMAL` | 55 |

CSV artifacts:

- `results/exp_009_cpsat_benchmark_matrix_runs.csv`
- `results/exp_009_cpsat_benchmark_matrix_summary.csv`

All 16 schedules passed feasibility checking. Loader failures and solver
failures remain visible in the raw CSV and process exit code.

## `exp_010_heuristic_benchmark_matrix.py`

Recursively discovers the tracked static FJSPLib subset and evaluates Phase 1
heuristics. Deterministic rules run once per instance. `Random` and
`DispatchRandom` use fixed seeds `42`, `123`, and `999`, so their spread is
reproducible and auditable.

Run:

```powershell
.\.conda-env\python.exe experiments\exp_010_heuristic_benchmark_matrix.py
```

Useful controls:

```powershell
.\.conda-env\python.exe experiments\exp_010_heuristic_benchmark_matrix.py --max-files 2
.\.conda-env\python.exe experiments\exp_010_heuristic_benchmark_matrix.py --seeds 7 42 123
```

Tracked default summary:

| Instance | Best deterministic rule | Makespan | Random range | DispatchRandom range |
|---|---|---:|---:|---:|
| `mk01` | DispatchMWKR | 44 | 148-165 | 92-125 |
| `mk03` | DispatchFIFO / DispatchMWKR | 204 | 1086-1206 | 488-563 |
| `fattahi1` | DispatchMWKR | 66 | 86-135 | 86-135 |
| edata `ft06` | DispatchFIFO | 55 | 146-152 | 71-112 |

CSV artifacts:

- `results/exp_010_heuristic_benchmark_matrix_runs.csv`
- `results/exp_010_heuristic_benchmark_matrix_summary.csv`

All 56 schedules passed feasibility checking. Loader and solver failures remain
visible in the raw CSV and process exit code.

## General Requirements

- Every experiment result must pass `check_feasibility()`.
- Infeasible schedules must not be reported as valid schedules.
- Feasibility constraints must not be weakened to make tests pass.
