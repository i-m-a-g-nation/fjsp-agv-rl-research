# Evidence traceability progress

Pre-flight: Task 1 produces allowlisted claim references and audit data consumed by Task 2 and Task 3. Task 2's code-derived source map is bound in Task 3's existing evidence review payload. No scheduling interface changes.

Task 1: Seven tests observed RED (missing auditor), then GREEN. Missing, repeated, forged-offset, wrong-index and unseen-text references do not establish evidence. Model-supplied verification is overwritten.

Task 2: Five PDF/provider/report tests observed RED before implementation. Code-derived physical page mapping preserves empty pages and only applies when the complete extracted PDF body occurs uniquely in the resolved text. Raw-file hashes are separate from normalized-text offsets. Integration verification in progress.

Task 3: Source-change regression observed RED before adding the identity check. First combined run: 25 passed, one report-format failure (escaped status); corrected renderer, verification pending.

Integration verification: 26 passed after report-format fix. Evidence/review/session integration then passed 32 tests, including changed resolved-cache rejection after evidence approval. No real model calls.

Task 2 follow-up: local PDF source without download metadata regression RED→GREEN. Downloaded PDF outer-whitespace normalization regression RED→GREEN; physical page numbering still includes empty pages. Latest evidence/review gate suite: 21 passed. Fully located claims remain unverified; prefix text receives no PDF page and cross-page quotes preserve the actual page range.

Task 3 in progress: documentation updated; independent whole-change review and complete coverage verification pending.

Pre-review full verification: 292 passed, 85.26% source coverage, unchanged 80% minimum. Native experiments 001/002 passed; CP-SAT toy makespan 11 OPTIMAL. Existing tracked CSV/Gantt artifacts restored byte-for-byte.

Independent review: one Important finding, no Critical or deferred Minor findings. Unbound legacy caches and identifier-free version-1 caches could substitute a different paper before deterministic auditing. Five regressions reproduced that problem RED; an additional changed-PDF cache association regression also failed before the fix. One fix pass binds new acquisitions to request identity, requires sufficient identity for old-cache reuse, and binds the neighboring PDF by byte hash. Correct matching DOI/arXiv version-1 caches retain text/depth compatibility; associated page reuse requires a PDF hash. Fix verification pending.

Final: Ruling: semantic entailment and scientific correctness remain human responsibilities — literal matching consistently retains unverified and cannot certify research acceptance — cost if wrong: a reviewer can still approve a scientifically unsupported claim.

Final: Ruling: withhold physical pages when no unique code-derived PDF correspondence exists — conservative text coordinates are the promised behavior — cost if wrong: some legitimate documents lack convenient page navigation.

Final: Ruling: direct low-level source_map arguments belong to a trusted-caller boundary — managed sessions exclude arbitrary initial fields and rebuild maps from target documents — cost if wrong: custom embeddings must validate their own input maps.

Final: Ruling: local SQLite/provenance records are not authenticated or tamper-proof — documented local research tooling, with no identity service introduced — cost if wrong: a person with local write access can alter records.

Final: Ruling: real provider behavior and Linux kernel ownership remain explicitly unverified locally — no paid calls or unsupported platform claims — cost if wrong: service/platform integration needs its own validation.

Final: Ruling: the reviewer does not duplicate the parent's full coverage run — the parent owns the complete-suite gate and will rerun after fixes — cost if wrong: testing is not independently reproduced by the reviewer.

Ruling: Preserve the existing managed worktree and uncommitted changes, and do not commit or merge — the user's authorization covers concrete local improvements; reviewable work remains in this checkout — cost if wrong: integration into the main checkout requires a separate step.

Final: fixed cache-to-paper identity and PDF association — six regressions observed RED→GREEN; existing and new targeted tests 46/46 passed. Final full suite **300/300 passed**, **85.49% source coverage**, unchanged 80% minimum. Windows/Python 3.11.15 dedicated Conda; no skipped tests. Independent review completed once, no re-review and no deferred minors.

All three tasks complete. Native experiments 001/002 green and tracked artifacts restored; core data/dynamic/scheduling/solver source unchanged. `git diff --check` passes. Full verification output retained locally in `.pytest_cache/workflow-evidence-verification.log`. No commit, merge, push, provider calls or research-algorithm implementation.
