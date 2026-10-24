# Execution ledger — plan: 2026-10-24-workflow-guards.md

- Baseline: 208 tests passed in the dedicated Conda environment in the managed worktree.
- Authorization: the user's “开始改进” accepts the previously discussed priorities; implement inline without another planning approval round.
- Pre-flight: task 2 consumes task 1 result metadata; task 3 preserves SandboxEvaluationResult fields used by the graph. Existing scheduling interfaces remain unchanged.
- Scope: implement the agreed first safeguards, not a new autonomous research platform or the underlying future research algorithms.
- Task 1: complete — 3 audit regressions failed first, then 10 AI/guard tests passed.
- Task 2: complete — 9 contract tests failed first, then 19 combined tests passed. Added a further disk-memory regression before fixing re-ingestion.
- Task 3: worker and CLI implemented — 11 sandbox regressions and 5 CLI/disk-memory regressions observed failing; sandbox/AI/contract group 30 passed and CLI group 5 passed. A legacy invalid-candidate probe hung twice during RED; only its exact test processes were stopped, and the probe was made safe before proceeding.
- Task 3: complete — budget and embedding-outage regressions failed first and were fixed; package metadata dry run passed. Windows worker limits verified.
- Task 4: complete — final full suite 245 passed, coverage 82.15%; experiments 001/002 and 014–017 passed; all three 018 tracks exercised with the expected 0/2/2 exit codes and research incompleteness.
- Final: fixed cached-PDF acquisition provenance loss — two RED→GREEN integrity/cache cases; suite 245/245.
- Final: fixed generated-report quarantine bypass across import routes — three RED→GREEN ingestion cases; suite 245/245.
- Final review: one independent reviewer; both important findings resolved with tests. No deferred minor findings or scope rulings. Real online API and POSIX runtime remain explicit unverified limitations, outside the local/offline verification scope.
- Delivery: preserve the managed worktree and reviewable changes; do not push or merge without a user request. Source scheduling/checker files and tracked experiment outputs are unchanged.
