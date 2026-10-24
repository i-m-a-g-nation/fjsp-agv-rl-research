# Phase 2A fixed baseline experiment

The user approved saving the existing safeguards and implementing a fixed, reproducible Phase 2A experiment and two-track acceptance map. Reuse existing FIFO/SPT/EFT rescheduling; no scheduling/checker changes, new optimizers, paid providers or expanded phase permissions.

## Protocol and comparison

Version 1 uses fattahi1, kacem1 and mk01; independent machine-breakdown/repair-window, job-arrival and processing-time-change cases; seeds 42/43/44; rules fifo/spt/eft; three timing repetitions. This gives 27 cases and 243 runs. Repetitions measure timing variation of deterministic rules, not independent quality samples.

Generate one common initial schedule with the existing dynamic FIFO rule at time zero. Nominal event time is max(1, initial makespan // 3). Freeze completed and in-process operations using the existing snapshot helper. Each case is independent, not an online event stream.

- Breakdown: seeded choice among machines with future scheduled operations. If the chosen machine is currently processing, defer the event to that operation's end. Repair duration is a seeded integer from max(1,C//10) through max(1,C//3), inclusive. No preemption is modeled.
- Arrival: clone a seeded existing job's full route and eligible-machine options; release the one new job at the nominal time.
- Processing-time change: seeded choice of one unstarted initial-schedule operation; increase its scheduled machine option duration to max(old+1,ceil(3*old/2)). Frozen operations remain unchanged.
- Every rule receives the same case state and frozen records; all operations use the existing static and dynamic checkers. Invalid or failed runs retain diagnostic rows and have no accepted makespan.

Store the exact protocol, benchmark bytes/hashes, generated event specs, frozen records, initial and returned schedules, deterministic schedule hashes, raw/aggregate CSV, manifest, report and representative Gantt charts. Plot only first-seed/first-repeat EFT runs, selected in advance. Capture Python/dependency/platform metadata and source fingerprints; runtime is hardware-dependent and excluded from reproducibility hashes. Source and snapshot bytes, not timing, must reproduce.

Protocol schema rejects unknown phase/rules/events, duplicate IDs/paths/seeds and escaping or absolute instance paths. Output directories are new-only; default CLI destinations are unique directories under ignored experiments/runs/. The bounded declared grid is the stopping rule; failed cases/runs remain in artifacts and cause exit 1. No statistical superiority, dynamic optimality, total tardiness or research completion claims.

## Workflow integration

Add a fixed-protocol route to the existing persistent CLI: scope -> prepare input evidence -> evidence review -> execute fixed batch -> conclusion review. This route does not build RAG, call models, or generate code. Protocol/input hashes are pinned by the session and rechecked on resume and execution. Existing literature/selector route remains supported. Three human decisions remain necessary; tests may use clearly identified synthetic decisions, never manufacture approval of a real session.

Standalone Experiment 019 runs only deterministic baseline validation; its completion is not human scientific acceptance. A real managed-session smoke will stop at scope review. Both innovation and graduation remain not achieved after any successful batch.

## Deliverables

A JSON protocol; reusable src/research modules for validation/cases and batch artifacts; thin Experiment 019 CLI; persistent workflow route; regression tests; protocol guide, two-track evidence/acceptance map and one inspected baseline run. Preserve the earlier safeguards in a named codex branch first. Commit local tested work; do not merge or push.
