<!-- fjsp-generated-report track=foundation -->
# Phase 2A Sequential Replay Validation

Status: **COMPLETED**; passed episodes 9/9; completed timestamp groups 18.

| Scenario | Rule | Status | Final makespan | Completed groups |
|---|---|---|---:|---:|
| repair_releases_work | fifo | PASS | 9 | 2 |
| repair_releases_work | spt | PASS | 9 | 2 |
| repair_releases_work | eft | PASS | 9 | 2 |
| arrival_then_duration | fifo | PASS | 13 | 3 |
| arrival_then_duration | spt | PASS | 13 | 3 |
| arrival_then_duration | eft | PASS | 13 | 3 |
| simultaneous_updates | fifo | PASS | 12 | 1 |
| simultaneous_updates | spt | PASS | 12 | 1 |
| simultaneous_updates | eft | PASS | 12 | 1 |

## Chronological trace

| Episode | Time | Current event batch | Frozen operations | Planned makespan |
|---|---:|---|---|---:|
| repair_releases_work-fifo | 0 | machine_breakdown | none | 24 |
| repair_releases_work-fifo | 5 | machine_repair | none | 9 |
| repair_releases_work-spt | 0 | machine_breakdown | none | 24 |
| repair_releases_work-spt | 5 | machine_repair | none | 9 |
| repair_releases_work-eft | 0 | machine_breakdown | none | 24 |
| repair_releases_work-eft | 5 | machine_repair | none | 9 |
| arrival_then_duration-fifo | 1 | machine_breakdown | J0O0 | 11 |
| arrival_then_duration-fifo | 4 | job_arrival | J0O0 | 11 |
| arrival_then_duration-fifo | 6 | processing_time_change | J0O0, J0O1, J1O0 | 13 |
| arrival_then_duration-spt | 1 | machine_breakdown | J0O0 | 11 |
| arrival_then_duration-spt | 4 | job_arrival | J0O0 | 11 |
| arrival_then_duration-spt | 6 | processing_time_change | J0O0, J0O1, J1O0 | 13 |
| arrival_then_duration-eft | 1 | machine_breakdown | J0O0 | 11 |
| arrival_then_duration-eft | 4 | job_arrival | J0O0 | 11 |
| arrival_then_duration-eft | 6 | processing_time_change | J0O0, J0O1, J1O0 | 13 |
| simultaneous_updates-fifo | 0 | machine_breakdown, processing_time_change, job_arrival | none | 12 |
| simultaneous_updates-spt | 0 | machine_breakdown, processing_time_change, job_arrival | none | 12 |
| simultaneous_updates-eft | 0 | machine_breakdown, processing_time_change, job_arrival | none | 12 |

## Scope and interpretation

Every episode uses the same initial FIFO plan and its own chronological execution history. Each rule receives only the current state, frozen records and current event batch.
Equal-time events occur before dispatch. Completed and in-process records freeze from the immediately preceding validated schedule, including newly arrived jobs.
Breakdowns are idle-only; processing interruption, transport, AGV, reinforcement learning and maintenance optimization are not modeled.
Unsupported or failed batches stop an episode. Successful prefix traces remain diagnostic and are never accepted as a final result.
These small hand-checkable streams test temporal correctness; they do not establish statistical superiority, dynamic optimality or real-world model fidelity.
Innovation and graduation research goals remain NOT ACHIEVED. No human approval is implied by this development experiment.
