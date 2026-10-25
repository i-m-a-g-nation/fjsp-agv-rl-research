# G2 execution ledger

Plan: docs/superpowers/plans/2026-10-25-graduation-g2.md. Baseline8522d88; managed isolated codex/phase2a-protocol is clean at start. User “开始” follows the specific G2 CP-SAT/independent-enumeration proposal and releases that increment; prior confirmed G1 model is the mathematical authority. No repeated authorization or design questions necessary for already specified choices.

Preflight: reuse dedicated environment via FJSP_CONDA_ENV; no dependency installs. New solver must minimize total tardiness, not inherited makespan. Independent oracle must not call CP-SAT or share its model; budget exhaustion cannot return an optimum. G2 native validation is separate from future workflow integration or final research acceptance.

Task1:25solver tests observed RED for absent module, then98G1/G2 targeted tests GREEN. Actual CP-SAT returns OPTIMAL4/0/6/0; late mandatory maintenance preserves production makespan1/objective0, idle machine maintains in a tight window. Controlled status tests verify FEASIBLE preservation and no extraction for UNKNOWN/INFEASIBLE/MODEL_INVALID. Objective mismatch and unchanged-domain-checker refusal reject. Conservative aggregate numeric guard2^50 keeps diagnostic objectives exact; default one worker/seed42/time10s. Full suite is scheduled after all tasks, targeted results are not claimed as full verification.

Task2:22oracle tests observed RED, then120targeted tests GREEN. Inspection identified eager itertools.product pool construction before the visited-state guard. One extra wide-window preallocation regression observed RED; added cardinality lower-bound guard before product. Final121targeted tests GREEN. Twelve seeded variable-p/d/q/window/fixed-start cases agree for both fixed and joint domains; returned optimal totals respect joint<=fixed. Full enumeration never invokes CP-SAT; exceeding limits raises without a best-prefix result.

Task3:7experiment tests observed RED for absent runner, thenGREEN; combined128graduation tests pass. Runner preserves inputs, separate accepted metrics and raw diagnostics, oracle legality, honest FEASIBLE status, no overwrite and outcome-based rerun digest. Four hand/boundary cases plus8newseeded cases form24native comparisons. Full coverage run and fresh final review now in progress; source files are frozen during full run.

Final review: fresh read-only reviewer found no Critical/Important/Minor issues, Declined-to-judge list empty. Independently reasoned oracle coverage and preallocation/visited-state memory bounds; no fix pass required. No new rulings or deferred minors.

Full verification: dedicated environment, `python -m pytest --cov=src --cov-report=term-missing --cov-fail-under=80 -q` ->492passed,13upstream warnings,88.61%coverage,246.81s,exit0. Native001/002 ->exit0/all schedules feasible, toy CP-SAT11OPTIMAL, legacyCSV/Gantt restored byte-for-byte. Original static/dynamic/G1 checkers, AGENTS/contracts and019/020 protocol/evidence unchanged against8522d88.
