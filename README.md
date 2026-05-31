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
- Provenance-documented FJSPLib subset from Brandimarte, Hurink, and Fattahi families
- Normalized CSV experiment result recording under `experiments/results/`
- Shared experiment runner utilities for timing, feasibility validation, failures, and solver metadata
- Recursive benchmark batch experiment with stable discovery order and auditable loader failures
- OR-Tools CP-SAT baseline with optional intervals, exactly-one machine assignment, precedence constraints, and machine `NoOverlap`
- CP-SAT diagnostics: solver status, objective bound, relative gap, and solver wall time
- CP-SAT time-limit sweep on tracked `mk03` with a fixed single worker
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
Its four upstream files are copied from the official ScheduleOpt FJSPLib
repository and retain CC-BY-SA-4.0 attribution.

| FJSPLib instance | Size | Best heuristic in current suite | CP-SAT | FJSPLib BKS |
|---|---:|---:|---:|---:|
| `fattahi1` | 2 x 2 | 66 | 66 `OPTIMAL` | 66 |
| Hurink edata `ft06` | 6 x 6 | 55 | 55 `OPTIMAL` | 55 |
| Brandimarte `mk01` | 10 x 6 | 44 | 40 `OPTIMAL` | 40 |
| Brandimarte `mk03` | 15 x 8 | 204 | 204 `FEASIBLE` | 204 |

For `mk03`, the local CP-SAT value matches the upstream BKS, but the solver did
not prove optimality within the 10-second limit. The result is therefore
reported only as a feasible reference schedule.

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
