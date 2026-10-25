# Graduation G1 data, metric and checker implementation plan

> **For agentic workers:** User explicitly released G1 on2026-10-25. Use executing-plans inline and TDD, with one fresh final review.

**Goal:** Make the confirmed first-edition maintenance assumptions executable as data/metric/legality contracts, without an optimizer.
**Architecture:** Keep existing FJSP ScheduleResult/checker behavior; adapt each production task to one operation on identical machines. Add separate maintenance records and domain validation, never fake production jobs for maintenance.
**Tech Stack:** Existing Python dataclasses/Pydantic/pytest; no new dependency, model API, training, AGV or transport.
**Spec:** docs/graduation_model_draft.md

## Authorization and scope
- User confirmed priority graduation, identical machines, exactly one mandatory maintenance per machine including idle machines, and full-interval window containment.
- Proposed first-edition defaults: one nonpreemptive operation/job, release0, no shared maintenance crew, no setup/transport/fault dynamics. These are explicit design bounds, not facts proven by the screenshot.
- Current AGENTS still says Phase2A dynamic FJSP minimum foundation. The user's subsequent explicit answer “允许，按首版范围实现 G1” releases only this G1 exception. This does not authorize G2 optimization, AGV/RL/transport, or change runtime human approvals.
- G1 excludes CP-SAT models, optimization heuristics, RL and comparative research conclusions. Mathematical examples become manually constructed validation fixtures only.

## Review focus
- Missing/duplicate maintenance, including machines with no production work.
- Maintenance starts inside a window but ends outside, and exact touching boundaries.
- Incorrect tardiness, early/late completion cancellation and wrong instance association.
- Weakening the existing checker or disguising maintenance as additional production jobs.
- Invalid integer data, silently ignored unsupported features and invalid schedules counted as valid metric samples.

### Task1 — typed data and ScheduleResult compatibility
Files to create: src/graduation/__init__.py, src/graduation/data.py, src/graduation/result.py, tests/test_graduation_data.py.

Interfaces:
- ProductionTask(job_id:int, processing_time:int, due_date:int), immutable; task IDs0..n-1, p>0,d>=0, n>=1.
- MaintenanceRequirement(machine_id:int,duration:int,window_start:int,window_end:int,fixed_start:int|None), immutable; exactly one spec per machine0..m-1, m>=1, duration>0,0<=start<end, duration<=end-start. fixed_start, when present, must fit the complete interval.
- ParallelMaintenanceInstance(tasks:tuple, num_machines:int, maintenance:tuple), identical-machine first edition; reject nonintegers/bools, duplicate IDs, missing machines and unsupported nonzero release/setup/crew fields instead of ignoring them.
- to_fjsp_instance(data)->FJSPInstance, oneop/job and each machine option uses the same p_j.
- MaintenanceRecord(machine_id,start,end,duration); MaintenanceScheduleResult(ScheduleResult) adds maintenance_records:list and total_tardiness:int|None. Maintain all inherited production fields and makespan semantics.

- [x] RED tests for invalid/duplicate/missing data, mandatory idle-machine maintenance specs, full-window fit, identical production mapping and isinstance(result,ScheduleResult).
- [x] Implement pure data/result contracts; GREEN targeted tests. No solver or auto-filled scientific result.

### Task2 — independently calculated total tardiness
Files: src/graduation/metrics.py, tests/test_graduation_metrics.py.

Interface: calculate_total_tardiness(data,result:ScheduleResult)->int. First verify target production-instance equality and the unmodified static feasibility checker; invalid/missing/duplicate production schedules raise ValueError. Then sum max(0,C_j-d_j), with each job's sole operation end as C_j. Do not repair makespan/records inside validation or return a partial metric.

- [x] RED witnesses: one-machine fixed scheduleT=4, jointT=0; two-machine fixedT=6,jointT=0; one early and one tardy job must not cancel (C=(4,6),d=(10,0) gives6); wrong/partial instance rejected.
- [x] Implement exact metric; GREEN tests using hand-constructed schedules, not a solver under test.

### Task3 — domain legality conjunction
Files: src/graduation/feasibility.py, tests/test_graduation_feasibility.py, docs/graduation_g1_validation.md.

Interface: check_parallel_maintenance_feasibility(result:MaintenanceScheduleResult,data,*,mode:'fixed'|'joint')->tuple[bool,list[MaintenanceViolation]]. Mode is explicit. Validate record shape/types defensively, target instance, and existing static checker; never weaken or bypass it. Check exactly one maintenance per machine, correct duration/end-start, complete-window containment, production/maintenance overlap, fixed_start match in fixed mode (missing fixed_start is invalid configuration), and independent total_tardiness agreement. Invalid rows retain diagnostics and never become valid metrics.

Violation categories: INSTANCE_MISMATCH, BASE_SCHEDULE_INVALID, MISSING_MAINTENANCE, DUPLICATE_MAINTENANCE, INVALID_MAINTENANCE_MACHINE, INVALID_MAINTENANCE_TIME, MAINTENANCE_DURATION_MISMATCH, MAINTENANCE_OUTSIDE_WINDOW, MAINTENANCE_PRODUCTION_OVERLAP, FIXED_START_MISMATCH, TOTAL_TARDINESS_MISMATCH. Diagnostics may refine these without changing rejection semantics.

- [x] RED: positive hand schedules, end==window_end accepted, production end==maintenance start accepted, maintenance end==production start accepted, starts-inside/ends-outside rejected, idle-machine maintenance omission rejected, duplicate/invalid IDs, overlap, wrong fixed start, wrong total and malformed/nonfinite times rejected with diagnostics.
- [x] Implement domain checks plus human-readable fixture report; GREEN targeted and whole suite. This does not certify optimized maintenance decisions or research completion.
- [x] On authorized completion: native001/002, full coverage>=80%, one fresh review, important fixes with regressions, commit tested work; leave AGV/RL/transport scope unchanged and document that G2 optimization remains future work.
