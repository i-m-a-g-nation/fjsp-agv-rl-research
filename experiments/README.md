# Experiments

This directory contains static, dynamic, graduation and research-workflow experiments. Project status and the next step are maintained in [START_HERE.md](../START_HERE.md); this page describes reproducible entry points.

Use the dedicated Conda environment from the [setup guide](../README.md#environment-and-checks), never `base`. Before running the examples below, verify the interpreter:

```powershell
.\.conda-env\python.exe -c "import sys; print(sys.executable)"
```

The printed path must belong to `.conda-env` or the environment selected by `FJSP_CONDA_ENV`. For a custom environment, replace `.\.conda-env\python.exe` in the examples with that environment's Python. Run scripts from the repository root.

| Purpose | Entry points | Guide |
|---|---|---|
| Static baselines, benchmark and solver checks | `exp_001`–`exp_013` | Detailed examples below; [Phase 1 reproduction](../docs/reproducibility_phase1.md) |
| Dynamic smoke, event audit and report | `exp_014`–`exp_017` | Detailed examples below; [dynamic checklist](../docs/phase2a_acceptance.md) |
| Persistent human-reviewed execution | [`exp_018`](exp_018_ai_rag_workflow.py) | [Research workflow](../docs/research_workflow.md) |
| Fixed dynamic protocol and sequential replay | [`exp_019`](exp_019_phase2a_protocol.py), [`exp_020`](exp_020_sequential_reschedule.py) | [Protocol](../docs/phase2a_experiment_protocol.md), [sequential replay](../docs/phase2a_sequential_validation.md) |
| Graduation reference solvers and rules | [`exp_021`](exp_021_graduation_solver_check.py), [`exp_022`](exp_022_graduation_rule_smoke.py) | [G2](../docs/graduation_g2_validation.md), [R2](../docs/graduation_r2_validation.md) |
| Paper/code evidence extraction and review | [`exp_023`](exp_023_paper_code_validation.py) | [Field extraction](../docs/paper_field_validation.md), [state semantics](../docs/paper_state_semantic_validation.md) |
| Observation encoding, policy pilot and validation iteration | [`exp_024`](exp_024_state_encoding_check.py), [`exp_025`](exp_025_neural_policy_pilot.py), [`exp_026`](exp_026_validation_iteration.py) | [Encoding](../docs/graduation_state_encoding_validation.md), [policy pilot](../docs/graduation_neural_policy_pilot.md), [validation iteration](../docs/graduation_validation_iteration.md) |
| Audit / controlled-template controller | [`exp_027`](exp_027_research_controller.py) | [Profiles, commands and boundaries](../docs/research_controller_validation.md) |

**Recorded result tables and validation reports are snapshots of the stated inputs, source and settings.** They are examples for reproduction, not a claim that the latest checkout has just passed validation. Timed CP-SAT results may vary; only `OPTIMAL` proves local optimality. Preserve prior outputs and use a new run directory when the script supports one. Development plans in [`docs/superpowers/`](../docs/superpowers/) are history, not required setup reading.

After Phase 1 hardening, `exp_001`–`exp_004` default to a fresh directory under `experiments/runs/`; use `--output-dir` to choose a new directory. Their artifact names below are relative to that directory. Schedule CSVs now have a sibling `.evidence.json` containing the original instance, complete schedule, configuration and provenance. Existing CSV/evidence pairs are never overwritten. For later scripts with historical default paths, select fresh `--output`, `--runs-output` and/or `--summary-output` paths as exposed by `--help`; the [Phase 1 guide](../docs/reproducibility_phase1.md) gives a complete example.

The shared local/CI entry is `python scripts/check_experiments.py`. Add `--heavy` for 005/009/010/011/013 with fresh report inputs, or `--heavy --max-files 1` for a declared small sample. Sampling saves its instance hashes and matching BKS table before running; it never derives the denominator from successful rows. These are input snapshots, not a lock against concurrent file edits. EAM is included once in the matrix and quality report, under `EarliestAvailableMachine`.

## `exp_001_toy_instance.py`

Runs heuristic baselines on the toy 3 jobs x 3 machines FJSP instance.

Algorithms:

- FIFO
- SPT
- EarliestAvailableMachine (FIFO operation, then earliest feasible start / machine-ID tie)
- EarliestFinishTime
- Random with seeds 42, 123, and 999

Run:

```powershell
.\.conda-env\python.exe experiments\exp_001_toy_instance.py
```

Expected output:

| Algorithm | Makespan |
|---|---:|
| FIFO | 14 |
| SPT | 13 |
| EarliestAvailableMachine | 11 |
| EarliestFinishTime | 13 |
| Random(s=42) | 14 |
| Random(s=123) | 14 |
| Random(s=999) | 20 |

Artifacts:

- `exp_001_gantt_latest.png`: Gantt output within this run's directory
- `exp_001_toy_instance.csv`: normalized experiment records
- `exp_001_toy_instance.evidence.json`: complete saved schedules and provenance

Exit code: `0` when all schedules pass feasibility checking, `1` otherwise.

## `exp_002_solver_check.py`

Compares heuristic baselines with the OR-Tools CP-SAT baseline on the same toy instance.

Run:

```powershell
.\.conda-env\python.exe experiments\exp_002_solver_check.py
```

Expected output:

| Algorithm | Makespan | Note |
|---|---:|---|
| FIFO | 14 | HEURISTIC |
| SPT | 13 | HEURISTIC |
| EarliestAvailableMachine | 11 | HEURISTIC |
| EarliestFinishTime | 13 | HEURISTIC |
| Random(42) | 14 | HEURISTIC |
| CP-SAT(tl=30s) | 11 | CP-SAT optimal |

If CP-SAT returns `FEASIBLE` rather than `OPTIMAL`, the experiment reports it as a feasible reference solution, not as an optimum.

CSV artifact:

- `exp_002_solver_check.csv` and `exp_002_solver_check.evidence.json`

Exit code: `0` when all algorithms pass feasibility checking and no solver errors occur, `1` otherwise.

## `exp_003_dispatching_rules.py`

Runs the strict dispatching-rule variants on the same toy instance.

Algorithms:

- DispatchFIFO: choose the earliest ready operation, then choose its earliest-finish eligible machine
- DispatchEAM: choose the earliest ready operation, then the smallest `(feasible start, machine ID)` eligible machine
- DispatchSPT: choose the ready operation-machine pair with the shortest processing time
- DispatchEFT: choose the ready operation-machine pair with the earliest finish time
- DispatchMWKR: choose the ready job with most remaining route work, then choose its earliest-finish eligible machine
- DispatchMOPNR: choose the ready job with most operations remaining, then choose its earliest-finish eligible machine
- DispatchRandom(42): choose a ready operation-machine pair with a reproducible random seed

Run:

```powershell
.\.conda-env\python.exe experiments\exp_003_dispatching_rules.py
```

Expected output:

| Algorithm | Feasible |
|---|---|
| DispatchFIFO | PASS |
| DispatchEAM | PASS |
| DispatchSPT | PASS |
| DispatchEFT | PASS |
| DispatchMWKR | PASS |
| DispatchMOPNR | PASS |
| DispatchRandom(42) | PASS |

CSV artifact:

- `exp_003_dispatching_rules.csv` and `exp_003_dispatching_rules.evidence.json`

Exit code: `0` when all strict dispatching rules pass feasibility checking, `1` otherwise.

## `exp_004_benchmark_smoke.py`

Loads small benchmark-format instances from `instances/` and runs selected
simple baselines, strict dispatching rules, and CP-SAT.

Input files:

- `instances/toy_3x3_0based.fjs`
- `instances/tiny_2x2_1based.fjs`

Run:

```powershell
.\.conda-env\python.exe experiments\exp_004_benchmark_smoke.py
```

Expected behavior:

- both files load successfully
- 1-based machine ids are normalized to 0-based ids
- every algorithm result passes `check_feasibility()`
- CP-SAT reports `OPTIMAL` or `FEASIBLE` through `ScheduleResult.solver_status`

CSV artifact:

- `exp_004_benchmark_smoke.csv` and `exp_004_benchmark_smoke.evidence.json`

Exit code: `0` when all benchmark smoke schedules pass feasibility checking, `1` otherwise.

## `exp_005_benchmark_batch.py`

Recursively discovers benchmark files and runs the Phase 1 static FJSP suite.
Unlike the fixed smoke experiment, this entry point is intended to scale to
tracked benchmark collections with nested directories.

Run:

```powershell
.\.conda-env\python.exe experiments\exp_005_benchmark_batch.py
```

Useful controls:

```powershell
.\.conda-env\python.exe experiments\exp_005_benchmark_batch.py --max-files 10
.\.conda-env\python.exe experiments\exp_005_benchmark_batch.py --skip-cp-sat
.\.conda-env\python.exe experiments\exp_005_benchmark_batch.py --cp-sat-time-limit 30
```

Behavior:

- recursively discovers `*.fjs` files in stable path order
- records loader failures as `LOAD` rows instead of silently dropping files
- runs FIFO, SPT, EarliestAvailableMachine, DispatchFIFO, DispatchSPT, DispatchEFT, DispatchMWKR, and DispatchMOPNR
- runs CP-SAT by default with a configurable per-instance time limit
- writes `results/exp_005_benchmark_batch.csv`

The default batch currently includes the repository-local smoke files and the
tracked FJSPLib subset documented in `instances/README.md`:

| Upstream instance | Size | CP-SAT result | FJSPLib UB |
|---|---:|---:|---:|
| Fattahi `fattahi1` | 2 x 2 | 66 `OPTIMAL` | 66 |
| Fattahi `fattahi4` | 3 x 2 | 355 `OPTIMAL` | 355 |
| Fattahi `fattahi5` | 3 x 2 | 119 `OPTIMAL` | 119 |
| Fattahi `fattahi6` | 3 x 3 | 320 `OPTIMAL` | 320 |
| Hurink edata `ft06` | 6 x 6 | 55 `OPTIMAL` | 55 |
| Brandimarte `mk01` | 10 x 6 | 40 `OPTIMAL` | 40 |
| Brandimarte `mk03` | 15 x 8 | 204 `FEASIBLE` | 204 |
| Brandimarte `mk05` | 15 x 4 | 175 `FEASIBLE` | 172 |
| Brandimarte `mk06` | 10 x 15 | 74 `FEASIBLE` | 57 |
| Brandimarte `mk07` | 20 x 5 | 159 `FEASIBLE` | 139 |
| Brandimarte `mk08` | 20 x 10 | 523 `FEASIBLE` | 523 |
| Brandimarte `mk09` | 20 x 10 | 340 `FEASIBLE` | 307 |
| Kacem `kacem4` | 15 x 10 | 13 `FEASIBLE` | 11 |

`mk03` intentionally exercises time-limited solver semantics: matching the
upstream BKS does not become a local optimality proof unless CP-SAT reports
`OPTIMAL`.

Exit code: `0` when all files load and all schedules pass feasibility checking,
`1` when a loader or solver run fails, and `2` for invalid configuration or an
empty discovery result.

## `exp_006_cpsat_time_limit_sweep.py`

Runs tracked Brandimarte `mk03` under several CP-SAT time limits and records
status, objective bound, relative gap, and solver wall time. The sweep defaults
to one worker to reduce parallel-search noise during comparisons.

Run:

```powershell
.\.conda-env\python.exe experiments\exp_006_cpsat_time_limit_sweep.py
```

Useful controls:

```powershell
.\.conda-env\python.exe experiments\exp_006_cpsat_time_limit_sweep.py --time-limits 1 5 30
.\.conda-env\python.exe experiments\exp_006_cpsat_time_limit_sweep.py --num-workers 4
```

Tracked default result:

| Time limit | Makespan | Status | Bound | Relative gap |
|---:|---:|---|---:|---:|
| 1s | 417 | `FEASIBLE` | 20 | 0.952038 |
| 3s | 285 | `FEASIBLE` | 20 | 0.929825 |
| 10s | 220 | `FEASIBLE` | 20 | 0.909091 |

CSV artifact:

- `results/exp_006_cpsat_time_limit_sweep.csv`

Exit code: `0` when every returned schedule passes feasibility checking, `1`
for solver or schedule failures, and `2` for invalid configuration.

## `exp_007_cpsat_worker_sweep.py`

Runs tracked Brandimarte `mk03` with a fixed 10-second time limit and varies the
CP-SAT worker configuration. Worker count `0` means the solver's automatic
configuration.

Run:

```powershell
.\.conda-env\python.exe experiments\exp_007_cpsat_worker_sweep.py
```

Useful controls:

```powershell
.\.conda-env\python.exe experiments\exp_007_cpsat_worker_sweep.py --worker-counts 1 2 4 0
.\.conda-env\python.exe experiments\exp_007_cpsat_worker_sweep.py --time-limit 30
```

Tracked default result:

| Workers | Makespan | Status | Bound | Relative gap |
|---:|---:|---|---:|---:|
| 1 | 220 | `FEASIBLE` | 20 | 0.909091 |
| 2 | 207 | `FEASIBLE` | 20 | 0.903382 |
| 4 | 207 | `FEASIBLE` | 20 | 0.903382 |
| auto | 209 | `FEASIBLE` | 75 | 0.641148 |

CSV artifact:

- `results/exp_007_cpsat_worker_sweep.csv`

Every returned schedule must pass feasibility checking. These values are one
timed observation, not a stable ranking of worker configurations.

## `exp_008_cpsat_worker_repeats.py`

Repeats each tracked `mk03` worker-count configuration under the same
10-second limit. Every raw schedule is independently feasibility checked
before the script reports aggregate statistics.

Run:

```powershell
.\.conda-env\python.exe experiments\exp_008_cpsat_worker_repeats.py
```

Useful controls:

```powershell
.\.conda-env\python.exe experiments\exp_008_cpsat_worker_repeats.py --repeats 5
.\.conda-env\python.exe experiments\exp_008_cpsat_worker_repeats.py --time-limit 30 --worker-counts 1 4 0
```

Tracked default aggregate result:

| Workers | Feasible runs | Best makespan | Mean makespan | Population std. dev. | Best bound | Best gap |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3 / 3 | 220 | 220.000000 | 0.000000 | 20 | 0.909091 |
| 2 | 3 / 3 | 204 | 204.000000 | 0.000000 | 20 | 0.901961 |
| 4 | 3 / 3 | 204 | 204.000000 | 0.000000 | 21 | 0.897059 |
| auto | 3 / 3 | 204 | 204.000000 | 0.000000 | 88 | 0.568627 |

CSV artifacts:

- `results/exp_008_cpsat_worker_repeats_runs.csv`
- `results/exp_008_cpsat_worker_repeats_summary.csv`

All 12 tracked schedules passed feasibility checking. Reaching the FJSPLib UB
does not become a local optimality proof while CP-SAT reports `FEASIBLE`.

## `exp_009_cpsat_benchmark_matrix.py`

Recursively discovers the tracked static FJSPLib subset and runs a controlled
repeated CP-SAT matrix. The defaults compare one worker with the solver's
automatic configuration, repeat each configuration twice, and use a 3-second
per-run limit.

Run:

```powershell
.\.conda-env\python.exe experiments\exp_009_cpsat_benchmark_matrix.py
```

Useful controls:

```powershell
.\.conda-env\python.exe experiments\exp_009_cpsat_benchmark_matrix.py --max-files 2
.\.conda-env\python.exe experiments\exp_009_cpsat_benchmark_matrix.py --repeats 3 --time-limit 10 --worker-counts 1 4 0
```

Tracked default worker summary:

| Workers | Instances | Feasible rows | Proved-optimal rows | Mean best makespan | Mean best bound | Mean best gap |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 30 | 30 | 12 | 674.333 | 258.067 | 0.451173 |
| auto | 30 | 30 | 12 | 590.367 | 358.900 | 0.273244 |

CSV artifacts:

- `results/exp_009_cpsat_benchmark_matrix_runs.csv`
- `results/exp_009_cpsat_benchmark_matrix_summary.csv`

All 120 schedules passed feasibility checking. Loader failures and solver
failures remain visible in the raw CSV and process exit code. Use
`exp_013_cpsat_report.py` for a readable Markdown interpretation of these
aggregates.

## `exp_010_heuristic_benchmark_matrix.py`

Recursively discovers the tracked static FJSPLib subset and evaluates Phase 1
heuristics. Deterministic rules run once per instance. `Random` and
`DispatchRandom` use fixed seeds `42`, `123`, and `999`, so their spread is
reproducible and auditable.

Run:

```powershell
.\.conda-env\python.exe experiments\exp_010_heuristic_benchmark_matrix.py
```

Useful controls:

```powershell
.\.conda-env\python.exe experiments\exp_010_heuristic_benchmark_matrix.py --max-files 2
.\.conda-env\python.exe experiments\exp_010_heuristic_benchmark_matrix.py --seeds 7 42 123
```

Tracked default summary:

| Instance | Best deterministic rule | Makespan | Random range | DispatchRandom range |
|---|---|---:|---:|---:|
| `mk01` | DispatchMWKR | 44 | 148-165 | 92-125 |
| `mk02` | DispatchMWKR | 30 | 134-169 | 86-113 |
| `mk03` | DispatchFIFO / DispatchMWKR | 204 | 1086-1206 | 488-563 |
| `mk04` | DispatchFIFO | 77 | 279-292 | 143-177 |
| `mk05` | DispatchFIFO | 185 | 541-584 | 287-323 |
| `mk06` | DispatchMWKR | 67 | 594-673 | 222-238 |
| `mk07` | DispatchMOPNR | 160 | 689-854 | 345-427 |
| `mk08` | DispatchFIFO | 531 | 2306-2560 | 755-916 |
| `mk09` | DispatchFIFO | 341 | 2071-2200 | 817-960 |
| `mk10` | DispatchMWKR | 243 | 1973-2087 | 610-710 |
| `mt10c1` | DispatchMOPNR | 1225 | 3348-3394 | 1446-1728 |
| `mt10cc` | DispatchMWKR | 1121 | 3348-3394 | 1597-1841 |
| `mt10x` | EarliestFinishTime / DispatchEFT | 1173 | 3095-3394 | 1744-1849 |
| `01a` | DispatchFIFO | 3056 | 10212-10398 | 4132-4525 |
| `02a` | DispatchFIFO | 2443 | 10010-10305 | 4401-4804 |
| `03a` | DispatchFIFO | 2413 | 10025-10207 | 4197-4898 |
| `04a` | DispatchMOPNR | 3070 | 10177-10380 | 4090-4495 |
| `fattahi1` | DispatchMWKR | 66 | 86-135 | 86-135 |
| `fattahi2` | DispatchFIFO / DispatchMWKR | 107 | 107-192 | 107-149 |
| `fattahi3` | DispatchFIFO / DispatchMOPNR | 221 | 298-442 | 221-361 |
| `fattahi4` | DispatchFIFO / DispatchMWKR / DispatchMOPNR | 367 | 409-699 | 407-626 |
| `fattahi5` | DispatchFIFO | 119 | 207-246 | 150-220 |
| `fattahi6` | EarliestFinishTime / DispatchEFT | 330 | 557-707 | 470-557 |
| `fattahi7` | EarliestFinishTime / DispatchFIFO / DispatchSPT / DispatchEFT / DispatchMOPNR | 397 | 491-595 | 462-598 |
| `fattahi8` | EarliestFinishTime / DispatchEFT | 273 | 275-317 | 341-450 |
| edata `ft06` | DispatchFIFO | 55 | 146-152 | 71-112 |
| `kacem1` | DispatchFIFO | 11 | 27-82 | 26-44 |
| `kacem2` | DispatchMWKR | 12 | 62-102 | 50-88 |
| `kacem3` | DispatchFIFO / DispatchMWKR / DispatchMOPNR | 8 | 42-77 | 50-72 |
| `kacem4` | DispatchMWKR | 12 | 114-159 | 71-138 |

CSV artifacts:

- `results/exp_010_heuristic_benchmark_matrix_runs.csv`
- `results/exp_010_heuristic_benchmark_matrix_summary.csv`

All 420 schedules passed feasibility checking. Loader and solver failures remain
visible in the raw CSV and process exit code.

## `exp_011_heuristic_quality_report.py`

Reads the Experiment 010 family summary and the structured upstream references
in `instances/fjsplib_bks.csv`. For every family and instance, it computes:

```text
gap_UB = (makespan - FJSPLib_UB) / FJSPLib_UB
```

Run:

```powershell
.\.conda-env\python.exe experiments\exp_011_heuristic_quality_report.py
```

Tracked family summary:

| Algorithm family | Mean best gap | Maximum best gap |
|---|---:|---:|
| DispatchFIFO | 0.151281 | 0.370370 |
| DispatchMWKR | 0.158760 | 0.364924 |
| DispatchMOPNR | 0.193880 | 0.466667 |
| EarliestFinishTime | 0.392423 | 1.384615 |
| DispatchEFT | 0.405199 | 1.384615 |

CSV artifacts:

- `results/exp_011_heuristic_quality_rows.csv`
- `results/exp_011_heuristic_quality_families.csv`

The report rejects missing reference rows, missing summarized instances, and
values below upstream lower bounds. A feasible schedule may improve an open
upper bound; upstream reference bounds are not local optimality proofs.

## `exp_012_benchmark_metadata_audit.py`

Recursively discovers tracked static FJSPLib files, matches them one-to-one
with `instances/fjsplib_bks.csv`, and loads every discovered instance.

Run:

```powershell
.\.conda-env\python.exe experiments\exp_012_benchmark_metadata_audit.py
```

CSV artifact:

- `results/exp_012_benchmark_metadata_audit.csv`

The script returns exit code `1` when any tracked file, BKS metadata row, or
loadable instance is missing. All thirty current tracked rows pass.

## `exp_013_cpsat_report.py`

Reads `results/exp_009_cpsat_benchmark_matrix_summary.csv` and writes a compact
Markdown report.

Run:

```powershell
.\.conda-env\python.exe experiments\exp_013_cpsat_report.py
```

Artifact:

- `results/exp_013_cpsat_report.md`

The report adds FJSPLib LB/UB columns, records whether each best local row
reaches the upstream UB, and keeps the distinction between proved `OPTIMAL`
rows and valid time-limited `FEASIBLE` schedules explicit.

## `exp_014_dynamic_reschedule_smoke.py`

Runs the Phase 2A dynamic FJSP smoke scenarios:

- a machine-breakdown event that delays the remaining operation until repair
- a job-arrival event that enlarges the current instance before rescheduling
- a multi-event sequence combining job arrival, machine breakdown, and
  processing-time change from `dynamic_events_multi_event.json`

Run:

```powershell
.\.conda-env\python.exe experiments\exp_014_dynamic_reschedule_smoke.py
```

Artifact:

- `results/exp_014_dynamic_reschedule_smoke.csv`
- `results/exp_014_dynamic_reschedule_smoke.md`

Each result is a full `ScheduleResult` and must pass the Phase 1 feasibility
checker before being written as `PASS`.

## `exp_015_dynamic_event_file_check.py`

Audits Phase 2A dynamic event JSON scenario files before they are used by
rescheduling experiments. The audit checks that each file can be loaded into
typed dynamic events, contains at least one event, and has non-decreasing event
times for deterministic replay.

Current tracked event files:

- `dynamic_events_multi_event.json`
- `dynamic_events_release_stagger.json`
- `dynamic_events_repair_cycle.json`

Run:

```powershell
.\.conda-env\python.exe experiments\exp_015_dynamic_event_file_check.py
```

Artifact:

- `results/exp_015_dynamic_event_file_check.csv`

The script returns exit code `1` if any event file fails to load or has an
invalid event timeline.

## `exp_016_dynamic_event_file_reschedule.py`

Runs a small deterministic rescheduling smoke scenario for each tracked dynamic
event JSON file. Each file is loaded through `load_event_specs_json()`, applied
to a compatible Phase 2A base state, and repaired with the EFT dynamic
rescheduling baseline.

Run:

```powershell
.\.conda-env\python.exe experiments\exp_016_dynamic_event_file_reschedule.py
```

Artifact:

- `results/exp_016_dynamic_event_file_reschedule.csv`
- `results/exp_016_dynamic_event_file_reschedule.md`

Each row must pass the shared experiment runner's Phase 1 feasibility check and
the dynamic checks inside `reschedule_from_state()`.

## `exp_017_phase2a_dynamic_report.py`

Reads the Phase 2A dynamic CSV artifacts from Experiments 014, 015, and 016,
then writes one Markdown overview report. This is a report-only gate: it does
not rerun solvers, so refresh `exp_014`, `exp_015`, and `exp_016` first.

Run:

```powershell
.\.conda-env\python.exe experiments\exp_017_phase2a_dynamic_report.py
```

Artifact:

- `results/exp_017_phase2a_dynamic_report.md`

The report summarizes dynamic smoke reschedules, event-file audits, and
event-file replay reschedules in one place.

## `exp_018_ai_rag_workflow.py`

Persistent supervised research execution. Choose `--track foundation`, `--track innovation`, or `--track graduation`; offline is the default. The entry point returns `3` at scope, evidence and conclusion review gates. Resume with `--session-dir` and a human-completed `--decision-file`; budgets are cumulative and cannot change on resume. See [workflow commands and exit statuses](../docs/research_workflow.md); the graduation G1/G2 route has a [dedicated guide](../docs/graduation_workflow.md).

## `exp_019_phase2a_protocol.py`

Runs the fixed Phase 2A FIFO/SPT/EFT protocol without models and writes a unique run containing inputs, schedules, raw/aggregate CSV, manifest, report and representative Gantt images.

```powershell
.\.conda-env\python.exe experiments\exp_019_phase2a_protocol.py
```

The persistent 018 route also accepts `--experiment-protocol experiments/protocols/phase2a_v1.json`, retaining its three human reviews. See [protocol semantics and limits](../docs/phase2a_experiment_protocol.md).

## `exp_020_sequential_reschedule.py`

Validates sequential event timestamps with existing dynamic rules and exports each step's frozen records and schedules. It runs independently of 018's isolated-event protocol route.

```powershell
.\.conda-env\python.exe experiments\exp_020_sequential_reschedule.py
```

See [sequential replay assumptions and saved evidence](../docs/phase2a_sequential_validation.md).

## `exp_021_graduation_solver_check.py` and `exp_022_graduation_rule_smoke.py`

The G2 reference solver check and R2 EDD/SPT/seeded Random rule smoke test use the graduation maintenance/tardiness model. Commands, outputs and limitations are documented in [G2 validation](../docs/graduation_g2_validation.md) and [R2 validation](../docs/graduation_r2_validation.md). Development smoke cases do not substitute for a formal G3 comparison.

## `exp_023_paper_code_validation.py`

Paper/code evidence validation, including field extraction and state-semantic review modes. Read the [initial validation snapshot](../docs/real_paper_code_validation.md), [field-extraction guide](../docs/paper_field_validation.md) and [state-semantic review guide](../docs/paper_state_semantic_validation.md) for the appropriate mode and its evidence limits.

## `exp_024_state_encoding_check.py` through `exp_026_validation_iteration.py`

These independent entry points validate lossless observation transport, run a bounded NumPy policy pilot, and compare a validation-driven candidate. Commands and saved-run interpretation are in the [encoding](../docs/graduation_state_encoding_validation.md), [policy pilot](../docs/graduation_neural_policy_pilot.md) and [validation iteration](../docs/graduation_validation_iteration.md) guides. A pilot or candidate result does not establish final research acceptance.

## `exp_027_research_controller.py`

Runs or inspects the bounded controller for registered research tasks. Use the [controller guide](../docs/research_controller_validation.md) for commands, budgets, evidence identity and stopping boundaries. The current registered capabilities are summarized only in [START_HERE.md](../START_HERE.md).

## `exp_028_graduation_reference_pilot.py`

Runs 12 paired tiny instances and 24 CP-SAT solves checked by enumeration, with a90-second execution deadline and zero API/network calls. See [pilot usage and its formal-review boundary](../docs/graduation_g3_protocol_draft.md#9-先导开发验证2026-10-28). The formal main grid remains a separate proposed protocol.

## `exp_029_graduation_main_scope.py`

`exp_029_graduation_main_scope.py` prepares or rechecks the complete240-pair/480-request formal-scope materials without running a solver. Read the [scope guide and review boundaries](../docs/graduation_g3_protocol_draft.md#10-主比较范围材料2026-10-29) before preparing a new folder.

## `exp_030_graduation_main.py`

Prepares/rechecks content-bound evidence, inspects the original cumulative budget, or executes the frozen main comparison only after its actual evidence approval. The supervised worker preserves all480 planned rows, including failures and missing requests, and independently checks saved production/maintenance plans. [Usage and review limitation](../docs/graduation_g3_protocol_draft.md#11-主比较后端与evidence材料2026-10-29). The published evidence packet grants no execution approval.

## `exp_031_graduation_solver_diagnostics.py`

Read-only `audit` selects the five archived G3A errors. Read-only `recheck` verifies development captures and explicit captured-source snapshots; see [diagnosis, budget lock and usage](../docs/graduation_g3_protocol_draft.md#14-拒绝候选诊断2026-10-29). The single five-call development capture reproduced reported-objective/returned-solution disagreement; its packaging failed and remains FAILED. The original cumulative budget is now locked with zero available time. `dev-probe` cannot resume it. No formal results are replaced or accepted by these diagnostics.

## `exp_032_graduation_remedy_scope.py`

Preparation-only scope for14 solver-remedy development requests: five historical error requests under two presolve configurations, plus four enumerable controls. Only `prepare` and read-only `recheck` are available. No execution, budget or approval is created. [Scope, new-budget proposal and limitations](../docs/graduation_g3_protocol_draft.md#15-补救开发范围提案2026-10-29).

## General Requirements

- Every experiment result must pass `check_feasibility()`.
- Infeasible schedules must not be reported as valid schedules.
- Feasibility constraints must not be weakened to make tests pass.
- Research acceptance is separate from static feasibility or one completed workflow run; see the [acceptance map](../docs/research_acceptance_map.md).
