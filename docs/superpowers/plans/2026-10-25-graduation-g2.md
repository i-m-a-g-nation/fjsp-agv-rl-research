# Graduation G2 reference solver implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline, TDD and one fresh final review. User requested execution of the previously described G2 approach; do not repeat authorization questions.

**Goal:** Solve and independently validate tiny fixed/joint production-maintenance models.
**Architecture:** New graduation CP-SAT module plus bounded combinatorial oracle; keep G1 domain checker and existing FJSP solver/checkers unchanged. A native validation runner records inputs, outputs, statuses and objective-specific diagnostics.
**Tech Stack:** Existing Python/OR-Tools/pytest; dedicated Conda only, no dependencies added.
**Spec:** docs/superpowers/specs/2026-10-25-graduation-g2-design.md; mathematical authority docs/graduation_model_draft.md.

## Global Constraints

- First edition: identical machines, single nonpreemptive operation, release0, mandatory once-per-machine maintenance including idle machines, complete windows, no shared crew.
- No AGV/RL/transport, new provider calls, workflow auto-approval or scientific superiority claims. No edits to original static/dynamic checkers, AGENTS, frozen contracts or019/020 archives.
- Preserve ScheduleResult production makespan. Objective/gap are total tardiness. FEASIBLE stays FEASIBLE. No extractable result for failed status or checker refusal.
- Reuse current managed codex/phase2a-protocol worktree, baseline8522d88. Inline method persists from previous phase.

## Review Focus

- Due dates/objectives/numerical bounds cause CP-SAT overflow or model-invalid; reject instead of returning a bogus optimum.
- Idle machines, tight windows, and maintenance ending after all production still retain exactly one mandatory interval and production-only makespan.
- Independent oracle covers all assignments/orders/maintenance positions, and its budget termination never masquerades as OPTIMAL.
- Status/bound/gap refer to total tardiness, including zero objective and FEASIBLE solutions; corrupt extraction and checker refusal never return a valid result.
- Batch failures and different same-objective schedules are honestly represented; invalid plans have no accepted metric and reruns preserve old output.

### Task1 — fixed/joint CP-SAT

Files: src/graduation/solver.py (new), result.py and __init__.py (compatible exports), tests/test_graduation_solver.py (new).
Interface: solve_parallel_maintenance(data,*,mode,time_limit=10.0,num_workers=1,seed=42)->MaintenanceScheduleResult; GraduationSolverError for solver/extraction/validation failure. Add optional solver_objective_value to result.

- [x] Write tests for literal4/0/6/0, production-only makespan with late mandatory maintenance, idle-machine/tight-window maintenance, strict config/numerical guards, FEASIBLE preservation, no extraction on bad statuses, independent metric/checker refusal.
- [x] Run `python -m pytest tests/test_graduation_solver.py -q --tb=short`; Expected RED missing solver module.
- [x] Implement optional production intervals, mandatory maintenance, exact max tardiness, validation and metadata; default one worker andseed42.
- [x] Run all tests/test_graduation*.py; Expected all pass. Commit task1 with ledger.

### Task2 — independent finite oracle

Files: src/graduation/enumeration.py, tests/test_graduation_enumeration.py; __init__.py exports.
Interface: enumerate_parallel_maintenance(data,*,mode,max_states=200000)->MaintenanceScheduleResult; EnumerationLimitError on exhausted budget/unsupported tiny size. n<=5,m<=3,max_states<=200000.

- [x] Tests:4/0/6/0,12seeded tiny instances with variable p/d/q/window/fixed-start, both methods agree, joint<=fixed when proven optimal, checker acceptance, budget failure with no prefix result, no CP-SAT call from enumeration, same immutable data unchanged.
- [x] Run `python -m pytest tests/test_graduation_enumeration.py -q --tb=short`; Expected RED absent oracle.
- [x] Enumerate maintenance starts, assignments, permutations, per-machine maintenance cut; direct positive-lateness sum, domain-check final best only. No CP-SAT or shared metric used to choose best.
- [x] Run G1/G2 targeted suite; Expected all pass. Commit task2 and completeness/budget evidence.

### Task3 — runnable validation and documentation

Files: experiments/exp_021_graduation_solver_check.py, tests/test_graduation_experiment.py, docs/graduation_g2_validation.md, review_status/model/acceptance/readmes progress; new archived021 only after tested source commit.
Interface: run_experiment(output_dir:Path)->manifest, main(argv=None)->exitcode. Fixed defaults10seconds,one worker,seed42; separate fixed/joint inputs and full schedules, original solver objective/bound/gap/time and oracle objective. Never overwrite.

- [x] Tests for native fixture objectives, source/artifact hashes, same-input/config/outcome digest across reruns, corrupt/failed result no accepted metric andCLI failure, output preservation, FEASIBLE distinguished from optimum.
- [x] Run experiment tests; Expected RED absent runner.
- [x] Implement runner/report; both OPTIMAL objectives must match oracle for validationPASS. Domain-accepted FEASIBLE remains feasible but validation not complete.
- [x] Run all G1/G2 tests then full `python -m pytest --cov=src --cov-report=term-missing --cov-fail-under=80 -q`; Expected green>=80%. No source edits during full run.
- [x] One fresh-context read-only review of G2 delta; Critical/Important single TDD fix pass, Minor ledgered. Native001/002 rerun with tracked artifacts restored byte-for-byte.
- [x] Commit tested code, generate021 archive against that source, independently replay outcome digest, verify bytes/source and archive with exact-byte gitattributes. Keep branch/worktree, no push/merge or human approval.
