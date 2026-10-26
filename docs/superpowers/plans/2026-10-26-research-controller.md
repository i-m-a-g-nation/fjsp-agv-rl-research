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

## Next authorized increment: controlled candidate profile and simpler navigation

User requested beginning the next step after explaining Markdown proliferation. Audit found124tracked Markdown, including47development records and33otherdocs. Keep this existing plan/ledger and existing controller guide; add no new Markdown. Simplify four navigation documents with START_HERE as single current-status source, leaving evidence paths intact.

**Architecture:** Add an explicit shared_scorer_v1 profile beside the existing audit-only registry. After the same evidence/diagnosis gates it materializes exactly one versioned template into its own batch directory, records an add-only patch and file hashes, runs independent runtime checks, then trains/evaluates that candidate under the original environment/reward/G1. No repository code is overwritten and no document/model instruction can supply executable code. This is controlled template materialization, not arbitrary AI code synthesis.

**Candidate:** Shared32feature/16hidden/tanh/1score network over every task-machine or maintenance action; all local/pool features exclude IDs.545parameters. Reuse original masked probabilities, PolicySample and checked rollout through a MaskedMLP subclass; original actor/trainer and saved weights unchanged. Analytic REINFORCE gradients must pass finite differences; distribution equivariance checked before and after training. Greedy ties need not be label-equivariant.

**Protocol:** Frozen train8/validation4 fromexp026, modesfixed/joint,seeds17/29,64episodes each, total1536newtrainingsteps. Same64episode budget as archived none controls; controls/rules/CP are replay-verified archived evidence, not fresh retraining. Select earliest minimum validation checkpoint; compare all8validation outcomes per mode, strict lower mean retains candidate, otherwise reject. No probe/final testing/API/network; no production default change or scientific achievement.

**Files/interfaces:**
- Template `src/graduation/candidate_templates/shared_scorer.py`: SharedScorer(seed,hidden_size16), state_dict/from_state, probabilities/select_action/log_probability_gradient/reinforce_update, original samplefeatures372 with32actionfeatures. Tests own `tests/test_shared_scorer.py`.
- Trainer `src/graduation/candidate_training.py`: train_shared_policy(training,validation,*,mode,seed,episodes64,validation_every16,check_budget=None,on_progress=None)->original compatible training record. Tests `tests/test_candidate_training.py`.
- Controlled package/experiment adapter `src/ai_workflow/controlled_candidate.py`: materialize_candidate(batch),check_candidate(batch),compare_candidate(batch,reference), immutable template+protected identities, full logs/NPZ/checks/decisions. Tests `tests/test_controlled_candidate.py`.
- Comparison adapter `src/ai_workflow/candidate_comparison.py` owns bounded training/reference replay; `candidate_evidence.py` independently checks complete result artifacts, checkpoints, logs and selection denominators.
- Extend existingcontroller/tasks/worker/exp027 with explicitprofile and owned batch artifact output,5tasks shared120second active cap; audit profile remains2tasks. Source/contract/input change requires new batch, never rewrites prior archives.

### Acceptance steps

- [x] Simplify existing navigation and validate links; explain retained historical files.
- [x] RED/GREEN shared actor and trainer, no protected source edits.
- [x] RED/GREEN package boundaries, test gate, comparison completeness, budget/resume and rejection/retention semantics.
- [x] Independent review and targeted fixes; frozen full regression and one native five-task batch plus terminal resume.
- [x] Archive actual results; update existing guide/START_HERE; secret/hash/diff checks and commit. No merge/push.

Ruling: one predeclared template limits what the program can materialize and execute; arbitrary AI patches and automatic paper discovery remain later work. A retained validation candidate is a batch artifact, never automatic promotion to the repository or a final research claim.

### Increment execution ledger (verification completed2026-10-27)

- Navigation audit removed479netlines from4existingpages, validated186local links/headings; no newMD, moves or deletions. Further edits keep existingguide andSTART_HERE only.
- Actor/trainer63newtests RED→GREEN; original+new131passes. Comparison26tests passed, including native64episode protocol and reference/source/config/data/checker corruption; all original sources unchanged.
- Parent integration initially32passes. Fresh review found gatefile-count bypass and summary-only completion;3newregressions failed before receipt/evidence fixes. Follow-up reported no runtimeblocker; sole testfixture issue corrected withvalidgate receipt, rerunpassed. Candidate evidence now requires exactartifactclosure, checked32plans/recomputedmeans,256logs,52checkpointidentities and384states.
- Frozenfullsuite1377passed/2skipped/13warnings,90.88%coverage,818.97seconds,exit0. Activebudget120seconds,0provider/tokens,5tasks.
- Nativebatch36.5active seconds;fixed31vs10.25,joint17.75vs7.5:bothrejectshared/retainnone. Selectedepochs0,0,0,64. Native terminalresume identical with0newtasks/training.
- Fresh reviewer hit an account quota before numerical replay; parent completed independent replay instead without calling trainer/comparison/evidence verifier:2274checks/0differences,256updates/1536steps,52checkpoints,80interval+32selected+56referenceplans,384states,81sourceidentities. Runtime/source/nativebytes unchanged.
- Handoffcheck:8editedMarkdown/219localfilelinks valid;124trackedMarkdown/0newMD;156changedfiles actualkeyscan0matches; archiveand81frozenruntimehashesmatch. Read-only archive includes candidatecode/patch/checkreceipt, all52NPZ/logs/results and independentrecord. No merge/push.
