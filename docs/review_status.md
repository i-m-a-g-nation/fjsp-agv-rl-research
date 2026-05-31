# Phase 1 Review Status

Last updated: 2026-05-31

## Current Status

| Item | Value |
|---|---|
| Latest reviewed commit | Current branch `HEAD` |
| Python environment | Dedicated Conda environment: `.conda-env` or `FJSP_CONDA_ENV` |
| matplotlib | 3.8.4 |
| Pillow | 10.4.0 |
| pytest | 120 passed, 0 failed |
| Known warning | Low-priority `.pytest_cache` warning on some Windows paths |

## Verified Commands

| Command | Exit code | Result |
|---|---:|---|
| `experiments/exp_001_toy_instance.py` | 0 | All heuristic schedules feasible, best makespan 13 |
| `experiments/exp_002_solver_check.py` | 0 | CP-SAT optimal makespan 11 with bound/gap metadata |
| `experiments/exp_003_dispatching_rules.py` | 0 | Strict dispatching rules feasible, including MWKR and MOPNR |
| `experiments/exp_004_benchmark_smoke.py` | 0 | Benchmark-format smoke instances feasible, including MWKR and MOPNR |
| `experiments/exp_005_benchmark_batch.py` | 0 | Recursive batch feasible; `mk03` records time-limited CP-SAT `FEASIBLE` correctly |
| `experiments/exp_006_cpsat_time_limit_sweep.py` | 0 | Single-worker `mk03` sweep records status, bound, gap, and solver wall time |
| `experiments/exp_007_cpsat_worker_sweep.py` | 0 | Fixed-limit `mk03` sweep records worker-count observations without claiming a stable ranking |
| `docs/math_model_phase1.tex` compile | 0 | Tectonic generated refreshed `docs/math_model_phase1_en.pdf` |
| `docs/math_model_phase1_zh.tex` compile | 0 | Tectonic generated `docs/math_model_phase1_zh.pdf` |
| `pytest` | 0 | 120 passed |
| `git status --short` | 0 | Clean |

## Module Status

| Module | Status | Notes |
|---|---|---|
| `FJSPInstance` | Done | `from_jobs_array`, `get_processing_time`, `is_machine_eligible` |
| Benchmark loader | Done | Smoke coverage plus four tracked Brandimarte, Hurink edata, and Fattahi FJSPLib files |
| Benchmark provenance | Done | `instances/README.md` records upstream repository, license, families, and BKS values |
| Experiment records | Done | Shared runner plus normalized CSV output for `exp_001` through `exp_007` |
| Benchmark batch entry | Done | Recursive discovery, stable order, loader failure records, optional CP-SAT controls |
| CP-SAT sweep | Done | Fixed-worker `mk03` time-limit comparison with bound/gap diagnostics |
| CP-SAT worker sweep | Done | Fixed-limit `mk03` worker-count comparison with cautious timed-run interpretation |
| `encoding` | Done | `ScheduleRecord`, `ScheduleResult`, solver status/bound/gap/wall-time metadata |
| `decoding` | Done | Semi-active `decode_schedule` |
| `feasibility` | Done | Core constraints plus robustness checks |
| Heuristics | Done | Split into `baselines.py`, `dispatching.py`, and compatibility facade `heuristics.py`; includes MWKR and MOPNR |
| CP-SAT | Done | Optional intervals, `NoOverlap`, precedence, end-time validation, bound/gap reporting |
| Gantt | Done | Agg backend, fixed `exp_001_gantt_latest.png` output |
| Math model | Done | Static FJSP formulation in English and Chinese LaTeX plus compiled PDFs |

## Next Review Targets

1. Expand the FJSPLib subset in controlled batches beyond `mk03`.
2. Compare heuristic behavior on larger static benchmark subsets before adding more rules.
3. Add repeated-run aggregation before drawing stronger CP-SAT worker-performance conclusions.
