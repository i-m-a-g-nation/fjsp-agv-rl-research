# Phase 1 代码导读

本文档用于快速理解 Phase 1 静态 FJSP 实验平台的代码结构、关键概念和推荐阅读顺序。

## 推荐阅读顺序

```text
1. src/data/instance.py             从 FJSP 数据结构开始
2. src/data/loader.py               理解 benchmark 文本如何变成实例
3. src/scheduling/encoding.py       调度结果的数据结构
4. src/scheduling/decoding.py       如何把分配方案解码成时间表
5. src/scheduling/feasibility.py    如何验证调度是否合法
6. src/solvers/baselines.py         简单 job-order baseline
7. src/solvers/dispatching.py       严格 ready-operation dispatching rules
8. src/solvers/heuristics.py        向后兼容的启发式门面模块
9. src/solvers/ortools_solver.py    OR-Tools CP-SAT baseline
10. experiments/common.py           统一实验 CSV 记录
11. experiments/exp_*.py            实验脚本如何串联全部模块
```

## 模块职责

| 模块 | 职责 |
|---|---|
| `src/data/instance.py` | 定义 `FJSPInstance`、`Job`、`Operation` 和 `MachineOption` |
| `src/data/loader.py` | 解析 Brandimarte/FJSPLib 风格 benchmark 文本和文件，已覆盖真实 FJSPLib 子集 |
| `src/scheduling/encoding.py` | 定义 `ScheduleRecord` 和 `ScheduleResult` |
| `src/scheduling/decoding.py` | 使用半主动解码，把 `(job, op, machine)` 序列变成带时间的调度表 |
| `src/scheduling/feasibility.py` | 独立检查工序覆盖、工序顺序、机器容量、机器可行性、加工时间和 makespan |
| `src/solvers/baselines.py` | FIFO、SPT、EarliestFinishTime、Random 等简单 baseline |
| `src/solvers/dispatching.py` | DispatchFIFO、DispatchSPT、DispatchEFT、DispatchMWKR、DispatchMOPNR、DispatchRandom |
| `src/solvers/heuristics.py` | 保持旧导入路径不变的兼容门面 |
| `src/solvers/ortools_solver.py` | CP-SAT baseline，包含 optional intervals、ExactlyOne、NoOverlap 和诊断信息 |
| `src/vis/gantt.py` | Gantt 图绘制 |
| `experiments/common.py` | 标准化实验结果，并写入 CSV |
| `experiments/exp_005_benchmark_batch.py` | 批量运行 tracked benchmark，记录启发式和 CP-SAT 结果 |
| `experiments/exp_006_cpsat_time_limit_sweep.py` | 固定 worker，对比 CP-SAT 时限、bound 和 gap |
| `experiments/exp_007_cpsat_worker_sweep.py` | 固定时限，对比 CP-SAT worker 数量、bound 和 gap |

## 核心数据流

```text
FJSPInstance
    |
    | 传给 solver
    v
solver(instance)
    |
    | 启发式生成 assignment，或 CP-SAT 直接生成 ScheduleResult
    v
decode_schedule(assignment, instance)
    |
    | 得到 ScheduleResult(records, makespan, metadata)
    v
check_feasibility(result)
    |
    | PASS 后进入实验记录和可视化
    v
ExperimentRecord / Gantt / CSV
```

## Baseline 和 Strict Dispatching 的区别

`baselines.py` 中的 FIFO、SPT、Random 是简单 baseline。它们按照固定 job/order 顺序生成 assignment，然后交给 `decode_schedule()` 放置时间。

`dispatching.py` 中的 `dispatch_*` 函数更接近调度规则定义。每一步只考虑当前 ready operations，并构造候选：

```text
(job_id, op_id, machine_id, ready_time, start, finish, processing_time)
```

然后不同规则选择不同候选：

| 规则 | 选择逻辑 |
|---|---|
| DispatchFIFO | 最早 ready 的工序，然后选 earliest-finish 机器 |
| DispatchSPT | processing time 最短的 ready operation-machine pair |
| DispatchEFT | finish time 最早的 ready operation-machine pair |
| DispatchMWKR | 剩余路线工作量最大的 ready job，然后选 earliest-finish 机器 |
| DispatchMOPNR | 剩余工序数最多的 ready job，然后选 earliest-finish 机器 |
| DispatchRandom | 从 ready operation-machine pairs 中按 seed 随机选 |

## Feasibility Checker 为什么重要

所有求解器返回前都必须经过 feasibility checker。它是 Phase 1 的安全阀，防止非法调度被当成有效结果。

它主要检查：

1. 调度结果必须关联一个实例。
2. 记录不能为空。
3. job id、operation id、machine id 必须合法。
4. 每道工序必须恰好出现一次。
5. 每个 job 内部必须满足工序顺序。
6. 同一机器上的工序不能时间重叠。
7. 加工时间必须与实例数据一致。
8. makespan 必须等于所有工序完成时间的最大值。

## CP-SAT 模型阅读重点

`ortools_solver.py` 是一个最小可行 CP-SAT baseline：

- 每个 `(job, op, machine)` 创建一个 optional interval。
- `presence` 表示该工序是否选择该机器。
- `AddExactlyOne()` 保证每道工序恰好选择一台机器。
- `OnlyEnforceIf()` 让 precedence 约束只在对应机器组合被选中时生效。
- `AddNoOverlap()` 保证同一机器上区间不重叠。
- `makespan` 约束所有 job 的最后一道工序完成时间。

CP-SAT 结果还会记录：

- `solver_status`
- `solver_objective_bound`
- `solver_gap`
- `solver_wall_time`

启发式算法没有这些求解器诊断信息，对应字段保持为空。

## 实验记录

实验脚本通过 `ExperimentRecord` 写入 CSV。标准字段包括：

```text
experiment_id
instance_name
algorithm
makespan
feasible
runtime_s
note
objective_bound
gap
solver_wall_time
```

当前 CSV 输出位于：

```text
experiments/results/
```

## 后续维护建议

当前项目不需要大重构。接下来应保持小步开发：

1. 分批扩展 FJSPLib 子集并保存来源说明。
2. 比较更大静态实例上的 OR-Tools 限时行为。
3. 若继续增加启发式规则，可在 `dispatching.py` 内再拆 rule selector。
4. 在进入 AGV/RL/GNN 前，继续保持 feasibility checker 独立且严格。
