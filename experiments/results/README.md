# Experiment Results

This directory stores versioned evidence for static FJSP, dynamic scheduling, graduation experiments and research-workflow validation. Current project status is maintained in [START_HERE](../../START_HERE.md); archive contents describe the source and environment recorded at their run time.

| Evidence | Location / guide |
|---|---|
| Phase 1 contract hardening (`fd89472`) | [`phase1_hardening_v1/`](phase1_hardening_v1/) |
| EAM benchmark, shared checks and environment reconstruction | [`phase1_closeout_v1/`](phase1_closeout_v1/); [acceptance guide](../../docs/reproducibility_phase1.md) |
| Dynamic protocol and sequential replay | `exp_019_phase2a_protocol_v1/`, `exp_020_sequential_reschedule_v1/` |
| Graduation reference and rules | `exp_021_graduation_g2_v1/`, `exp_022_graduation_rules_v1/` |
| Paper/code and state encoding evidence | `exp_023_*`, `exp_024_state_encoding_v1/` |
| Current source-bound training references | `exp_025_neural_policy_phase1_v2/`, `exp_026_validation_iteration_phase1_v2/` |
| Controller candidate evidence | `exp_027_controlled_candidate_v1/`; [controller guide](../../docs/research_controller_validation.md) |
| One registered rejection-feedback trial; both candidates rejected | [`exp_027_feedback_v1/summary.json`](exp_027_feedback_v1/summary.json); [verification](exp_027_feedback_v1/validation_record.json) |
| Graduation reference pilot development validation; two complete repeats | [`exp_028_graduation_reference_pilot_v1/`](exp_028_graduation_reference_pilot_v1/); [protocol and limits](../../docs/graduation_g3_protocol_draft.md) |
| Formal main scope preparation snapshot; actual scope approval stored separately | [`exp_029_graduation_main_scope_v1/materials/scope_summary.txt`](exp_029_graduation_main_scope_v1/materials/scope_summary.txt); [verification](exp_029_graduation_main_scope_v1/validation_record.json) |
| Main backend development checks and superseded first evidence packet; never approved | [`exp_030_graduation_main_evidence_v1/materials/evidence_summary.txt`](exp_030_graduation_main_evidence_v1/materials/evidence_summary.txt); [validation](exp_030_graduation_main_evidence_v1/validation_record.json); [independent review limitation](exp_030_graduation_main_evidence_v1/review_limitations.json) |
| Main backend evidence v2 snapshot; later approved, first attempt failed before solve | [`exp_030_graduation_main_evidence_v2/materials/evidence_summary.txt`](exp_030_graduation_main_evidence_v2/materials/evidence_summary.txt); [validation](exp_030_graduation_main_evidence_v2/validation_record.json); [review limitation](exp_030_graduation_main_evidence_v2/review_limitations.json) |
| First approved main attempt failed;480 NOT_RUN rows and actual approvals retained | [`exp_030_graduation_main_failed_v1/failure_summary.txt`](exp_030_graduation_main_failed_v1/failure_summary.txt); [failure record](exp_030_graduation_main_failed_v1/failure_record.json) |
| Corrected second-attempt evidence snapshot; later approved for one attempt | [`exp_030_graduation_main_evidence_v3/attempt_review.txt`](exp_030_graduation_main_evidence_v3/attempt_review.txt); [validation](exp_030_graduation_main_evidence_v3/validation_record.json) |
| Second actual attempt:480 requests,475 accepted/5 ERROR; batch FAILED, conclusion pending | [`exp_030_graduation_main_attempt2_v1/conclusion/conclusion_summary.txt`](exp_030_graduation_main_attempt2_v1/conclusion/conclusion_summary.txt); [raw rows](exp_030_graduation_main_attempt2_v1/run/raw.csv); [validation](exp_030_graduation_main_attempt2_v1/validation_record.json) |

New static schedule CSVs have a sibling `.evidence.json` containing the original instance, complete plan, configuration, source hashes and installed versions. Recheck these with `experiments.artifacts.recheck_results_csv`; old metric-only CSVs cannot be certified as complete-plan evidence. Domain checks for maintenance and dynamic events remain separate. New runs belong under ignored `experiments/runs/`; promote a completed, verified batch to a new archive, never overwrite an old one.

## Historical flat-file index

The early Phase 1 / Phase 2A snapshots below remain available. Their dates, algorithms and results have not been rewritten to match newer runs:

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
- `exp_014_dynamic_reschedule_smoke.csv`
- `exp_014_dynamic_reschedule_smoke.md`

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

Experiment 011 adds UB-relative heuristic quality ratios. Its per-instance
rows and cross-instance family summaries use the structured upstream
references in `instances/fjsplib_bks.csv`.

Experiment 012 records one-to-one tracked-file, LB/UB-row, and loader integrity
checks before the benchmark subset is expanded.

Experiment 013 converts the CP-SAT benchmark-matrix aggregate CSV into a
Markdown report. It adds FJSPLib LB/UB comparison, whether the local result
reaches the upstream UB, and whether the local CP-SAT status proved optimality.

Experiment 014 records Phase 2A dynamic-rescheduling smoke scenarios as both a
CSV table and compact Markdown report. Each PASS row is still validated through
the Phase 1 feasibility checker and Phase 2A dynamic checks.
