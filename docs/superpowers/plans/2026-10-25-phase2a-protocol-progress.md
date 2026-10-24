# Execution ledger

Authorization: user said “那你开始” after the concrete four-step proposal. Earlier design questioning is complete; proceed inline using existing architecture. Implementation choices are stated in the spec, not represented as user-supplied details.

Baseline saved: codex/phase2a-protocol, commit 16efbcd. Earlier 300-test/85.49% evidence retained; working tree clean after preservation commit.

Pre-flight: Task 1's Protocol/case interfaces feed Task 2; Task 2's described hashes and batch result feed Task 3. Sessions must pin the new JSON protocol as well as declared benchmark bytes. Fixed protocol route must bypass RAG/generation rather than silently run the old static demonstration.

Task 1 starting: add failing schema and independently hand-checked case tests.

Task 1: 15 new tests RED before src/research existed; schema/case implementation then GREEN with existing dynamic tests, 28 passed. Hand example: breakdown defers to t=3, repairs at t=4, resulting makespan 6; duration change affects only unstarted op 1. Initial/frozen schedules reuse existing checker-backed APIs.

Task 2: 10 batch tests RED before implementation. First integration exposed a file-vs-text loader mismatch and a malformed test header; traced diagnostics and corrected both. Stronger assertions require the intended static/dynamic/exception diagnostics, preventing case-load failures from falsely satisfying solver-failure tests. Protocol+batch suite now 25 passed; 13 third-party Matplotlib/pyparsing deprecation warnings, no failures. Replay digests match; all declared failed rows retained; existing output preserved.

Task 3: 9 integration tests RED for absent protocol route/CLI/session binding (two test hook-name errors corrected before observing the actual missing payload). Fixed route and existing workflow gates/CLI then passed 22 tests. Real first matrix: 243/243 feasible; preserved as an ignored exploratory run, not final evidence after subsequent source changes.

Additional batch checks: identical events from different seeds and valid-but-varying repeated schedules observed RED before adding unique-case and nonreproducible-group counts. Deterministic digest now binds generated case snapshots as well as accepted schedules.

Ruling: “independent cases” means each event starts from the original initial schedule, not statistical independence — expose actual unique snapshot count and do not infer inferential sample size from seeds/repeats — cost if wrong: this small protocol cannot support significance or generalization claims.

Pre-review verification: full suite 336 passed, 87.82% coverage (80% minimum unchanged); 13 Matplotlib/pyparsing deprecation warnings. Native 001/002 green, tracked artifacts restored; dynamic/scheduling/checker/solver modules unchanged. Native 243-run matrix and separate-directory replay match case and schedule digests; 27 configurations produce 23 unique snapshots. Inspected two representative Gantt charts.

Independent review: one Important malformed-result serialization boundary; no Critical or Minor findings requiring a change. Three regressions (NaN field, unserializable field, malformed record) observed RED: the original batch stopped after its first corrupt result. Fix adds bounded diagnostic-only serialization, resets acceptance/hash on every run exception, and continues the full grid. Targeted batch suite 15 passed after fix; final complete suite pending.

Final: Ruling: reuse the existing Gantt renderer and document crowded mk01 labels — numerical JSON/CSV remain authoritative and the charts are not publication figures — cost if wrong: dense short-operation labels require consulting numerical artifacts.

Final: Ruling: preserve separate session-lifecycle and experiment-result statuses — an approved conclusion ends the session even for a failed experiment; eval_passed remains false and CLI exits 1 — cost if wrong: API consumers must inspect the experiment result, not lifecycle COMPLETED alone.

Final: Ruling: keep new optimizers, continuous event simulation and research superiority claims outside Phase 2A — user approved fixed baseline validation with existing algorithms — cost if wrong: neither innovation nor graduation is completed by this increment.

Final: fixed malformed-result diagnostics — three regressions RED→GREEN; targeted batch 15/15; final full suite **339/339**, **87.85%** coverage, 13 upstream deprecation warnings, no skipped cases. Native post-fix matrix and replay remain 243/243 and all registered artifacts verify. Finalization: commit source, regenerate saved evidence against that committed source revision, prepare a real scope-pause without approving it, then commit artifacts and final record.
