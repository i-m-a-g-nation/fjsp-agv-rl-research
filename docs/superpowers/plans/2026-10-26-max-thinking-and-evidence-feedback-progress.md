# Execution ledger — max thinking and evidence feedback

Base: 360cbfa; branch codex/phase2a-protocol, existing isolated worktree. User authorized improving feedback and requested max thinking. Main remains untouched.

Decision: previous failed live samples used disabled thinking; their evidence is retained unchanged. Official docs confirm enabled thinking plus reasoning_effort=max. Keep existing global budget ceilings; use explicit bounded settings for the new diagnostic, and treat reasoning truncation as a failure.

Configuration implementer observed RED (41 failed / 19 passed), then 60 passed in 3.97s. Added max effort, strict 0..1 repair limit and real SDK wire tests; no credentials accessed by agent. Parent updated only two local `.env` thinking fields, preserved the key line, and native checker confirmed enabled/max plus key presence.

Feedback helper observed 12 missing-feature failures, then 12 passed; pipeline integration observed 5 failures, then the combined focused selection passed 107 tests in 12.05s. Complete regression is running against this initial source state. No live max-thinking provider call yet.

Independent read-only review confirmed request/routing/identity behavior and found one P2: a repair exception could discard the completed initial extraction history. Fix will persist each completed attempt and preserve exception status/history; add failure-path regressions and rerun complete verification after source change. Keep current full-run source frozen until it completes.

Initial complete run finished: 723 passed, 89.62%, 353.55s. Then implemented the P2 fix only after that process finished. Seven added regressions observed RED, then combined focused tests 114 passed / 15.05s. Original exception type and budget behavior remain; failed completed reports persist before the next request and also attach to repair exceptions/degraded metadata. Fresh re-review requested. Final complete regression is now running against frozen final runtime source.

P2 re-review resolved, no new issues. That complete run finished 730 passed / 89.57% /333.09s. Bounded real max diagnostic then used only 2 requests, both HTTP200/stop with enabled/max request fields and nonzero reasoning usage. Known arithmetic4/0/start4, formula and missing RL fields pass, quotes7/7; no repair needed.53.234s, actual completion tokens9975, reserved16384 of24576. Reasoning text/auth headers not saved.

Measured operating correction: max extraction consumed8156/8192 completion tokens; leaving normal local config4096/30 would risk truncation. Added explicit env numeric profile within unchanged hard caps, with defaults still4096/30 and local/template8192/60. Config profile TDD43RED then100GREEN/4.97s; exact old runtime sources archived before this change. Reviewer confirmed no new numerical/identity/secret issue and reminded that default16384 cumulative reservation permits only two8192 calls. Local key preserved; native checker confirms all four profile values. Final profile-inclusive full suite is running, source frozen, no further provider calls planned.

Final profile-inclusive complete regression: **770 passed, 89.57% source coverage, 300.20s**,13third-party Matplotlib/Pyparsing deprecation warnings, unchanged80% threshold. Local output `.pytest_cache/max-evidence-profile-final.log` is ignored. No production changes after this run.

Original max result, driver and exact runtime sources archived; byte hashes verified, hidden reasoning text absent, actual key excluded from all archived files. Existing G1 checker independently accepts reconstructed fixed/joint4/0 plans. Seven extracted claims have seven locations but remain unverified. New documentation links resolve; no AGENTS/contracts/solvers/domain-checker/dependency or prior evidence changes. Main untouched, no merge/push. Non-secret commit ready; local `.env` stays ignored.
