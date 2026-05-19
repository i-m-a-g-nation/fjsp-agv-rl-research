# FJSP-AGV-RL Research Project Rules

本项目研究柔性作业车间调度 FJSP，后续扩展 AGV、动态扰动与强化学习。

当前阶段：Phase 1。

## Phase 1 目标

当前阶段只做静态 FJSP 基础实验平台。

目标不是创新，而是保证实验底座正确、可验证、可复现。

必须支持：

- 静态 FJSP 实例。
- 基础调度规则。
- 统一 ScheduleRecord / ScheduleResult。
- makespan 计算。
- feasibility checker 合法性检查。
- 甘特图输出。
- 小规模 OR-Tools CP-SAT 求解器基线。
- 可复现实验脚本。

## 当前阶段禁止事项

除非用户明确要求，否则禁止实现：

- AGV 调度。
- 运输时间。
- 强化学习。
- DQN。
- PPO。
- GNN。
- 多智能体强化学习。
- 动态工件到达。
- 机器故障。
- 能耗目标。
- 多目标 Pareto 优化。
- AGV 路径冲突避免。

这些是后续阶段。

## Conda 环境规则

必须使用专用 Conda 环境。

本地路径不要写死在仓库里；默认由脚本创建到项目内 `.conda-env`，也可以通过环境变量 `FJSP_CONDA_ENV` 指定自定义路径。

禁止使用 base。

运行 Python 前必须检查：

python -c "import sys; print(sys.executable)"

输出路径必须是专用环境路径（项目内 `.conda-env` 或 `FJSP_CONDA_ENV` 指向的路径）。

如果环境不存在，先运行：

powershell -ExecutionPolicy Bypass -File .\scripts\setup_env.ps1

## 核心数据格式

FJSP 实例统一使用：

jobs[job_id][op_id] = [(machine_id, processing_time), ...]

示例：

jobs = [
    [
        [(0, 3), (1, 5)],
        [(1, 4), (2, 6)],
    ],
    [
        [(0, 2), (2, 4)],
        [(1, 3)],
    ],
]

## ScheduleRecord 要求

每条调度记录至少包含：

- job_id
- op_id
- machine_id
- start
- end
- processing_time

所有算法必须返回统一 ScheduleResult。

## 合法性检查要求

所有调度结果必须经过 feasibility checker。

必须检查：

1. 每道工序是否恰好加工一次。
2. 同一工件工序先后约束是否满足。
3. 同一机器上的工序是否无重叠。
4. 所选机器是否属于该工序可选机器集合。
5. processing_time 是否等于 end - start。
6. processing_time 是否匹配实例数据。
7. makespan 是否等于所有工序 end 的最大值。

禁止把非法调度当成有效结果。

禁止为了通过测试而削弱合法性检查。

## Phase 1 必须实现的规则基线

- FIFO
- SPT
- Earliest Available Machine
- Random baseline with seed

## 求解器基线要求

使用 OR-Tools CP-SAT 做小规模参考解。

建模要求：

- operation-machine 组合使用 optional interval。
- 每道工序 exactly one machine。
- 同一工件相邻工序满足 precedence。
- 同一机器上所有任务满足 NoOverlap。
- 目标 minimize makespan。
- 有 time limit。
- 只有 solver status 为 OPTIMAL 时才能说最优。
- 如果 status 为 FEASIBLE，只能说限时可行参考解。

## 测试要求

Phase 1 完成后运行：

python experiments/exp_001_toy_instance.py
pytest

加入 CP-SAT 后运行：

python experiments/exp_002_solver_check.py
pytest

失败必须如实报告，不允许假装成功。

## AI 编码规则

- 优先小步修改。
- 不要一次性重写整个项目。
- 不要越界实现后续阶段。
- 所有新增功能必须配测试。
- 所有实验结果必须可复现。
- 所有算法结果必须过 feasibility checker。
