# Experiment Results

This directory stores normalized CSV outputs produced by Phase 1 experiment scripts.

Current generated files:

- `exp_001_toy_instance.csv`
- `exp_002_solver_check.csv`
- `exp_003_dispatching_rules.csv`
- `exp_004_benchmark_smoke.csv`

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
