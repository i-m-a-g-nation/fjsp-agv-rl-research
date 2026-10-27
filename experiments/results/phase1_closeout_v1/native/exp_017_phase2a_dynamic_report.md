# Phase 2A Dynamic Overview Report

This report summarizes the current Phase 2A dynamic FJSP chain: dynamic smoke rescheduling, JSON event-file auditing, and JSON-driven event replay rescheduling.

| gate | passed | total |
| --- | ---: | ---: |
| dynamic smoke reschedules | 3 | 3 |
| event-file audits | 3 | 3 |
| event-file replay reschedules | 3 | 3 |

Overall status: PASS.

## Dynamic Smoke Reschedules

| scenario | algorithm | makespan | feasible | note |
| --- | --- | ---: | --- | --- |
| dynamic_breakdown_1x1 | DynamicEFT(machine_breakdown) | 12 | PASS | DYNAMIC_PASS |
| dynamic_job_arrival_2x1 | DynamicEFT(job_arrival) | 10 | PASS | DYNAMIC_PASS |
| dynamic_multi_event_2x2 | DynamicEFT(multi_event) | 8 | PASS | DYNAMIC_PASS |

## Dynamic Event Files

| file | events | first | last | order | status | note |
| --- | ---: | ---: | ---: | --- | --- | --- |
| dynamic_events_multi_event.json | 3 | 2 | 2 | PASS | PASS | EVENT_FILE_OK |
| dynamic_events_release_stagger.json | 3 | 2 | 5 | PASS | PASS | EVENT_FILE_OK |
| dynamic_events_repair_cycle.json | 3 | 1 | 4 | PASS | PASS | EVENT_FILE_OK |

## Event-File Replay Reschedules

| scenario | algorithm | makespan | feasible | note |
| --- | --- | ---: | --- | --- |
| dynamic_file_multi_event_2x2 | DynamicEFT(dynamic_events_multi_event.json) | 8 | PASS | EVENT_FILE_DYNAMIC_PASS |
| dynamic_file_repair_cycle_1x2 | DynamicEFT(dynamic_events_repair_cycle.json) | 10 | PASS | EVENT_FILE_DYNAMIC_PASS |
| dynamic_file_release_stagger_3x2 | DynamicEFT(dynamic_events_release_stagger.json) | 14 | PASS | EVENT_FILE_DYNAMIC_PASS |

Interpretation note: this overview is a report-only gate. It does not rerun solvers; it expects exp_014, exp_015, and exp_016 CSV artifacts to have been refreshed first.

