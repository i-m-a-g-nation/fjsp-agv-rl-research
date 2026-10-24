# Execution ledger

Authorization: user said “那你开始” after the concrete four-step proposal. Earlier design questioning is complete; proceed inline using existing architecture. Implementation choices are stated in the spec, not represented as user-supplied details.

Baseline saved: codex/phase2a-protocol, commit 16efbcd. Earlier 300-test/85.49% evidence retained; working tree clean after preservation commit.

Pre-flight: Task 1's Protocol/case interfaces feed Task 2; Task 2's described hashes and batch result feed Task 3. Sessions must pin the new JSON protocol as well as declared benchmark bytes. Fixed protocol route must bypass RAG/generation rather than silently run the old static demonstration.

Task 1 starting: add failing schema and independently hand-checked case tests.

Task 1: 15 new tests RED before src/research existed; schema/case implementation then GREEN with existing dynamic tests, 28 passed. Hand example: breakdown defers to t=3, repairs at t=4, resulting makespan 6; duration change affects only unstarted op 1. Initial/frozen schedules reuse existing checker-backed APIs.

Task 2: 10 batch tests RED before implementation. First integration exposed a file-vs-text loader mismatch and a malformed test header; traced diagnostics and corrected both. Stronger assertions require the intended static/dynamic/exception diagnostics, preventing case-load failures from falsely satisfying solver-failure tests. Protocol+batch suite now 25 passed; 13 third-party Matplotlib/pyparsing deprecation warnings, no failures. Replay digests match; all declared failed rows retained; existing output preserved.
