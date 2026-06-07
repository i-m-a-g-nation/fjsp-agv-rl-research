# Phase 2A Dynamic FJSP Plan

Phase 2A adds a minimal dynamic scheduling layer on top of the verified Phase 1
static FJSP base. The goal is to model events and rescheduling without adding
AGV routing, transportation time, reinforcement learning, GNN models, or full
paper reproduction.

## Scope

- Represent dynamic events that occur at a simulation time.
- Maintain a lightweight dynamic state derived from a static `FJSPInstance`.
- Freeze already executed or currently executing schedule records.
- Re-dispatch remaining operations with Phase 1-style feasibility guarantees.
- Return the same `ScheduleResult` type used by Phase 1.
- Check dynamic-only constraints that the static feasibility checker cannot
  see: frozen-record immutability, job release times, and machine unavailable
  windows.
- Apply event sequences through `apply_events()` so experiments reject
  out-of-order dynamic timelines early.
- Extract frozen records from an existing `ScheduleResult` with
  `frozen_records_at_time()`, including in-process operations by default because
  Phase 2A does not model preemption.

## Initial Events

- `MachineBreakdown`: a machine cannot start new operations until a repair time.
- `MachineRepair`: a machine becomes available again at the event time.
- `JobArrival`: one new job is appended to the current FJSP instance.
- `ProcessingTimeChange`: one operation-machine processing time is updated for
  future rescheduling.

## Non-Goals

- No AGV or transport resource.
- No operation interruption model beyond freezing existing records.
- No stochastic simulator loop.
- No RL environment.
- No multi-objective optimization.

## Reused Phase 1 Contracts

- `FJSPInstance` remains the authoritative operation-machine data model.
- `ScheduleRecord` and `ScheduleResult` remain the output representation.
- `check_feasibility()` remains mandatory before returning a rescheduled result.
- `check_dynamic_feasibility()` is also mandatory for Phase 2A reschedules.
- Dispatching remains deterministic unless an explicitly random policy is added
  later.

## First Baseline

`reschedule_from_state()` accepts a `DynamicFJSPState` and frozen records. It
computes job and machine ready times from those records, applies machine
unavailability, dispatches all remaining operations with a simple rule, and
checks the final full schedule with both the Phase 1 feasibility checker and
the Phase 2A dynamic feasibility checker.
