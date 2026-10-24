# Phase 2A experiment protocol implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline, with test-driven-development and one final fresh-context review.

**Goal:** Run a fixed dynamic baseline matrix with inspectable, repeatable evidence and persistent human review.
**Architecture:** src/research validates the protocol and builds common case snapshots, then executes existing reschedulers and emits artifacts. The existing graph gains a deterministic protocol route under its three review gates.
**Tech Stack:** Existing Python/Pydantic/Matplotlib/LangGraph/SQLite; no new dependencies.
**Spec:** docs/superpowers/specs/2026-10-25-phase2a-protocol.md

## Global constraints
- Phase 2A only; existing reschedulers/checkers unchanged.
- Dedicated Conda interpreter verified before Python; no provider/network calls.
- Independent cases, common frozen snapshots, timing repetitions not quality samples.
- Protocol/input/source hashes, new-only output directories and explicit failure records.
- No manufactured human approval; local commits authorized, no merge/push.

## Review focus
- Failures omitted from denominators, comparisons or process exit status.
- Event targeting frozen operations or using different snapshots across rules.
- Changed protocol/benchmark files between reviews and batch execution.
- Repeated timings presented as independent quality evidence or dynamic optimality.
- Output reuse, invalid schedule artifacts and malformed protocol/path inputs.

### Task 1: Protocol and reproducible case snapshots
Files: src/research/__init__.py, src/research/protocol.py, experiments/protocols/phase2a_v1.json, tests/test_phase2a_protocol.py.
Interfaces: load_protocol(path, project_root) returns validated Protocol and resolved relative instance paths; build_case(instance, event_type, seed) returns initial schedule, state, frozen records and event spec.
- [x] Write and run RED tests for strict scope/duplicates/path bounds and hand-checkable event/snapshot behavior.
- [x] Implement protocol validation and generation with existing FIFO/snapshot/state APIs; GREEN targeted tests.
- [x] Commit protocol/case layer with verification evidence.

### Task 2: Batch execution and artifacts
Files: src/research/batch.py, experiments/exp_019_phase2a_protocol.py, tests/test_phase2a_batch.py, .gitignore.
Interfaces: run_protocol(protocol_path, output_dir, project_root, *, expected_protocol_hash=None, expected_input_hashes=None, plots=True) returns manifest summary; describe_protocol returns schema/grid/input fingerprint description.
- [ ] RED tests for identical schedule hashes on replay, dual-checker enforcement/failure rows, timing-repeat aggregation, new-only output and input identity.
- [ ] Implement finite grid, JSON schedules/input snapshots, raw/aggregate CSV and Markdown with failure counts; deterministic representative Gantt generation.
- [ ] CLI exit tests for success/failure/config errors; GREEN targeted suite; commit.

### Task 3: Review integration, research run and acceptance map
Files: src/ai_workflow/langgraph_pipeline.py, sessions.py, session_worker.py; experiments/exp_018_ai_rag_workflow.py; tests/test_protocol_workflow.py; docs/phase2a_experiment_protocol.md; docs/research_acceptance_map.md; relevant README/status docs.
Interfaces: experiment_protocol_path initial session field / --experiment-protocol CLI flag; protocol_hash and benchmark_hashes pinned by session; protocol_result state links audited batch artifacts.
- [ ] RED tests for three gates without RAG/model work, changed protocol/input refusal, no generation on protocol route, research status still not achieved and rejected approvals.
- [ ] Integrate the fixed route, preserving existing selector path and persistent budget/identity checks; GREEN integration tests.
- [ ] Run the declared 243-run matrix, independently replay and compare deterministic artifacts; inspect representative Gantt images; write cautious report and both-track evidence map.
- [ ] Full pytest coverage >=80%, native 001/002, one final review; fix important findings RED→GREEN and rerun full suite. Update docs with actual results and commit tested changes.
