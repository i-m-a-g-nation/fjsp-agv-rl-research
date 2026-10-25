# Phase 2A closeout implementation plan

> **For agentic workers:** executing-plans inline, TDD for the missing baseline, one fresh final code/domain-design review.

**Goal:** Correct the EAM acceptance gap and deliver a truthful Phase2A handoff plus next-model draft.
**Architecture:** Reuse shared dispatch/checker APIs for EAM; keep research-model design in Markdown and current code in Phase2A.
**Tech Stack:** Existing Python/pytest and local document extraction; no dependencies or providers.
**Spec:** docs/superpowers/specs/2026-10-25-phase2a-closeout.md

## Global constraints
- Current AGENTS Phase2A scope remains authoritative; no future-model implementation.
- Dedicated Conda verification before Python. No fabricated human approvals, contract edits or remote calls.
- EAM's project-specific tie policy explicit; no aliasing of EFT as EAM.
- Existing019/020 evidence unchanged. No inferential statistics or research-completion claims.
- Local tested commits only, no merge/push.

## Review focus
- EAM accidentally ranks finish/processing time or changes FIFO operation priority.
- Tied start times, alternate machine-option order and uniform checker enforcement.
- Closeout claims technical evidence equals human acceptance or omits proposal outcomes.
- Graduation assumptions presented as source requirements; maintenance optionality/window ambiguity.
- Fixed-vs-joint feasible-set reasoning, tardiness arithmetic and result/checker compatibility.

### Task1: Missing EAM baseline
Files: src/solvers/dispatching.py,baselines.py,heuristics.py,__init__.py; experiments001/002; tests/test_eam_baseline.py.
- [x] RED tests for EAM/EFT distinction, available-machine selection, tie/order semantics and compatibility.
- [x] Implement shared-decoder EAM and register native toy comparisons; GREEN targeted tests.

### Task2: Acceptance and model design
Files: docs/phase2a_acceptance.md, docs/graduation_model_draft.md, research_acceptance_map.md and relevant status/README docs.
- [x] Recheck saved artifacts and latest test evidence; map requirements including the corrected EAM gap and unconfirmed human judgments.
- [x] Draft identical-parallel-machine candidate, mandatory maintenance/window semantics, sum tardiness, horizon/checker interfaces and fixed/joint comparison; independently verify small hand schedules.
- [x] One fresh code/domain review; important fixes with regressions or explicit mathematical counterexamples. Full pytest>=80%, native001/002, preserve snapshots; commit verified work. Record pending user choices and remaining research work.
