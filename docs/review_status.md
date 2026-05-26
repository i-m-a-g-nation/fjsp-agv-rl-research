# Phase 1 Review Status

Last updated: 2026-05-19

## Current Status

| Item | Value |
|---|---|
| Latest reviewed commit | `3723cce` |
| Python environment | Dedicated Conda environment: `.conda-env` or `FJSP_CONDA_ENV` |
| matplotlib | 3.8.4 |
| Pillow | 10.4.0 |
| pytest | 81 passed, 0 failed |
| Known warning | Low-priority `.pytest_cache` warning on some Windows paths |

## Verified Commands

| Command | Exit code | Result |
|---|---:|---|
| `experiments/exp_001_toy_instance.py` | 0 | All heuristic schedules feasible, best makespan 13 |
| `experiments/exp_002_solver_check.py` | 0 | CP-SAT optimal makespan 11 |
| `experiments/exp_003_dispatching_rules.py` | 0 | Strict dispatching rules feasible |
| `experiments/exp_004_benchmark_smoke.py` | 0 | Benchmark-format smoke instances feasible |
| `pytest` | 0 | 81 passed |
| `git status --short` | 0 | Clean |

## Module Status

| Module | Status | Notes |
|---|---|---|
| `FJSPInstance` | Done | `from_jobs_array`, `get_processing_time`, `is_machine_eligible` |
| Benchmark loader | Done | Small Brandimarte/FJSPLib-style text and file loading smoke coverage |
| `encoding` | Done | `ScheduleRecord`, `ScheduleResult`, `solver_status` |
| `decoding` | Done | Semi-active `decode_schedule` |
| `feasibility` | Done | Core constraints plus robustness checks |
| Heuristics | Done | Simple baselines plus strict FIFO/SPT/EFT/Random dispatching rules |
| CP-SAT | Done | Optional intervals, `NoOverlap`, precedence, end-time validation |
| Gantt | Done | Agg backend, fixed `exp_001_gantt_latest.png` output |

## Next Review Targets

1. Load real benchmark instances from FJSPLib, Brandimarte, and Hurink formats.
2. Add CP-SAT time-limit and gap reporting.
3. Add more static FJSP heuristic baselines such as MWKR or MOPNR.
4. Test OR-Tools behavior on larger instances before moving to later phases.
