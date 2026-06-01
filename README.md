# FJSP-AGV-RL Research

Chinese version: [README.zh-CN.md](README.zh-CN.md)

Phase 1: a static flexible job shop scheduling (FJSP) research platform.

This repository currently focuses on correctness, reproducibility, and a small verified experimental baseline. AGV scheduling, transportation time, dynamic events, reinforcement learning, and GNN models are intentionally out of scope for Phase 1.

## Scope

- FJSP instance data structures: `FJSPInstance`, jobs, operations, and machine options
- Schedule representation: `ScheduleRecord` and `ScheduleResult`
- Semi-active decoding from `(job_id, op_id, machine_id)` assignments to timed schedules
- Feasibility checker for operation coverage, precedence, machine capacity, machine eligibility, processing times, and makespan consistency
- Heuristic baselines: FIFO, SPT, Earliest Finish Time, and seeded Random
- Strict dispatching-rule variants: DispatchFIFO, DispatchSPT, DispatchEFT, DispatchMWKR, DispatchMOPNR, and DispatchRandom
- Benchmark-format loader smoke tests for small 0-based and 1-based FJSP files
- Provenance-documented FJSPLib subset from Brandimarte, Hurink, Fattahi, and Kacem families
- Normalized CSV experiment result recording under `experiments/results/`
- Shared experiment runner utilities for timing, feasibility validation, failures, and solver metadata
- Recursive benchmark batch experiment with stable discovery order and auditable loader failures
- OR-Tools CP-SAT baseline with optional intervals, exactly-one machine assignment, precedence constraints, and machine `NoOverlap`
- CP-SAT diagnostics: solver status, objective bound, relative gap, and solver wall time
- CP-SAT time-limit sweep on tracked `mk03` with a fixed single worker
- CP-SAT worker-count sweep on tracked `mk03` with a fixed 10-second limit
- Repeated CP-SAT worker-count aggregation with per-run and summary CSV artifacts
- Controlled repeated CP-SAT matrix across the tracked static FJSPLib subset
- Heuristic matrix with deterministic rules and reproducibly seeded random families
- BKS-aware heuristic quality ratios from structured upstream references
- Metadata audit tying tracked FJSPLib files to BKS rows and loader checks
- Matplotlib Gantt chart output using a non-interactive backend
- Toy-instance experiments and pytest coverage

## Repository Layout

```text
src/
  data/          FJSP instance data structures and loaders
  scheduling/    encoding, decoding, and feasibility checking
  solvers/       baselines, dispatching rules, compatibility facade, and CP-SAT
  vis/           Gantt chart rendering
tests/           pytest suite
experiments/     experiment scripts and tracked artifacts
instances/       local smoke files and a tracked real FJSPLib subset
notes/           literature notes and review material
papers/          paper category indexes
scripts/         environment helper scripts
AGENTS.md        project rules and phase boundaries
environment.yml  Conda environment definition
pyproject.toml   Python project metadata
```

## Environment

Create the dedicated Conda environment:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_env.ps1
```

By default the script creates the environment at `.conda-env` inside the project. To use a custom local path, set `FJSP_CONDA_ENV` before running the script.

Do not use the Conda `base` environment for project checks.

## Quick Checks

```powershell
.\.conda-env\python.exe -c "import sys; print(sys.executable)"
.\.conda-env\python.exe experiments\exp_001_toy_instance.py
.\.conda-env\python.exe experiments\exp_002_solver_check.py
.\.conda-env\python.exe experiments\exp_003_dispatching_rules.py
.\.conda-env\python.exe experiments\exp_004_benchmark_smoke.py
.\.conda-env\python.exe experiments\exp_005_benchmark_batch.py
.\.conda-env\python.exe experiments\exp_006_cpsat_time_limit_sweep.py
.\.conda-env\python.exe experiments\exp_007_cpsat_worker_sweep.py
.\.conda-env\python.exe experiments\exp_008_cpsat_worker_repeats.py
.\.conda-env\python.exe experiments\exp_009_cpsat_benchmark_matrix.py
.\.conda-env\python.exe experiments\exp_010_heuristic_benchmark_matrix.py
.\.conda-env\python.exe experiments\exp_011_heuristic_quality_report.py
.\.conda-env\python.exe experiments\exp_012_benchmark_metadata_audit.py
.\.conda-env\python.exe -m pytest
```

If you use `FJSP_CONDA_ENV`, replace `.\.conda-env\python.exe` with the Python executable in that environment.

## Current Toy Results

### Experiment 001: Heuristics

| Algorithm | Makespan | Feasible |
|---|---:|---|
| FIFO | 14 | PASS |
| SPT | 13 | PASS |
| EarliestFinishTime | 13 | PASS |
| Random(s=42) | 14 | PASS |
| Random(s=123) | 14 | PASS |
| Random(s=999) | 20 | PASS |

Best heuristic result on the toy instance: makespan 13.

### Experiment 002: Heuristics vs CP-SAT

| Algorithm | Makespan | Status |
|---|---:|---|
| FIFO | 14 | HEURISTIC |
| SPT | 13 | HEURISTIC |
| EarliestFinishTime | 13 | HEURISTIC |
| Random(42) | 14 | HEURISTIC |
| CP-SAT(tl=30s) | 11 | CP-SAT optimal |

CP-SAT currently proves makespan 11 on the toy instance.

### Experiment 003: Strict Dispatching Rules

| Algorithm | Definition | Feasible |
|---|---|---|
| DispatchFIFO | earliest ready operation, then earliest-finish machine | PASS |
| DispatchSPT | shortest processing-time ready operation-machine pair | PASS |
| DispatchEFT | earliest-finish ready operation-machine pair | PASS |
| DispatchMWKR | most remaining route work, then earliest-finish machine | PASS |
| DispatchMOPNR | most operations remaining, then earliest-finish machine | PASS |
| DispatchRandom(42) | seeded random ready operation-machine pair | PASS |

The original heuristic functions remain as simple baselines. The `dispatch_*`
functions are the stricter dispatching-rule implementations intended for
definition-sensitive comparisons.

On the toy instance, DispatchMWKR and DispatchMOPNR currently produce makespan 12.

### Experiment 004: Benchmark Loader Smoke

Loads small benchmark-format files from `instances/` and runs selected baselines,
strict dispatching rules, and CP-SAT. The included smoke files are intentionally
small so the experiment stays fast and deterministic.

### Experiment 005: Benchmark Batch

Recursively discovers `*.fjs` files under `instances/`, evaluates each static
FJSP instance in stable path order, and records loader failures rather than
silently dropping malformed files. Use `--max-files`, `--skip-cp-sat`, and
`--cp-sat-time-limit` to control runs on larger tracked collections.

The tracked real subset is documented in [instances/README.md](instances/README.md).
Its seven upstream files are copied from the official ScheduleOpt FJSPLib
repository and retain CC-BY-SA-4.0 attribution.

| FJSPLib instance | Size | Best heuristic in current suite | CP-SAT | FJSPLib BKS |
|---|---:|---:|---:|---:|
| `fattahi1` | 2 x 2 | 66 | 66 `OPTIMAL` | 66 |
| `fattahi2` | 2 x 2 | 107 | 107 `OPTIMAL` | 107 |
| `kacem1` | 4 x 5 | 11 | 11 `OPTIMAL` | 11 |
| Hurink edata `ft06` | 6 x 6 | 55 | 55 `OPTIMAL` | 55 |
| Brandimarte `mk01` | 10 x 6 | 44 | 40 `OPTIMAL` | 40 |
| Brandimarte `mk02` | 10 x 6 | 30 | 29 `FEASIBLE` | 26 |
| Brandimarte `mk03` | 15 x 8 | 204 | 211 `FEASIBLE` | 204 |

For `mk02` and `mk03`, the local CP-SAT values are time-limited feasible
reference schedules, not locally proven optima. Timed CP-SAT runs can vary
between observations.

### Experiment 006: CP-SAT Time-Limit Sweep

Runs tracked Brandimarte `mk03` with a fixed single CP-SAT worker so that
time-limit comparisons have less parallel-search noise.

| Time limit | Makespan | Status | Bound | Relative gap |
|---:|---:|---|---:|---:|
| 1s | 417 | `FEASIBLE` | 20 | 0.952038 |
| 3s | 285 | `FEASIBLE` | 20 | 0.929825 |
| 10s | 220 | `FEASIBLE` | 20 | 0.909091 |

The fixed-worker sweep is intentionally separate from the default batch run,
which allows CP-SAT to use its default worker configuration. Solver settings
are part of an experiment result and must be compared explicitly.

### Experiment 007: CP-SAT Worker-Count Sweep

Runs tracked Brandimarte `mk03` with a fixed 10-second limit while varying the
CP-SAT worker configuration.

| Workers | Makespan | Status | Bound | Relative gap |
|---:|---:|---|---:|---:|
| 1 | 220 | `FEASIBLE` | 20 | 0.909091 |
| 2 | 207 | `FEASIBLE` | 20 | 0.903382 |
| 4 | 207 | `FEASIBLE` | 20 | 0.903382 |
| auto | 209 | `FEASIBLE` | 75 | 0.641148 |

Every row passed the independent feasibility checker. This is one observed
timed run, not a stable worker-performance ranking: parallel CP-SAT search can
vary between runs. The auto configuration produced the strongest bound in
this observation, while 2 and 4 workers produced slightly better incumbents.

### Experiment 008: Repeated CP-SAT Worker Observations

Repeats every tracked worker configuration three times on Brandimarte `mk03`
with the same 10-second limit. Raw runs and aggregate statistics are recorded
separately.

| Workers | Feasible runs | Best makespan | Mean makespan | Std. dev. | Best bound | Best gap |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3 / 3 | 220 | 220.000000 | 0.000000 | 20 | 0.909091 |
| 2 | 3 / 3 | 204 | 204.000000 | 0.000000 | 20 | 0.901961 |
| 4 | 3 / 3 | 204 | 204.000000 | 0.000000 | 21 | 0.897059 |
| auto | 3 / 3 | 204 | 204.000000 | 0.000000 | 88 | 0.568627 |

All 12 schedules passed the independent feasibility checker. In this
three-repeat observation, 2, 4, and automatic workers consistently reached
the upstream BKS of 204. CP-SAT still reported `FEASIBLE`, so these remain
time-limited feasible reference schedules rather than locally proven optima.

### Experiment 009: Repeated CP-SAT Benchmark Matrix

Scans the tracked static FJSPLib subset recursively. Each instance is evaluated
twice with one worker and twice with the automatic worker configuration under
the same 3-second limit.

| Instance | Workers | Feasible runs | Best makespan | Mean makespan | Status | Best bound |
|---|---:|---:|---:|---:|---|---:|
| `mk01` | 1 | 2 / 2 | 40 | 40.000000 | `FEASIBLE` / `OPTIMAL` | 40 |
| `mk01` | auto | 2 / 2 | 40 | 40.000000 | `OPTIMAL` | 40 |
| `mk02` | 1 | 2 / 2 | 31 | 31.000000 | `FEASIBLE` | 3 |
| `mk02` | auto | 2 / 2 | 29 | 29.500000 | `FEASIBLE` | 21 |
| `mk03` | 1 | 2 / 2 | 280 | 282.500000 | `FEASIBLE` | 20 |
| `mk03` | auto | 2 / 2 | 218 | 218.500000 | `FEASIBLE` | 83 |
| `fattahi1` | 1 / auto | 4 / 4 | 66 | 66.000000 | `OPTIMAL` | 66 |
| `fattahi2` | 1 / auto | 4 / 4 | 107 | 107.000000 | `OPTIMAL` | 107 |
| edata `ft06` | 1 / auto | 4 / 4 | 55 | 55.000000 | `OPTIMAL` | 55 |
| `kacem1` | 1 / auto | 4 / 4 | 11 | 11.000000 | `OPTIMAL` | 11 |

All 28 schedules passed the independent feasibility checker. The smaller
tracked instances except `mk02` were solved optimally within the limit. For
`mk02` and `mk03`, automatic workers improved the observed incumbents and
bounds, but neither configuration proved optimality within 3 seconds.

### Experiment 010: Heuristic Benchmark Matrix

Runs deterministic baselines and strict dispatching rules once on each tracked
FJSPLib instance. `Random` and `DispatchRandom` are aggregated across fixed
seeds `42`, `123`, and `999`.

| Instance | Best deterministic rule | Makespan | Random range | DispatchRandom range |
|---|---|---:|---:|---:|
| `mk01` | DispatchMWKR | 44 | 148-165 | 92-125 |
| `mk02` | DispatchMWKR | 30 | 134-169 | 86-113 |
| `mk03` | DispatchFIFO / DispatchMWKR | 204 | 1086-1206 | 488-563 |
| `fattahi1` | DispatchMWKR | 66 | 86-135 | 86-135 |
| `fattahi2` | DispatchFIFO / DispatchMWKR | 107 | 107-192 | 107-149 |
| edata `ft06` | DispatchFIFO | 55 | 146-152 | 71-112 |
| `kacem1` | DispatchFIFO | 11 | 27-82 | 26-44 |

All 98 schedules passed the independent feasibility checker. No single
dispatching rule dominates every instance: MWKR is strongest on `mk01`, `mk02`,
and `fattahi1`, while FIFO is strongest on `ft06` and `kacem1`, and ties MWKR
on `mk03` and `fattahi2`.
Ready-operation random dispatching is consistently better than the simple
job-order random baseline in this tracked subset, but remains seed-sensitive.

### Experiment 011: BKS-Aware Heuristic Quality Report

Reads the structured upstream references in `instances/fjsplib_bks.csv` and
computes

```text
gap_BKS = (makespan - BKS) / BKS
```

for every Experiment 010 family and instance. The upstream BKS values are
comparison references, not local optimality proofs.

| Algorithm family | Mean best gap | Maximum best gap |
|---|---:|---:|
| FIFO | 2.706465 | 5.196078 |
| SPT | 1.592590 | 2.961538 |
| EarliestFinishTime | 0.510503 | 1.384615 |
| DispatchFIFO | 0.092191 | 0.303030 |
| DispatchSPT | 0.910265 | 1.653846 |
| DispatchEFT | 0.513235 | 1.384615 |
| DispatchMWKR | 0.062238 | 0.153846 |
| DispatchMOPNR | 0.165276 | 0.303030 |
| Random | 2.084214 | 4.323529 |
| DispatchRandom | 0.993918 | 2.307692 |

On the current seven-instance subset, DispatchMWKR has the strongest
cross-instance mean best gap. The subset remains intentionally small, so the
next step is broader benchmark coverage before adding more rules.

### Experiment 012: Benchmark Metadata Audit

Recursively discovers tracked FJSPLib files, matches them one-to-one with
`instances/fjsplib_bks.csv`, and verifies that every tracked file still loads.
All seven current rows pass the file, BKS, and loader checks. The script returns
a failing exit code when a file, metadata row, or loadable instance is missing.

## Known Notes

- `experiments/exp_001_gantt_latest.png` is the fixed Gantt output and is tracked.
- Historical Gantt PNG files are retained for traceability.
- A low-priority pytest cache warning may appear on some Windows paths; it does not affect the test results.

## Code Walkthrough

For a guided tour of the Phase 1 code, see [docs/code_walkthrough_phase1.md](docs/code_walkthrough_phase1.md).

## Mathematical Model

The Phase 1 static FJSP formulation is documented in
[docs/math_model_phase1.tex](docs/math_model_phase1.tex). A compiled refreshed
PDF is available at [docs/math_model_phase1_en.pdf](docs/math_model_phase1_en.pdf).

Chinese versions are also available:
[docs/math_model_phase1_zh.tex](docs/math_model_phase1_zh.tex) and
[docs/math_model_phase1_zh.pdf](docs/math_model_phase1_zh.pdf).
