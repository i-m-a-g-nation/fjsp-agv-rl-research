# Phase 1 Review Status

Last updated: 2026-06-07

## Current Status

| Item | Value |
|---|---|
| Latest reviewed commit | Current branch `HEAD` |
| Python environment | Dedicated Conda environment: `.conda-env` or `FJSP_CONDA_ENV` |
| matplotlib | 3.8.4 |
| Pillow | 10.4.0 |
| pytest | 194 passed, 0 failed |
| core coverage | 89.35% with 80% CI threshold |
| Known warning | Low-priority `.pytest_cache` warning on some Windows paths |

## Verified Commands

| Command | Exit code | Result |
|---|---:|---|
| `experiments/exp_001_toy_instance.py` | 0 | All heuristic schedules feasible, best makespan 13 |
| `experiments/exp_002_solver_check.py` | 0 | CP-SAT optimal makespan 11 with bound/gap metadata |
| `experiments/exp_003_dispatching_rules.py` | 0 | Strict dispatching rules feasible, including MWKR and MOPNR |
| `experiments/exp_004_benchmark_smoke.py` | 0 | Benchmark-format smoke instances feasible, including MWKR and MOPNR |
| `experiments/exp_005_benchmark_batch.py` | 0 | All 32 discovered files feasible; time-limited CP-SAT `FEASIBLE` statuses remain explicit |
| `experiments/exp_006_cpsat_time_limit_sweep.py` | 0 | Single-worker `mk03` sweep records status, bound, gap, and solver wall time |
| `experiments/exp_007_cpsat_worker_sweep.py` | 0 | Fixed-limit `mk03` sweep records worker-count observations without claiming a stable ranking |
| `experiments/exp_008_cpsat_worker_repeats.py` | 0 | 12/12 repeated `mk03` schedules feasible; raw runs and aggregate statistics recorded separately |
| `experiments/exp_009_cpsat_benchmark_matrix.py` | 0 | 120/120 tracked-subset schedules feasible; timed instances retain bound and gap diagnostics |
| `experiments/exp_010_heuristic_benchmark_matrix.py` | 0 | 420/420 tracked-subset heuristic schedules feasible; seeded random families aggregated |
| `experiments/exp_011_heuristic_quality_report.py` | 0 | Thirty-instance UB-relative per-instance and family summaries generated from structured upstream references |
| `experiments/exp_012_benchmark_metadata_audit.py` | 0 | 30/30 tracked files match LB/UB rows and remain loadable |
| `experiments/exp_013_cpsat_report.py` | 0 | Markdown CP-SAT report generated from exp_009 aggregates without rerunning the solver |
| `experiments/exp_014_dynamic_reschedule_smoke.py` | 0 | Three Phase 2A dynamic-rescheduling smoke scenarios feasible |
| `experiments/exp_015_dynamic_event_file_check.py` | 0 | 3/3 dynamic event JSON files load successfully and have non-decreasing event times |
| `experiments/exp_016_dynamic_event_file_reschedule.py` | 0 | 3/3 dynamic event JSON files drive feasible reschedules |
| `pytest --cov=src --cov-fail-under=80` | 0 | 194 passed; core coverage 89.35% |
| `docs/math_model_phase1.tex` compile | 0 | Tectonic generated refreshed `docs/math_model_phase1_en.pdf` |
| `docs/math_model_phase1_zh.tex` compile | 0 | Tectonic generated `docs/math_model_phase1_zh.pdf` |
| `docs/math_model_phase2a.tex` compile | 0 | Tectonic generated `docs/math_model_phase2a.pdf` |
| `docs/phase2a_dynamic_model_zh.md` | 0 | Chinese Phase 2A dynamic model reading note added |
| `pytest` | 0 | 194 passed |
| `git status --short` | 0 | Pending Phase 2A edits |

## Module Status

| Module | Status | Notes |
|---|---|---|
| `FJSPInstance` | Done | `from_jobs_array`, `get_processing_time`, `is_machine_eligible` |
| Benchmark loader | Done | Smoke coverage plus thirty tracked files across six FJSPLib source families; `fattahi6` records the loadable old-format size as 3 x 3 |
| Benchmark provenance | Done | `instances/README.md` plus `instances/fjsplib_bks.csv` record upstream repository, license, families, and LB/UB values |
| Experiment records | Done | Shared runner plus normalized CSV output for `exp_001` through `exp_013` |
| Benchmark batch entry | Done | Recursive discovery, stable order, loader failure records, optional CP-SAT controls |
| CP-SAT sweep | Done | Fixed-worker `mk03` time-limit comparison with bound/gap diagnostics |
| CP-SAT worker sweep | Done | Fixed-limit `mk03` worker-count comparison with cautious timed-run interpretation |
| CP-SAT worker repeats | Done | Raw and aggregate CSV artifacts; 2, 4, and auto workers reached UB 204 in all three tracked runs |
| CP-SAT benchmark matrix | Done | Controlled repeated 1/auto-worker comparison across the tracked FJSPLib subset; `kacem4` remains time-limited `FEASIBLE` locally |
| CP-SAT report builder | Done | Markdown interpretation report summarizes worker rows, best rows, bounds, gaps, and `OPTIMAL` vs `FEASIBLE` status |
| Dynamic feasibility | Started | Phase 2A checker validates frozen-record immutability, job release times, and machine unavailable windows |
| Dynamic timeline | Started | `apply_events()` applies ordered event sequences and rejects out-of-order timelines |
| Dynamic snapshot | Started | `frozen_records_at_time()` extracts completed and in-process operations for rescheduling |
| Dynamic remaining view | Started | `remaining_operations_from_frozen()` reports unscheduled operations after frozen route prefixes |
| Dynamic event specs | Started | Structured dictionaries and UTF-8 JSON arrays can be converted into typed dynamic events; `exp_015` audits three event files and `exp_016` replays them into feasible schedules |
| Code walkthrough | Done | Clean Chinese guide for reading Phase 1 modules and understanding solver data flow |
| Reproducibility checklist | Done | Fixed command order for metadata audit, benchmark runs, CP-SAT report, pytest, and PDF checks |
| CI / coverage | Done | GitHub Actions workflow installs dev dependencies, audits metadata, builds CP-SAT report, and enforces core coverage >= 80% |
| Heuristic benchmark matrix | Done | Deterministic rules plus seeded Random and DispatchRandom families across the tracked subset |
| Heuristic quality report | Done | Per-instance and cross-instance UB-relative ratios with reference coverage checks |
| Benchmark metadata audit | Done | One-to-one tracked-file, LB/UB-row, and loader integrity gate |
| `encoding` | Done | `ScheduleRecord`, `ScheduleResult`, solver status/bound/gap/wall-time metadata |
| `decoding` | Done | Semi-active `decode_schedule` |
| `feasibility` | Done | Core constraints plus robustness checks |
| Heuristics | Done | Split into `baselines.py`, `dispatching.py`, and compatibility facade `heuristics.py`; includes MWKR and MOPNR |
| CP-SAT | Done | Optional intervals, `NoOverlap`, precedence, end-time validation, bound/gap reporting |
| Gantt | Done | Agg backend, fixed `exp_001_gantt_latest.png` output |
| Math model | Done | Static FJSP formulation in English and Chinese LaTeX plus compiled PDFs |

## Next Review Targets

1. Keep benchmark expansion in controlled batches, with metadata audit before experiment runs.
2. Compare larger static benchmark subsets before adding more dispatching rules.
3. Treat AGV/RL/GNN as a later phase only after the static FJSP baseline remains stable.
