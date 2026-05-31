# Phase 1 Review Status

Last updated: 2026-05-27

## Current Status

| Item | Value |
|---|---|
| Latest reviewed commit | Current branch `HEAD` |
| Python environment | Dedicated Conda environment: `.conda-env` or `FJSP_CONDA_ENV` |
| matplotlib | 3.8.4 |
| Pillow | 10.4.0 |
| pytest | 97 passed, 0 failed |
| Known warning | Low-priority `.pytest_cache` warning on some Windows paths |

## Verified Commands

| Command | Exit code | Result |
|---|---:|---|
| `experiments/exp_001_toy_instance.py` | 0 | All heuristic schedules feasible, best makespan 13 |
| `experiments/exp_002_solver_check.py` | 0 | CP-SAT optimal makespan 11 with bound/gap metadata |
| `experiments/exp_003_dispatching_rules.py` | 0 | Strict dispatching rules feasible, including MWKR |
| `experiments/exp_004_benchmark_smoke.py` | 0 | Benchmark-format smoke instances feasible, including MWKR |
| `docs/math_model_phase1.tex` compile | 0 | Tectonic generated refreshed `docs/math_model_phase1_en.pdf` |
| `docs/math_model_phase1_zh.tex` compile | 0 | Tectonic generated `docs/math_model_phase1_zh.pdf` |
| `pytest` | 0 | 97 passed |
| `git status --short` | 0 | Clean |

## Module Status

| Module | Status | Notes |
|---|---|---|
| `FJSPInstance` | Done | `from_jobs_array`, `get_processing_time`, `is_machine_eligible` |
| Benchmark loader | Done | Small Brandimarte/FJSPLib-style text and file loading smoke coverage |
| Experiment records | Done | Shared runner plus normalized CSV output for `exp_001` through `exp_004` |
| `encoding` | Done | `ScheduleRecord`, `ScheduleResult`, solver status/bound/gap/wall-time metadata |
| `decoding` | Done | Semi-active `decode_schedule` |
| `feasibility` | Done | Core constraints plus robustness checks |
| Heuristics | Done | Split into `baselines.py`, `dispatching.py`, and compatibility facade `heuristics.py` |
| CP-SAT | Done | Optional intervals, `NoOverlap`, precedence, end-time validation, bound/gap reporting |
| Gantt | Done | Agg backend, fixed `exp_001_gantt_latest.png` output |
| Math model | Done | Static FJSP formulation in English and Chinese LaTeX plus compiled PDFs |

## Next Review Targets

1. Load real benchmark instances from FJSPLib, Brandimarte, and Hurink formats.
2. Add more static FJSP heuristic baselines such as MOPNR.
3. Test OR-Tools behavior on larger instances before moving to later phases.
