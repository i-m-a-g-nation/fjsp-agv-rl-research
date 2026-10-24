# Research workflow guards implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Make the existing research assistant fail honestly and distinguish static experiments from the two research deliverables.

**Architecture:** Preserve the current graph and scheduling backends. Add immutable requirement profiles and explicit result dimensions; move generated selectors into a bounded worker process and retain original-instance validation.

**Tech Stack:** Python 3.11, LangGraph, Pydantic, FAISS, pytest, subprocess.

**Spec:** `docs/superpowers/specs/2026-10-24-workflow-guards.md`

## Global constraints
- Use only the dedicated Conda environment through FJSP_CONDA_ENV.
- Remain within Phase 2A; never weaken the scheduling checkers.
- No automatic publication, remote model calls during tests, or new multi-agent orchestration.

## Review focus
- Long abstracts and prose must not become verified full text or invented formulas.
- Provider errors and opt-in fallback must be distinguishable in reports.
- Goal/profile fields supplied by a caller must not bypass fixed requirements.
- Missing benchmark files, infinite loops, and instance mutation must fail clearly.
- Offline feasibility and performance must not certify either research project.

### Task 1: Literature and failure honesty
Files: paper_fetcher.py, schemas.py, config.py, langgraph_pipeline.py; tests/test_workflow_guards.py.
Interfaces: preserve existing public functions; add explicit extraction_method and provider fallback status.
- [x] Add failing tests for long prose, unsupported fallback formulas, and provider outage.
- [x] Run these tests and observe failures.
- [x] Remove length-only full-text promotion and unsupported heuristic claims; fail on provider errors by default and record explicitly allowed fallback.
- [x] Run new tests and existing AI tests.

### Task 2: Track requirements and acceptance
Files: new contracts.py, graph, schemas, RAG metadata, CLI; tests/test_workflow_contracts.py.
Interfaces: get_research_contract(track); build_research_workflow(..., track="foundation"); fixed contract version/hash and deterministic unmet requirements.
- [x] Add failing tests for profile separation, static-only rejection, scope bypass, and unreviewed memory.
- [x] Run tests to observe failures.
- [x] Implement fixed profiles, per-dimension statuses, and track-aware memory; inject requirements directly rather than relying on RAG.
- [x] Verify both tracks cannot claim research completion from static schedules.

### Task 3: Bounded execution and reproducibility
Files: sandbox.py, new sandbox_worker.py, config.py, CLI, dependency manifests; tests/test_workflow_sandbox.py.
Interfaces: evaluate_generated_rule(..., timeout_seconds=10.0) preserves existing result fields and adds explicit quality status.
- [x] Add failing tests for missing data, mutation, forbidden constructs, and timeout.
- [x] Run tests to observe failures.
- [x] Add restricted AST validation and a subprocess deadline; validate outputs against unchanged input instances; fail for missing configured benchmarks.
- [x] Add explicit offline/live CLI modes, track-specific output paths, bounded LLM settings, and declared optional dependencies.

### Task 4: Documentation and verification
- [x] Document profiles, limitations, human review points, and reproducible offline commands.
- [x] Run full pytest with coverage, toy and solver experiments, dynamic chain, and both offline research tracks using temporary output paths.
- [x] Obtain one independent whole-change review, resolve important findings with regression tests, and leave changes reviewable.
