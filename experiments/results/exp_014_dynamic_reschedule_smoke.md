# Phase 2A Dynamic Reschedule Smoke Report

This report summarizes 3 dynamic smoke scenarios. Feasible rows: 3/3.

| scenario | algorithm | makespan | feasible | note |
| --- | --- | --- | --- | --- |
| dynamic_breakdown_1x1 | DynamicEFT(machine_breakdown) | 12 | PASS | DYNAMIC_PASS |
| dynamic_job_arrival_2x1 | DynamicEFT(job_arrival) | 10 | PASS | DYNAMIC_PASS |
| dynamic_multi_event_2x2 | DynamicEFT(multi_event) | 8 | PASS | DYNAMIC_PASS |

Every PASS row is a full ScheduleResult validated by the static Phase 1 feasibility checker and the Phase 2A dynamic checks inside the rescheduling path.
