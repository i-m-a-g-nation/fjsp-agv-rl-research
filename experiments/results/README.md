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
