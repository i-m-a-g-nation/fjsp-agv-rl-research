# Phase 1 Review Status

Last updated: 2026-06-01

## Current Status

| Item | Value |
|---|---|
| Latest reviewed commit | Current branch `HEAD` |
| Python environment | Dedicated Conda environment: `.conda-env` or `FJSP_CONDA_ENV` |
| matplotlib | 3.8.4 |
| Pillow | 10.4.0 |
| pytest | 147 passed, 0 failed |
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
| `experiments/exp_008_cpsat_worker_repeats.py` | 0 | 12/12 repeated `mk03` schedules feasible; raw runs and aggregate statistics recorded separately |
| `experiments/exp_009_cpsat_benchmark_matrix.py` | 0 | 16/16 tracked-subset schedules feasible; smaller instances optimal and `mk03` time-limited |
| `experiments/exp_010_heuristic_benchmark_matrix.py` | 0 | 56/56 tracked-subset heuristic schedules feasible; seeded random families aggregated |
| `experiments/exp_011_heuristic_quality_report.py` | 0 | BKS-relative per-instance and family summaries generated from structured upstream references |
| `experiments/exp_012_benchmark_metadata_audit.py` | 0 | 4/4 tracked files match BKS rows and remain loadable |
| `docs/math_model_phase1.tex` compile | 0 | Tectonic generated refreshed `docs/math_model_phase1_en.pdf` |
| `docs/math_model_phase1_zh.tex` compile | 0 | Tectonic generated `docs/math_model_phase1_zh.pdf` |
| `pytest` | 0 | 147 passed |
| `git status --short` | 0 | Clean |

## Module Status

| Module | Status | Notes |
|---|---|---|
| `FJSPInstance` | Done | `from_jobs_array`, `get_processing_time`, `is_machine_eligible` |
| Benchmark loader | Done | Smoke coverage plus four tracked Brandimarte, Hurink edata, and Fattahi FJSPLib files |
| Benchmark provenance | Done | `instances/README.md` plus `instances/fjsplib_bks.csv` record upstream repository, license, families, and BKS values |
| Experiment records | Done | Shared runner plus normalized CSV output for `exp_001` through `exp_012` |
| Benchmark batch entry | Done | Recursive discovery, stable order, loader failure records, optional CP-SAT controls |
| CP-SAT sweep | Done | Fixed-worker `mk03` time-limit comparison with bound/gap diagnostics |
| CP-SAT worker sweep | Done | Fixed-limit `mk03` worker-count comparison with cautious timed-run interpretation |
| CP-SAT worker repeats | Done | Raw and aggregate CSV artifacts; 2, 4, and auto workers reached BKS 204 in all three tracked runs |
| CP-SAT benchmark matrix | Done | Controlled repeated 1/auto-worker comparison across the tracked FJSPLib subset |
| Heuristic benchmark matrix | Done | Deterministic rules plus seeded Random and DispatchRandom families across the tracked subset |
| Heuristic quality report | Done | Per-instance and cross-instance BKS-relative ratios with reference coverage checks |
| Benchmark metadata audit | Done | One-to-one tracked-file, BKS-row, and loader integrity gate |
| `encoding` | Done | `ScheduleRecord`, `ScheduleResult`, solver status/bound/gap/wall-time metadata |
| `decoding` | Done | Semi-active `decode_schedule` |
| `feasibility` | Done | Core constraints plus robustness checks |
| Heuristics | Done | Split into `baselines.py`, `dispatching.py`, and compatibility facade `heuristics.py`; includes MWKR and MOPNR |
| CP-SAT | Done | Optional intervals, `NoOverlap`, precedence, end-time validation, bound/gap reporting |
| Gantt | Done | Agg backend, fixed `exp_001_gantt_latest.png` output |
| Math model | Done | Static FJSP formulation in English and Chinese LaTeX plus compiled PDFs |

## Next Review Targets

1. Expand the FJSPLib subset in controlled batches beyond `mk03`.
2. Re-run metadata audit and heuristic quality ratios after each benchmark batch.
3. Compare larger static benchmark subsets before adding more dispatching rules.
