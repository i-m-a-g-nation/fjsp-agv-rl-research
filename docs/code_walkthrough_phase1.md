# Phase 1 代码导读

本文用于快速理解 Phase 1 静态 FJSP 实验平台的代码结构、核心概念和推荐阅读顺序。

## 推荐阅读顺序

```text
1. src/data/instance.py             FJSP 数据结构
2. src/data/loader.py               benchmark 文本如何变成实例
3. src/scheduling/encoding.py       调度结果的数据结构
4. src/scheduling/decoding.py       assignment 如何解码为时间表
5. src/scheduling/feasibility.py    调度合法性如何验证
6. src/solvers/baselines.py         简单 job-order baseline
7. src/solvers/dispatching.py       严格 ready-operation dispatching rules
8. src/solvers/ortools_solver.py    OR-Tools CP-SAT baseline
9. experiments/common.py            统一实验记录
10. experiments/exp_*.py            实验脚本如何串联各模块
```

## 核心数据流

```text
FJSPInstance
    -> solver(instance)
    -> assignment 或 ScheduleResult
    -> decode_schedule(...)
    -> check_feasibility(...)
    -> ExperimentRecord / CSV / Gantt / report
```

所有调度结果进入实验记录前都必须通过 `check_feasibility()`。这是 Phase 1 最重要的安全边界。

## 模块职责

| 模块 | 职责 |
|---|---|
| `src/data/instance.py` | 定义 `FJSPInstance`、`Job`、`Operation`、`MachineOption` |
| `src/data/loader.py` | 解析 FJSPLib old-format 文件，并将机器编号规范化 |
| `src/scheduling/encoding.py` | 定义 `ScheduleRecord` 和 `ScheduleResult` |
| `src/scheduling/decoding.py` | 使用半主动解码生成开始时间和结束时间 |
| `src/scheduling/feasibility.py` | 独立检查工序覆盖、工序顺序、机器容量、机器可行性、加工时间和 makespan |
| `src/solvers/baselines.py` | 保留简单 FIFO/SPT/EFT/Random baseline |
| `src/solvers/dispatching.py` | 实现严格 ready-operation dispatching rules |
| `src/solvers/heuristics.py` | 保持旧导入路径兼容 |
| `src/solvers/ortools_solver.py` | CP-SAT optional-interval 模型和结果提取 |
| `experiments/common.py` | 统一运行 solver、校验结果、写 CSV |
| `experiments/exp_009_cpsat_benchmark_matrix.py` | 受控 CP-SAT worker 矩阵 |
| `experiments/exp_010_heuristic_benchmark_matrix.py` | 启发式 benchmark 矩阵 |
| `experiments/exp_011_heuristic_quality_report.py` | 基于 BKS 的启发式质量报告 |
| `experiments/exp_012_benchmark_metadata_audit.py` | benchmark 文件、LB/UB 行、loader 一致性审计 |
| `experiments/exp_013_cpsat_report.py` | CP-SAT 聚合结果的可读 Markdown 报告 |

## Baseline 与 Strict Dispatching

`baselines.py` 中的 FIFO、SPT、Random 是简单 baseline：它们按固定 job/order 生成 assignment，再交给 `decode_schedule()` 放置时间。

`dispatching.py` 中的 `dispatch_*` 函数更接近调度规则定义：每一步只考虑当前 ready operations，并构造候选：

```text
(job_id, op_id, machine_id, ready_time, start, finish, processing_time)
```

不同规则只改变候选选择逻辑：

| 规则 | 选择逻辑 |
|---|---|
| `DispatchFIFO` | 最早 ready 的工序，然后选 earliest-finish 机器 |
| `DispatchSPT` | processing time 最短的 ready operation-machine pair |
| `DispatchEFT` | finish time 最早的 ready operation-machine pair |
| `DispatchMWKR` | 剩余路线工作量最大的 ready job，然后选 earliest-finish 机器 |
| `DispatchMOPNR` | 剩余工序数最多的 ready job，然后选 earliest-finish 机器 |
| `DispatchRandom` | 从 ready operation-machine pairs 中按 seed 随机选择 |

## CP-SAT 模型阅读重点

`ortools_solver.py` 是最小可行 CP-SAT baseline：

- 每个 `(job, operation, machine)` 建一个 optional interval。
- `AddExactlyOne()` 保证每道工序选择一台可行机器。
- `OnlyEnforceIf()` 让 precedence 只在对应机器组合被选中时生效。
- `AddNoOverlap()` 保证同一机器上的 interval 不重叠。
- `makespan` 约束所有 job 的最后一道工序完成时间。
- 提取结果后再次调用 feasibility checker，防止模型或提取逻辑错误。

CP-SAT 结果会记录 `solver_status`、`solver_objective_bound`、`solver_gap` 和 `solver_wall_time`。启发式没有这些求解器诊断字段。

## 后续维护建议

当前架构不需要大重构。继续维护时建议保持小步：

1. 扩展 benchmark 前先记录来源和 BKS。
2. 扩展后先跑 `exp_012`，再跑矩阵实验。
3. 不把 `FEASIBLE` 说成本地已证明最优。
4. 新增规则优先复用 `dispatching.py` 的 shared dispatching framework。
5. 进入 AGV/RL/GNN 前继续保持 feasibility checker 独立且严格。
