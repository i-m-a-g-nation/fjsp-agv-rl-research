# Phase 2A Event-File Reschedule Report

This report replays 3 dynamic event JSON files. Feasible rows: 3/3.

| scenario | event file | makespan | feasible | note |
| --- | --- | ---: | --- | --- |
| dynamic_file_multi_event_2x2 | dynamic_events_multi_event.json | 8 | PASS | EVENT_FILE_DYNAMIC_PASS |
| dynamic_file_repair_cycle_1x2 | dynamic_events_repair_cycle.json | 10 | PASS | EVENT_FILE_DYNAMIC_PASS |
| dynamic_file_release_stagger_3x2 | dynamic_events_release_stagger.json | 14 | PASS | EVENT_FILE_DYNAMIC_PASS |

Each PASS row is a full ScheduleResult produced after loading the listed JSON file, applying its events to a compatible dynamic state, and passing both the static and dynamic feasibility gates.
