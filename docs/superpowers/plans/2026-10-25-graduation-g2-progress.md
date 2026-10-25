# G2 execution ledger

Plan: docs/superpowers/plans/2026-10-25-graduation-g2.md. Baseline8522d88; managed isolated codex/phase2a-protocol is clean at start. User “开始” follows the specific G2 CP-SAT/independent-enumeration proposal and releases that increment; prior confirmed G1 model is the mathematical authority. No repeated authorization or design questions necessary for already specified choices.

Preflight: reuse dedicated environment via FJSP_CONDA_ENV; no dependency installs. New solver must minimize total tardiness, not inherited makespan. Independent oracle must not call CP-SAT or share its model; budget exhaustion cannot return an optimum. G2 native validation is separate from future workflow integration or final research acceptance.

Task1:25solver tests observed RED for absent module, then98G1/G2 targeted tests GREEN. Actual CP-SAT returns OPTIMAL4/0/6/0; late mandatory maintenance preserves production makespan1/objective0, idle machine maintains in a tight window. Controlled status tests verify FEASIBLE preservation and no extraction for UNKNOWN/INFEASIBLE/MODEL_INVALID. Objective mismatch and unchanged-domain-checker refusal reject. Conservative aggregate numeric guard2^50 keeps diagnostic objectives exact; default one worker/seed42/time10s. Full suite is scheduled after all tasks, targeted results are not claimed as full verification.
