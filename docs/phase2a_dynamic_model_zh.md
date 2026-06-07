# Phase 2A 动态 FJSP 最小模型说明

本文是 `docs/math_model_phase2a.tex` 的中文阅读版，用于快速理解当前
Phase 2A 实现边界。

## 当前目标

Phase 2A 只在 Phase 1 静态 FJSP 底座上加入最小动态层：

- 动态事件
- 动态状态
- 冻结已执行或正在执行的工序
- 剩余工序视图
- 确定性重调度 baseline
- 静态合法性检查 + 动态合法性检查

当前仍然不做 AGV、运输时间、强化学习、GNN、多目标优化，也不做工序抢占。

## 动态状态

当前动态状态记为：

```text
S_t = (I_t, t, R_t, a_t, u_t)
```

含义：

- `I_t`：当前 FJSP 实例
- `t`：当前重调度时刻
- `R_t`：已经 release 的 job 集合
- `a_t(j)`：job `j` 的 release time
- `u_t(m)`：机器 `m` 下一次允许未来工序开工的时间

代码中对应：

- `DynamicFJSPState.instance`
- `DynamicFJSPState.current_time`
- `DynamicFJSPState.released_job_ids`
- `DynamicFJSPState.job_release_times`
- `DynamicFJSPState.machine_unavailable_until`

## 动态事件

当前事件包括：

| 事件 | 含义 |
|---|---|
| `MachineBreakdown` | 机器在维修完成前不能接受未来新开工 |
| `MachineRepair` | 机器从维修事件时刻重新可用 |
| `JobArrival` | 新 job 到达并追加到当前实例 |
| `ProcessingTimeChange` | 修改某个未来 operation-machine pair 的加工时间 |

多个事件通过 `apply_events()` 按非递减时间顺序应用。若事件乱序，直接报错。

## 冻结工序

Phase 2A 不做抢占，因此重调度时冻结两类工序：

- 已完成：`end <= current_time`
- 正在加工：`start < current_time < end`

代码入口：

```python
frozen_records_at_time(schedule, current_time)
```

冻结记录在重调度结果中必须保持原机器、原开始时间、原结束时间和原加工时间。

## 剩余工序

给定动态状态和 frozen records，可以得到剩余待调度工序：

```python
remaining_operations_from_frozen(state, frozen_records)
```

该函数要求每个 job 的 frozen records 必须构成工艺路线前缀。例如冻结
`op_1` 但没有冻结 `op_0` 会被拒绝。

## 重调度 baseline

当前重调度函数：

```python
reschedule_from_state(state, frozen_records, rule="eft")
```

支持规则：

- `fifo`
- `spt`
- `eft`

返回值仍是完整 `ScheduleResult`，不是 partial schedule。返回前必须同时通过：

- Phase 1 `check_feasibility()`
- Phase 2A `check_dynamic_feasibility()`

## 动态合法性检查

Phase 2A checker 额外检查 Phase 1 checker 看不到的约束：

- frozen records 不可改变
- job 不可早于 release time 开工
- 非 frozen 未来工序不可在机器 unavailable window 内开工

## 当前实验

`experiments/exp_014_dynamic_reschedule_smoke.py` 覆盖三个 smoke 场景：

| 场景 | 说明 |
|---|---|
| `dynamic_breakdown_1x1` | 机器故障后维修，再调度剩余工序 |
| `dynamic_job_arrival_2x1` | 新 job 到达后重调度 |
| `dynamic_multi_event_2x2` | job 到达 + 机器故障 + 加工时间变化 |

输出：

- `experiments/results/exp_014_dynamic_reschedule_smoke.csv`
- `experiments/results/exp_014_dynamic_reschedule_smoke.md`

## 下一步建议

下一步不建议立刻加入 AGV 或 RL。更稳的方向是：

1. 增加 partial schedule repair 策略对比。
2. 增加多次滚动重调度实验。
3. 给动态事件序列增加 JSON/CSV 输入格式。
4. 再考虑更复杂的 breakdown 语义，例如可中断加工。
