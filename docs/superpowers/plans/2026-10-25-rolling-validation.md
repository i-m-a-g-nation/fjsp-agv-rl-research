# Sequential Phase 2A validation implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: executing-plans inline, TDD and one final fresh-context review.

**Goal:** Validate preservation of actual executed prefixes across multiple rescheduling decisions.
**Architecture:** A simulation harness groups timestamps, snapshots the last validated ScheduleResult, applies the current event batch and calls the existing rescheduler. A thin Experiment020 emits chronological evidence for three hand-derived streams and existing rules.
**Tech Stack:** Existing Python dataclasses, dynamic/checker APIs and JSON/CSV; no new dependencies.
**Spec:** docs/superpowers/specs/2026-10-25-rolling-validation.md

## Global constraints
- Phase2A only; no changes to old rule selection, state transitions or checker strength.
- Dedicated Conda verified before Python. No network/models or artificial real approvals.
- Event batches precede dispatch at equal time; no future-event information passed to a rescheduler.
- Failure stops an episode and removes its accepted final result, while retaining prefix evidence.
- Prior fixed protocol/evidence untouched; local commits only.

## Review focus
- Dropping previously executed work by freezing only the original schedule.
- Same-time events accidentally causing dispatch between updates.
- Changing frozen durations or accepting an idle-only breakdown on a busy machine.
- Future repairs changing earlier schedules, or failures exposing prefix schedules as final success.
- Trace mutation, incomplete failed episode records and output overwrite.

### Task 1: Sequential replay
Files: src/dynamic/rolling.py, tests/test_dynamic_rolling.py.
Interfaces: replay_events(instance, events, rule='eft') -> ReplayEpisode; episode contains initial ScheduleResult, successful ReplayStep tuple, final_result or None, failed_events and error. Each step contains timestamp events, state, frozen records and full ScheduleResult.
- [x] RED tests for hand-derived makespans, frozen induction, grouped simultaneous events, prefix/future independence, invalid streams and failure result semantics.
- [x] Implement via existing helpers; GREEN targeted dynamic suite.

### Task 2: Experiment020 and evidence
Files: experiments/exp_020_sequential_reschedule.py, tests/test_sequential_experiment.py, docs/phase2a_sequential_validation.md, .gitattributes, README/status/experiment docs.
Interfaces: run_experiment(output_dir) -> manifest; CLI default unique output under ignored experiments/runs. All 9 episodes and each chronological step exported.
- [x] RED tests for the declared 9 episodes/18 steps, reproducible schedule/trace digest, rejected stream retained, CSV/CLI failure and new-only output.
- [x] Implement export and report; run 9 episodes and independent replay; manually inspect chronological records.
- [ ] Full coverage>=80%, native001/002, one fresh review; Important fixes RED→GREEN and full suite. Commit verified source, regenerate saved evidence against source revision, verify Git bytes, update docs and commit artifacts.
