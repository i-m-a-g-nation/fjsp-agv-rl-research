# Experiment Results

This directory stores normalized CSV outputs produced by Phase 1 experiment scripts.

Current generated files:

- `exp_001_toy_instance.csv`
- `exp_002_solver_check.csv`
- `exp_003_dispatching_rules.csv`
- `exp_004_benchmark_smoke.csv`
- `exp_005_benchmark_batch.csv`
- `exp_006_cpsat_time_limit_sweep.csv`
- `exp_007_cpsat_worker_sweep.csv`
- `exp_008_cpsat_worker_repeats_runs.csv`
- `exp_008_cpsat_worker_repeats_summary.csv`
- `exp_009_cpsat_benchmark_matrix_runs.csv`
- `exp_009_cpsat_benchmark_matrix_summary.csv`
- `exp_010_heuristic_benchmark_matrix_runs.csv`
- `exp_010_heuristic_benchmark_matrix_summary.csv`
- `exp_011_heuristic_quality_rows.csv`
- `exp_011_heuristic_quality_families.csv`
- `exp_012_benchmark_metadata_audit.csv`
- `exp_013_cpsat_report.md`

Each row records:

- experiment id
- instance name
- algorithm
- makespan
- feasibility status
- runtime in seconds
- status note
- objective bound, when reported by the solver
- relative optimality gap, when reported by the solver
- solver internal wall time, when reported by the solver

Experiment 011 adds BKS-relative heuristic quality ratios. Its per-instance
rows and cross-instance family summaries use the structured upstream
references in `instances/fjsplib_bks.csv`.

Experiment 012 records one-to-one tracked-file, BKS-row, and loader integrity
checks before the benchmark subset is expanded.

Experiment 013 converts the CP-SAT benchmark-matrix aggregate CSV into a
Markdown report. It adds FJSPLib LB/UB comparison, whether the local result
reaches the upstream UB, and whether the local CP-SAT status proved optimality.
