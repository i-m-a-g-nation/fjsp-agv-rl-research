# Phase 1 结果汇总与有效性威胁（历史快照）

本页恢复合并前 `main`（`61dcbe3`）README 中的 Phase 1 实验结果表、"Threats to Validity" 和 "Known Notes" 三节。合并 `codex/phase2a-protocol` 时这些内容从 README 移除，原始 CSV 仍在 [`experiments/results/`](../experiments/results/README.md)，但人工可读的汇总和有效性讨论没有其他副本，因此单独保留。

正文按原文保留，只把相对链接改为从 `docs/` 出发。数字是当时源码与环境下的快照；Phase 1 加固后的复现与验收以[Phase 1 复现说明](reproducibility_phase1.md)为准，当前状态以 [START_HERE](../START_HERE.md) 为准。

## Phase 1 Results (snapshot at 61dcbe3)

### Experiment 001: Heuristics

| Algorithm | Makespan | Feasible |
|---|---:|---|
| FIFO | 14 | PASS |
| SPT | 13 | PASS |
| EarliestFinishTime | 13 | PASS |
| Random(s=42) | 14 | PASS |
| Random(s=123) | 14 | PASS |
| Random(s=999) | 20 | PASS |

Best heuristic result on the toy instance: makespan 13.

### Experiment 002: Heuristics vs CP-SAT

| Algorithm | Makespan | Status |
|---|---:|---|
| FIFO | 14 | HEURISTIC |
| SPT | 13 | HEURISTIC |
| EarliestFinishTime | 13 | HEURISTIC |
| Random(42) | 14 | HEURISTIC |
| CP-SAT(tl=30s) | 11 | CP-SAT optimal |

CP-SAT currently proves makespan 11 on the toy instance.

### Experiment 003: Strict Dispatching Rules

| Algorithm | Definition | Feasible |
|---|---|---|
| DispatchFIFO | earliest ready operation, then earliest-finish machine | PASS |
| DispatchSPT | shortest processing-time ready operation-machine pair | PASS |
| DispatchEFT | earliest-finish ready operation-machine pair | PASS |
| DispatchMWKR | most remaining route work, then earliest-finish machine | PASS |
| DispatchMOPNR | most operations remaining, then earliest-finish machine | PASS |
| DispatchRandom(42) | seeded random ready operation-machine pair | PASS |

The original heuristic functions remain as simple baselines. The `dispatch_*`
functions are the stricter dispatching-rule implementations intended for
definition-sensitive comparisons.

On the toy instance, DispatchMWKR and DispatchMOPNR currently produce makespan 12.

### Experiment 004: Benchmark Loader Smoke

Loads small benchmark-format files from `instances/` and runs selected baselines,
strict dispatching rules, and CP-SAT. The included smoke files are intentionally
small so the experiment stays fast and deterministic.

### Experiment 005: Benchmark Batch

Recursively discovers `*.fjs` files under `instances/`, evaluates each static
FJSP instance in stable path order, and records loader failures rather than
silently dropping malformed files. Use `--max-files`, `--skip-cp-sat`, and
`--cp-sat-time-limit` to control runs on larger tracked collections.

The tracked real subset is documented in [instances/README.md](../instances/README.md).
Its thirty upstream files are copied from the official ScheduleOpt FJSPLib
repository and retain CC-BY-SA-4.0 attribution.

| FJSPLib instance | Size | Best heuristic in current suite | CP-SAT | FJSPLib UB |
|---|---:|---:|---:|---:|
| `fattahi1` | 2 x 2 | 66 | 66 `OPTIMAL` | 66 |
| `fattahi2` | 2 x 2 | 107 | 107 `OPTIMAL` | 107 |
| `fattahi3` | 3 x 2 | 221 | 221 `OPTIMAL` | 221 |
| `fattahi4` | 3 x 2 | 367 | 355 `OPTIMAL` | 355 |
| `fattahi5` | 3 x 2 | 119 | 119 `OPTIMAL` | 119 |
| `fattahi6` | 3 x 3 | 330 | 320 `OPTIMAL` | 320 |
| `fattahi7` | 3 x 5 | 397 | 397 `OPTIMAL` | 397 |
| `fattahi8` | 3 x 4 | 273 | 253 `OPTIMAL` | 253 |
| Chambers-Barnes `mt10c1` | 10 x 11 | 1225 | 927 `FEASIBLE` | 927 |
| Chambers-Barnes `mt10cc` | 10 x 12 | 1121 | 908 `FEASIBLE` | 908 |
| Chambers-Barnes `mt10x` | 10 x 11 | 1173 | 918 `FEASIBLE` | 918 |
| Dauzere-Peres `01a` | 10 x 5 | 3056 | 2586 `FEASIBLE` | 2505 |
| Dauzere-Peres `02a` | 10 x 5 | 2443 | 2534 `FEASIBLE` | 2228 |
| Dauzere-Peres `03a` | 10 x 5 | 2413 | 2602 `FEASIBLE` | 2228 |
| Dauzere-Peres `04a` | 10 x 5 | 3070 | 2591 `FEASIBLE` | 2503 |
| `kacem1` | 4 x 5 | 11 | 11 `OPTIMAL` | 11 |
| `kacem2` | 10 x 7 | 12 | 11 `OPTIMAL` | 11 |
| `kacem3` | 10 x 10 | 8 | 7 `OPTIMAL` | 7 |
| `kacem4` | 15 x 10 | 12 | 15 `FEASIBLE` | 11 |
| Hurink edata `ft06` | 6 x 6 | 55 | 55 `OPTIMAL` | 55 |
| Brandimarte `mk01` | 10 x 6 | 44 | 40 `OPTIMAL` | 40 |
| Brandimarte `mk02` | 10 x 6 | 30 | 28 `FEASIBLE` | 26 |
| Brandimarte `mk03` | 15 x 8 | 204 | 220 `FEASIBLE` | 204 |
| Brandimarte `mk04` | 15 x 8 | 77 | 62 `FEASIBLE` | 60 |
| Brandimarte `mk05` | 15 x 4 | 185 | 180 `FEASIBLE` | 172 |
| Brandimarte `mk06` | 10 x 15 | 67 | 74 `FEASIBLE` | 57 |
| Brandimarte `mk07` | 20 x 5 | 160 | 159 `FEASIBLE` | 139 |
| Brandimarte `mk08` | 20 x 10 | 531 | 523 `FEASIBLE` | 523 |
| Brandimarte `mk09` | 20 x 10 | 341 | 340 `FEASIBLE` | 307 |
| Brandimarte `mk10` | 20 x 15 | 243 | 302 `FEASIBLE` | 193 |

For larger or time-limited rows such as `mk02`-`mk10`, the Chambers-Barnes
variants, the Dauzere-Peres rows, and `kacem4`, the local
CP-SAT values are time-limited feasible reference schedules, not locally proven
optima. Timed CP-SAT runs can vary between observations.

### Experiment 006: CP-SAT Time-Limit Sweep

Runs tracked Brandimarte `mk03` with a fixed single CP-SAT worker so that
time-limit comparisons have less parallel-search noise.

| Time limit | Makespan | Status | Bound | Relative gap |
|---:|---:|---|---:|---:|
| 1s | 417 | `FEASIBLE` | 20 | 0.952038 |
| 3s | 285 | `FEASIBLE` | 20 | 0.929825 |
| 10s | 220 | `FEASIBLE` | 20 | 0.909091 |

The fixed-worker sweep is intentionally separate from the default batch run,
which allows CP-SAT to use its default worker configuration. Solver settings
are part of an experiment result and must be compared explicitly.

### Experiment 007: CP-SAT Worker-Count Sweep

Runs tracked Brandimarte `mk03` with a fixed 10-second limit while varying the
CP-SAT worker configuration.

| Workers | Makespan | Status | Bound | Relative gap |
|---:|---:|---|---:|---:|
| 1 | 220 | `FEASIBLE` | 20 | 0.909091 |
| 2 | 207 | `FEASIBLE` | 20 | 0.903382 |
| 4 | 207 | `FEASIBLE` | 20 | 0.903382 |
| auto | 209 | `FEASIBLE` | 75 | 0.641148 |

Every row passed the independent feasibility checker. This is one observed
timed run, not a stable worker-performance ranking: parallel CP-SAT search can
vary between runs. The auto configuration produced the strongest bound in
this observation, while 2 and 4 workers produced slightly better incumbents.

### Experiment 008: Repeated CP-SAT Worker Observations

Repeats every tracked worker configuration three times on Brandimarte `mk03`
with the same 10-second limit. Raw runs and aggregate statistics are recorded
separately.

| Workers | Feasible runs | Best makespan | Mean makespan | Std. dev. | Best bound | Best gap |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3 / 3 | 220 | 220.000000 | 0.000000 | 20 | 0.909091 |
| 2 | 3 / 3 | 204 | 204.000000 | 0.000000 | 20 | 0.901961 |
| 4 | 3 / 3 | 204 | 204.000000 | 0.000000 | 21 | 0.897059 |
| auto | 3 / 3 | 204 | 204.000000 | 0.000000 | 88 | 0.568627 |

All 12 schedules passed the independent feasibility checker. In this
three-repeat observation, 2, 4, and automatic workers consistently reached
the upstream BKS of 204. CP-SAT still reported `FEASIBLE`, so these remain
time-limited feasible reference schedules rather than locally proven optima.

### Experiment 009: Repeated CP-SAT Benchmark Matrix

Scans the tracked static FJSPLib subset recursively. Each instance is evaluated
twice with one worker and twice with the automatic worker configuration under
the same 3-second limit.

| Workers | Instances | Feasible rows | Proved-optimal rows | Mean best makespan | Mean best bound | Mean best gap |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 30 | 30 | 12 | 674.333 | 258.067 | 0.451173 |
| auto | 30 | 30 | 12 | 590.367 | 358.900 | 0.273244 |

Representative best rows:

| Instance | Best workers | Best makespan | Best bound | Best gap | Status |
|---|---:|---:|---:|---:|---|
| `mk01` | 1 | 40 | 40 | 0.000000 | `OPTIMAL` |
| `mk10` | auto | 340 | 74 | 0.782353 | `FEASIBLE` |
| `mt10cc` | auto | 908 | 835 | 0.080396 | `FEASIBLE` |
| `03a` | auto | 2846 | 426 | 0.850316 | `FEASIBLE` |
| `fattahi8` | 1 | 253 | 253 | 0.000000 | `OPTIMAL` |
| `kacem4` | auto | 21 | 10 | 0.523810 | `FEASIBLE` |

All 120 CP-SAT schedules passed the independent feasibility checker. The
machine-readable report in
[`experiments/results/exp_013_cpsat_report.md`](../experiments/results/exp_013_cpsat_report.md)
keeps the complete per-instance interpretation. `FEASIBLE` rows are valid
schedules, but their objective bounds and gaps show that the local time limit
did not prove optimality.

### Experiment 010: Heuristic Benchmark Matrix

Runs deterministic baselines and strict dispatching rules once on each tracked
FJSPLib instance. `Random` and `DispatchRandom` are aggregated across fixed
seeds `42`, `123`, and `999`.

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

All 420 schedules passed the independent feasibility checker. No single
dispatching rule dominates every instance: MWKR is strongest on `mk01`, `mk02`,
`mk06`, `mk10`, `mt10cc`, `fattahi1`, `kacem2`, and `kacem4`; FIFO is strongest on `mk04`, `mk05`,
`mk08`, `mk09`, `02a`, `03a`, `fattahi5`, `ft06`, and `kacem1`, ties MWKR on `mk03` and `fattahi2`, and ties
MOPNR on `fattahi3` and `fattahi4`. EarliestFinishTime ties DispatchEFT on
`fattahi6`, `mt10x`, and `fattahi8`. MOPNR is strongest on `mk07`, `mt10c1`, and `04a`; FIFO is strongest on `01a`; and FIFO, MWKR, and MOPNR
tie on `kacem3`.
Ready-operation random dispatching is consistently better than the simple
job-order random baseline in this tracked subset, but remains seed-sensitive.

### Experiment 011: Upper-Bound-Aware Heuristic Quality Report

Reads the structured upstream references in `instances/fjsplib_bks.csv` and
computes

```text
gap_UB = (makespan - FJSPLib_UB) / FJSPLib_UB
```

for every Experiment 010 family and instance. The upstream lower bound is used
as a sanity check, so a feasible schedule may improve an open upper bound but
cannot fall below the upstream lower bound.

| Algorithm family | Mean best gap | Maximum best gap |
|---|---:|---:|
| FIFO | 4.862683 | 25.090909 |
| SPT | 2.291656 | 6.088083 |
| EarliestFinishTime | 0.392423 | 1.384615 |
| DispatchFIFO | 0.151281 | 0.370370 |
| DispatchSPT | 1.393257 | 4.564767 |
| DispatchEFT | 0.405199 | 1.384615 |
| DispatchMWKR | 0.158760 | 0.364924 |
| DispatchMOPNR | 0.193880 | 0.466667 |
| Random | 3.141676 | 9.421053 |
| DispatchRandom | 1.318093 | 6.142857 |

On the current thirty-instance subset, DispatchFIFO has the strongest
cross-instance mean best gap. The subset remains intentionally small, so the
next step is improving reporting and maintainability before adding more rules.

### Experiment 012: Benchmark Metadata Audit

Recursively discovers tracked FJSPLib files, matches them one-to-one with
`instances/fjsplib_bks.csv`, and verifies that every tracked file still loads.
All thirty current rows pass the file, BKS, and loader checks. The script returns
a failing exit code when a file, metadata row, or loadable instance is missing.

### Experiment 013: CP-SAT Report Builder

Reads the Experiment 009 aggregate CSV and writes a Markdown interpretation
report at
[`experiments/results/exp_013_cpsat_report.md`](../experiments/results/exp_013_cpsat_report.md).
It does not rerun CP-SAT; it checks the CSV shape, summarizes worker
configurations, selects each instance's best row, adds FJSPLib LB/UB comparison,
and keeps the distinction between `OPTIMAL` proofs and valid time-limited
`FEASIBLE` schedules explicit. In the current 30-instance report, 15 best rows
reach the upstream UB, 13 are locally proved `OPTIMAL`, and 2 reach UB without
a local optimality proof.

## Threats to Validity

| Threat | Current mitigation |
|---|---|
| Time-limited CP-SAT may find feasible schedules without proof | Reports keep `FEASIBLE`, bound, gap, UB gap, and local-proof fields separate |
| Benchmark subset is still moderate | Every expansion is audited by `exp_012`; current subset is documented with provenance and LB/UB rows |
| Random heuristics are seed-sensitive | Random families are reported with fixed seeds and ranges rather than single hidden samples |
| Upstream reference bounds are external data | Local reports distinguish reaching UB from locally proving `OPTIMAL` |
| Phase 2 topics could blur scope | Phase 2A allows dynamic events and rescheduling only; AGV, RL, GNN, transportation, and multi-objective extensions remain excluded |

## Known Notes

- `experiments/exp_001_gantt_latest.png` is the fixed Gantt output and is tracked.
- Historical Gantt PNG files are retained for traceability.
- A low-priority pytest cache warning may appear on some Windows paths; it does not affect the test results.

> 注：上表最后一行写于毕设路线放行之前。目前毕设简化模型内已有有界 REINFORCE 试训，范围以 [AGENTS.md](../AGENTS.md) 的"已放行的扩展"为准；AGV、运输、GNN 和多目标扩展仍未实现。
