# Graduation R2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deliver complete EDD/SPT/seeded Random baselines and a reproducible, no-training development smoke comparison.

**Architecture:** Rules consume the existing R1 mask and exact integer machine tails. A bounded episode returns the existing checked schedule type; an offline script records 24 development-validation rows with honest failure accounting.

**Tech Stack:** Existing dedicated Conda Python, dataclasses, random, pytest; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-25-graduation-r2-design.md`

## Global Constraints

- Retain G1 assumptions/checkers, R1 transition/reward/mask, G2 solvers, AGENTS and frozen contracts unchanged except the specified read-only R1 property.
- No PPO/Gym installation or training, AGV/transport implementation, formal G3 execution, model/network calls, synthetic human approvals, old-session mutation, push or merge.
- Dedicated Conda only; check sys.executable before every Python command group. Local environment comes from FJSP_CONDA_ENV, never write machine-specific paths into the repository.
- Source/tests owned by one implementer. No concurrent full test suites; parent runs the full suite after scoped tests and review.
- All algorithms return ScheduleResult-compatible plans and pass the original G1 checker. No optimality certificate for rule plans.

## Review Focus

- Full EDD/SPT priority and machine ties, including exact integer clocks near numeric limits.
- Random seed reentrancy and global RNG isolation, real/padded/maintenance mask handling.
- Mandatory idle-machine maintenance and late maintenance after production makespan.
- Terminal domain failure must not leak a partial plan or accepted row.
- Malformed/unserializable smoke results must retain all24 rows, without accepted metrics.

### Task 1: Complete R2 policies and development evidence

**Files:**
- Create `src/graduation/rules.py`, `tests/test_graduation_rules.py`.
- Modify `src/graduation/rl_environment.py` (read-only tails only), `src/graduation/__init__.py`.
- Create `experiments/exp_022_graduation_rule_smoke.py`, `tests/test_graduation_rule_smoke.py`.
- Create `docs/graduation_r2_validation.md` for implementation semantics and scoped evidence; parent fills full-suite/final review results.

**Interfaces:** Exact public interfaces, rule names, priorities, seed domain, cases and artifact schema are in the Spec; read it before writing tests. No extra strategies or evaluation framework.

- [x] Write meaningful tests for priority differences/ties, fixed/joint literal outcomes4/0 and6/0, exact integer tails isolation, complete maintenance, maximum24/4 inputs, local RNG and invalid rule/seed. Watch expected feature failures before production code.
- [x] Implement the minimal rule module, readonly property and exports; run focused R1/R2/G1 tests to GREEN. Record actual commands/results and RED evidence in task report.
- [x] Write smoke tests for 24 checked rows, deterministic digest in new directories, refusal to overwrite, truthful development labels, manifests/hashes, invalid returned schedule handling retaining failed rows and CLI failure exit. Watch expected missing-function failures.
- [x] Implement the bounded smoke and concise validation document. Run the new focused tests; self-review the full diff against the Spec.
- [x] Commit only owned files. Report actual scoped counts and any concerns; do not run a second full suite (parent owns full verification).

## Parent closeout

- [x] Run one task-scoped spec/code review and handle material issues.
- [x] Run full dedicated-environment regression with coverage and two fresh native smoke directories; compare deterministic evidence and validate saved plans independently.
- [x] Request final branch review, record findings and limitations in durable progress/status docs; keep main and prior evidence unchanged.
