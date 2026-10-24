# Persistent review and runtime budgets implementation plan

> **For agentic workers:** Use superpowers:executing-plans and test-driven-development. This continues the user-approved workflow improvements in the existing managed worktree.

**Goal:** Persist three human review gates and enforce cumulative active runtime, provider-call, and output-token reservation limits across resumes.

**Architecture:** LangGraph SQLite checkpoints preserve graph state. A local session runner pins the contract, input, code and configuration; an outer process supervisor bounds each active segment and records consumed time. SQLite budget reservations are committed before external calls and cannot be reset on resume. Human waiting consumes no active execution budget.

**Constraints:** Phase 2A only; no new research algorithms. Do not pass credentials into checkpoints, reports or selector workers. Human approval acknowledges the reviewed artifact, not research completion. Preserve prior uncommitted changes.

**Review focus:** reusing decisions after content changes; provider-budget exceptions entering fallback; concurrent resumes; process descendants after timeout; rebuilding RAG or resetting counters on resume; credentials in persistent state.

### Task 1 — persistent budget
- [x] Write and observe failing tests for invalid limits, cumulative reservations, and deadlines.
- [x] Implement `BudgetLimits`, `RunBudget`, `BudgetExceeded`; integrate provider reservations without hidden fallback.

### Task 2 — persistent human gates
- [x] Write and observe failing tests for scope/evidence/conclusion pauses, reject, invalid decisions, and reopening SQLite checkpoints.
- [x] Add separate review nodes and immutable artifact hashes; restore without rerunning completed extraction/experiments.

### Task 3 — supervised session entry
- [x] Write and observe failing tests for process timeout, restart, mismatched input/config/code, and CLI pending/resume status.
- [x] Implement isolated active segments, process-tree cleanup, exclusive local session access, sanitized persistence, and cumulative wall-clock accounting.
- [x] Update CLI and research dependencies; use persistent review for all CLI tracks and retain the low-level graph API for compatibility, per the execution ledger ruling.

### Task 4 — verification and documentation
- [x] Run complete tests with coverage >=80%, core static/dynamic checks, and offline start/reject/approve/resume flows.
- [x] Obtain one independent review, fix important findings with RED→GREEN tests, and update usage/evidence records.
