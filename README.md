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
- Provenance-documented FJSPLib subset from six upstream families
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
Its twenty-two upstream files are copied from the official ScheduleOpt FJSPLib
repository and retain CC-BY-SA-4.0 attribution.

| FJSPLib instance | Size | Best heuristic in current suite | CP-SAT | FJSPLib BKS |
|---|---:|---:|---:|---:|
| `fattahi1` | 2 x 2 | 66 | 66 `OPTIMAL` | 66 |
| `fattahi2` | 2 x 2 | 107 | 107 `OPTIMAL` | 107 |
| `fattahi3` | 3 x 2 | 221 | 221 `OPTIMAL` | 221 |
| `fattahi4` | 3 x 2 | 367 | 355 `OPTIMAL` | 355 |
| `fattahi5` | 3 x 2 | 119 | 119 `OPTIMAL` | 119 |
| `fattahi6` | 3 x 3 | 330 | 320 `OPTIMAL` | 320 |
| Chambers-Barnes `mt10c1` | 10 x 11 | 1225 | 927 `FEASIBLE` | 927 |
| Dauzere-Peres `01a` | 10 x 5 | 3056 | 2628 `FEASIBLE` | 2505 |
| `kacem1` | 4 x 5 | 11 | 11 `OPTIMAL` | 11 |
| `kacem2` | 10 x 7 | 12 | 11 `OPTIMAL` | 11 |
| `kacem3` | 10 x 10 | 8 | 7 `OPTIMAL` | 7 |
| `kacem4` | 15 x 10 | 12 | 15 `FEASIBLE` | 11 |
| Hurink edata `ft06` | 6 x 6 | 55 | 55 `OPTIMAL` | 55 |
| Brandimarte `mk01` | 10 x 6 | 44 | 40 `OPTIMAL` | 40 |
| Brandimarte `mk02` | 10 x 6 | 30 | 28 `FEASIBLE` | 26 |
| Brandimarte `mk03` | 15 x 8 | 204 | 220 `FEASIBLE` | 204 |
| Brandimarte `mk04` | 15 x 8 | 77 | 62 `FEASIBLE` | 60 |
| Brandimarte `mk05` | 15 x 4 | 185 | 180 `FEASIBLE` | 172 |
| Brandimarte `mk06` | 10 x 15 | 67 | 74 `FEASIBLE` | 57 |
| Brandimarte `mk07` | 20 x 5 | 160 | 159 `FEASIBLE` | 139 |
| Brandimarte `mk08` | 20 x 10 | 531 | 523 `FEASIBLE` | 523 |
| Brandimarte `mk09` | 20 x 10 | 341 | 340 `FEASIBLE` | 307 |

For `mk02`, `mk03`, `mk04`, `mk05`, `mk06`, `mk07`, `mk08`, `mk09`, `mt10c1`, `01a`, and `kacem4`, the local
CP-SAT values are time-limited feasible reference schedules, not locally proven
optima. Timed CP-SAT runs can vary between observations.

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
| `mk01` | 1 | 2 / 2 | 40 | 40.000000 | `OPTIMAL` | 40 |
| `mk01` | auto | 2 / 2 | 40 | 40.000000 | `OPTIMAL` | 40 |
| `mk02` | 1 | 2 / 2 | 31 | 31.000000 | `FEASIBLE` | 3 |
| `mk02` | auto | 2 / 2 | 30 | 30.000000 | `FEASIBLE` | 20 |
| `mk03` | 1 | 2 / 2 | 352 | 352.000000 | `FEASIBLE` | 20 |
| `mk03` | auto | 2 / 2 | 234 | 234.000000 | `FEASIBLE` | 82 |
| `mk04` | 1 | 2 / 2 | 68 | 68.000000 | `FEASIBLE` | 14 |
| `mk04` | auto | 2 / 2 | 64 | 65.000000 | `FEASIBLE` | 41 |
| `mk05` | 1 | 2 / 2 | 199 | 199.000000 | `FEASIBLE` | 32 |
| `mk05` | auto | 2 / 2 | 180 | 180.500000 | `FEASIBLE` | 79 |
| `mk06` | 1 | 2 / 2 | 119 | 120.000000 | `FEASIBLE` | 6 |
| `mk06` | auto | 2 / 2 | 77 | 80.000000 | `FEASIBLE` | 28 |
| `mk07` | 1 | 2 / 2 | 184 | 184.000000 | `FEASIBLE` | 25 |
| `mk07` | auto | 2 / 2 | 168 | 172.000000 | `FEASIBLE` | 87 |
| `mk08` | 1 | 2 / 2 | 578 | 578.000000 | `FEASIBLE` | 182 |
| `mk08` | auto | 2 / 2 | 528 | 530.500000 | `FEASIBLE` | 244 |
| `mk09` | 1 | 2 / 2 | 589 | 589.000000 | `FEASIBLE` | 27 |
| `mk09` | auto | 2 / 2 | 421 | 424.500000 | `FEASIBLE` | 118 |
| `mt10c1` | 1 | 2 / 2 | 957 | 957.000000 | `FEASIBLE` | 759 |
| `mt10c1` | auto | 2 / 2 | 928 | 930.000000 | `FEASIBLE` | 863 |
| `01a` | 1 | 2 / 2 | 2843 | 2843.000000 | `FEASIBLE` | 1395 |
| `01a` | auto | 2 / 2 | 2645 | 2647.000000 | `FEASIBLE` | 2107 |
| `fattahi1` | 1 / auto | 4 / 4 | 66 | 66.000000 | `OPTIMAL` | 66 |
| `fattahi2` | 1 / auto | 4 / 4 | 107 | 107.000000 | `OPTIMAL` | 107 |
| `fattahi3` | 1 / auto | 4 / 4 | 221 | 221.000000 | `OPTIMAL` | 221 |
| `fattahi4` | 1 / auto | 4 / 4 | 355 | 355.000000 | `OPTIMAL` | 355 |
| `fattahi5` | 1 / auto | 4 / 4 | 119 | 119.000000 | `OPTIMAL` | 119 |
| `fattahi6` | 1 / auto | 4 / 4 | 320 | 320.000000 | `OPTIMAL` | 320 |
| edata `ft06` | 1 / auto | 4 / 4 | 55 | 55.000000 | `OPTIMAL` | 55 |
| `kacem1` | 1 / auto | 4 / 4 | 11 | 11.000000 | `OPTIMAL` | 11 |
| `kacem2` | 1 / auto | 4 / 4 | 11 | 11.000000 | `OPTIMAL` | 11 |
| `kacem3` | 1 / auto | 4 / 4 | 7 | 7.000000 | `OPTIMAL` | 7 |
| `kacem4` | 1 | 2 / 2 | 167 | 167.000000 | `FEASIBLE` | 0 |
| `kacem4` | auto | 2 / 2 | 19 | 20.000000 | `FEASIBLE` | 10 |

All 88 schedules passed the independent feasibility checker. The smaller
tracked instances except `mk02` were solved optimally within the limit. For
`mk02`, `mk03`, `mk04`, `mk05`, `mk06`, `mk07`, `mk08`, `mk09`, `mt10c1`, `01a`, and `kacem4`, automatic
workers improved the observed incumbents and bounds in this run, but neither
configuration proved optimality within 3 seconds.

### Experiment 010: Heuristic Benchmark Matrix

Runs deterministic baselines and strict dispatching rules once on each tracked
FJSPLib instance. `Random` and `DispatchRandom` are aggregated across fixed
seeds `42`, `123`, and `999`.

| Instance | Best deterministic rule | Makespan | Random range | DispatchRandom range |
|---|---|---:|---:|---:|
| `mk01` | DispatchMWKR | 44 | 148-165 | 92-125 |
| `mk02` | DispatchMWKR | 30 | 134-169 | 86-113 |
| `mk03` | DispatchFIFO / DispatchMWKR | 204 | 1086-1206 | 488-563 |
| `mk04` | DispatchFIFO | 77 | 279-292 | 143-177 |
| `mk05` | DispatchFIFO | 185 | 541-584 | 287-323 |
| `mk06` | DispatchMWKR | 67 | 594-673 | 222-238 |
| `mk07` | DispatchMOPNR | 160 | 689-854 | 345-427 |
| `mk08` | DispatchFIFO | 531 | 2306-2560 | 755-916 |
| `mk09` | DispatchFIFO | 341 | 2071-2200 | 817-960 |
| `mt10c1` | DispatchMOPNR | 1225 | 3348-3394 | 1446-1728 |
| `01a` | DispatchFIFO | 3056 | 10212-10398 | 4132-4525 |
| `fattahi1` | DispatchMWKR | 66 | 86-135 | 86-135 |
| `fattahi2` | DispatchFIFO / DispatchMWKR | 107 | 107-192 | 107-149 |
| `fattahi3` | DispatchFIFO / DispatchMOPNR | 221 | 298-442 | 221-361 |
| `fattahi4` | DispatchFIFO / DispatchMWKR / DispatchMOPNR | 367 | 409-699 | 407-626 |
| `fattahi5` | DispatchFIFO | 119 | 207-246 | 150-220 |
| `fattahi6` | EarliestFinishTime / DispatchEFT | 330 | 557-707 | 470-557 |
| edata `ft06` | DispatchFIFO | 55 | 146-152 | 71-112 |
| `kacem1` | DispatchFIFO | 11 | 27-82 | 26-44 |
| `kacem2` | DispatchMWKR | 12 | 62-102 | 50-88 |
| `kacem3` | DispatchFIFO / DispatchMWKR / DispatchMOPNR | 8 | 42-77 | 50-72 |
| `kacem4` | DispatchMWKR | 12 | 114-159 | 71-138 |

All 308 schedules passed the independent feasibility checker. No single
dispatching rule dominates every instance: MWKR is strongest on `mk01`, `mk02`,
`mk06`, `fattahi1`, `kacem2`, and `kacem4`; FIFO is strongest on `mk04`, `mk05`,
`mk08`, `mk09`, `fattahi5`, `ft06`, and `kacem1`, ties MWKR on `mk03` and `fattahi2`, and ties
MOPNR on `fattahi3` and `fattahi4`. EarliestFinishTime ties DispatchEFT on
`fattahi6`. MOPNR is strongest on `mk07` and `mt10c1`; FIFO is strongest on `01a`; and FIFO, MWKR, and MOPNR
tie on `kacem3`.
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
| FIFO | 5.456190 | 25.090909 |
| SPT | 2.092635 | 4.473684 |
| EarliestFinishTime | 0.412865 | 1.384615 |
| DispatchFIFO | 0.135868 | 0.331176 |
| DispatchSPT | 1.192609 | 3.325733 |
| DispatchEFT | 0.416947 | 1.384615 |
| DispatchMWKR | 0.138297 | 0.350593 |
| DispatchMOPNR | 0.180611 | 0.466667 |
| Random | 3.163036 | 9.421053 |
| DispatchRandom | 1.487223 | 6.142857 |

On the current twenty-two-instance subset, DispatchFIFO has the strongest
cross-instance mean best gap. The subset remains intentionally small, so the
next step is broader benchmark coverage before adding more rules.

### Experiment 012: Benchmark Metadata Audit

Recursively discovers tracked FJSPLib files, matches them one-to-one with
`instances/fjsplib_bks.csv`, and verifies that every tracked file still loads.
All twenty-two current rows pass the file, BKS, and loader checks. The script returns
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
