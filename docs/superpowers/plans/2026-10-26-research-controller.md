# Bounded research controller implementation plan

> **For agentic workers:** Use superpowers:executing-plans or scoped parallel workers; test each task before implementation.

**Goal:** Replace chat-side dispatch for one bounded offline batch with a resumable program which reads evidence, chooses registered tasks, executes them, rereads results and stops explicitly.

**Architecture:** A deterministic planner consumes verified exp026 evidence and separate research contracts. A strict registry exposes a paper evidence audit and a validation-only identifier permutation diagnostic through supervised JSON workers. Persistent budgets, source/input identities, an exclusive lock and atomic state prevent duplicate execution and silent resets. This is a finite executor registry, not autonomous arbitrary code generation.

**Tech stack:** Existing Python/NumPy, RunBudget, process_supervisor, original graduation environment/checker; no new dependencies or API calls.

**Spec:** docs/autonomous_research_loop_requirements.md and the user's approval to begin the outer controller after identifying chat-side dispatch as the missing layer.

## Global constraints

- Preserve original objectives, checkers, contracts, prior evidence and workflow018 review gates.
- No new optimizer/algorithm, AGV, transport implementation, training, probe or final-test evaluation in this batch.
- Graduation and innovation remain separate and research_status remains not_achieved.
- Default cap 120 active seconds, zero provider calls/tokens, two registered tasks; unchanged limits on resume.
- No arbitrary commands, imports or executable instructions from documents/model output.
- Environment paths remain local configuration; no credentials loaded or archived.

## Design choices

Keep existing tools and add a thin registry/controller rather than rewriting workflow018 or adding an unrestricted coding agent. The first task audits archived paper provenance and unapproved semantics; the second tests frozen policy sensitivity to relabeling, the next diagnostic identified by exp026. Both are offline and read-only. The planner skips the rejected running_mean trial and stops with a concrete implementation-needed task after registered capabilities are exhausted. These implementation choices are delegated by the user's request to start; no new human research approval is implied.

## Review focus

- Changed/tampered input or source on resume must fail closed, including task outputs.
- Crash during a task must retain the reservation and mark interruption, not restart work or refund it.
- Concurrent starts must not execute tasks twice.
- A negative diagnostic, missing source or model semantic judgment cannot become a research achievement.
- Permutations must preserve physical constraints and mapped actions; check every completed plan with G1 and reward/TT consistency, and never consume probe/test data.

### Task 1: Frozen validation permutation diagnostic

Files: src/graduation/permutation_diagnostics.py; tests/test_permutation_diagnostics.py.

- [x] RED: permutation/action bijection, identity/uniform control, source/checkpoint tampering, checker and no probe access.
- [x] GREEN: read only exp026 validation and selected none actors; replay the same physical states under job/machine/both reversals; compare mapped distributions and full greedy TT, preserving complete denominators.
- [x] Record targeted test evidence; no original source edits.

### Task 2: Evidence registry and durable controller

Files: src/ai_workflow/research_tasks.py, research_controller.py, research_worker.py; experiments/exp_027_research_controller.py; tests/test_research_controller.py.

- [x] RED: automatic two-task dispatch and result-driven stop; rejection skips retraining; persistence/resume; cap/timeout/crash; tampering and registry boundary.
- [x] GREEN: source/contract/input-bound run, atomic state, exclusive lock, persistent budget; allowlisted supervised adapters only; clear status and stop reason.
- [x] Run targeted tests with dedicated Conda Python.

### Task 3: Review, real run and handoff

- [x] Fresh independent review and fixes supported by regression tests.
- [x] Freeze runtime; full pytest coverage gate and one native batch, plus terminal resume showing zero repeated tasks.
- [x] Archive portable results and source identities; update START_HERE and requirements with actual capability/limits and one command.
- [x] Secret/staged diff checks; commit only verified work. Do not merge/push.

## Execution ledger

- Existing isolated branch codex/phase2a-protocol was clean at b57b9d7; no new worktree needed.
- Task1 delegated only its module/tests;15 targeted passes, including a feature-dependent actor and identity/uniform controls.
- Task2 initial controller17passes; tuple-vs-JSON contract comparison corrected after failing resume tests.
- Independent review found reset on missing/deleted budget ledger, uncharged preflight, and incomplete report acceptance. Added failing regression tests before fixes. Follow-up found incomplete initialization resume and self-declared state denominator; both reproduced RED before related fixes.
- Final targeted38passes in75.00s. Fresh review reports no remaining scoped blockers.
- Ruling: registry is deliberately bound to existing exp026 native4task/2machine validation protocol (64cases/384states), rather than accepting self-declared counts; another dataset requires a versioned adapter and new tests.
- Ruling: terminal reads verify identity without reserving a fresh execution segment; nonterminal preflight is inside the active reservation. Failed initialization has a bootstrap identity and cannot reset budget or restart work.
- Native batch completed both registered tasks in9.187active seconds with0API/network calls, read new sensitivity285/384 and stopped at implementation_required; terminal resume completed without repeated tasks.
- Frozen full regression1276passed/2skipped/13warnings,90.62%coverage,650.36seconds,exit0. Independent native check4782checks/0discrepancies, all128plans/384probability states/fourcheckpoints/75sources,96identity and384uniform controls.
- Native and terminal-resume summaries/budgets identical; portable read-only archive retains both task results, identities, independent check and validation record. Archive is not a relocatable resume folder; source byte/line-ending changes fail closed.
- Staged22files checked against actual configured key (0matches); archive index bytes match all declared hashes, runtime remains frozen, original main checkout clean. No merge/push.
