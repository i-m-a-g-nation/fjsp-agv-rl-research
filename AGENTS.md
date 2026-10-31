# FJSP-AGV-RL Research Project Rules

本项目研究柔性作业车间调度 FJSP，后续扩展 AGV、动态扰动与强化学习。

当前阶段：Phase 1 与 Phase 2A 已完成工程交付并进入维护；毕设路线按下文“已放行的扩展”逐步推进。当前进度与下一步只在 `START_HERE.md` 维护。

## Phase 1 基础

Phase 1 已建立静态 FJSP 基础实验平台。

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

## Phase 2A 目标

当前阶段只做动态 FJSP 最小底座。

必须支持：

- 动态事件数据结构。
- 机器故障与维修事件。
- 新 job 到达事件。
- 加工时间变更事件。
- 动态状态对象。
- 固定已完成或正在执行的调度记录。
- 对剩余工序执行最小重调度 baseline。
- 重调度结果继续返回统一 ScheduleResult。
- 重调度结果继续通过 feasibility checker。

## 已放行的扩展（毕设路线）

以下内容已在用户确认的毕设范围内实现，代码在 `src/fjsp_lab/maintenance/`，模型见 `docs/models/graduation_model.md`，历史批准记录见 `docs/history/`：

- G1：同质平行机、每任务一道工序、0 时刻到达、每机一次必需维护（时间窗内）、总延期目标，及其数据与合法性检查器。
- G2：固定/联合维护的小规模 CP-SAT 参考模型与独立枚举核对。
- R1/R2：有限步、带动作掩码的调度构造环境及 EDD/MDD/ATC 规则基线。
- 智能优化算法：GA、SA、改进 GA（IGA）。
- 学习型构造策略（仅用于上述毕设简化模型）：NumPy 逐动作打分 MLP（模仿 + REINFORCE）；PyTorch 注意力策略（模仿 IGA 教师 + REINFORCE，共享基线，无 PPO）。

每个新阶段（例如正式 G3 批次、PPO、新的训练预算）仍需用户单独批准，已有批准不自动延伸。

## 当前禁止事项

除非用户明确要求，否则禁止实现：

- AGV 调度、运输时间、缓冲区、AGV 路径冲突避免（大创路线，最小范围草案尚未获批）。
- 毕设简化模型以外的强化学习，以及 DQN、PPO、GNN、多智能体强化学习。
- 能耗目标。
- 多目标 Pareto 优化。

这些是后续阶段。

## 代码结构

- 库代码只在 `src/fjsp_lab/`：`fjsp`（Phase 1）、`dynamic`（Phase 2A，依赖 `fjsp`）、`maintenance`（毕设，生产部分复用 `fjsp` 检查器）。子包之间不得反向依赖。
- 实验脚本在 `experiments/`（`p1_*`、`p2_*`、`g*_*`），共用 `experiments/_common.py`；测试在 `tests/`，按子包分目录。
- 只为有意义的行为写测试：合法性检查器的每类违规、每个算法输出过检查器、确定性/可复现、关键数值回归。不写只为凑覆盖率的测试。

## 分支与证据规则

- 日常开发在 `main` 上进行；功能分支完成后合并回 `main`。每次推送需用户明确同意。
- `experiments/archive/` 是重构前的已归档证据，逐字节不得改写；其 manifest 绑定旧源码，需在分支 `archive/pre-restructure-2026-10-31` 上核验。
- `experiments/results/` 是当前代码的已归档证据，不得改写或删除；新运行写入新目录（`experiments/runs/` 已被忽略）。归档前先提交代码，使 manifest 中 `git_dirty` 为 false。
- 每个结果的 manifest 记录 git 提交和 `src/fjsp_lab` 全部源码的 SHA-256；改动源码后旧结果仍可在其提交上核验，新结论需要重新运行。

## Conda 环境规则

必须使用专用 Conda 环境。

本地路径不要写死在仓库里；默认由脚本创建到项目内 `.conda-env`，也可以通过环境变量 `FJSP_CONDA_ENV` 指定自定义路径。

禁止使用 base。

运行 Python 前必须检查：

python -c "import sys; print(sys.executable)"

输出路径必须是专用环境路径（项目内 `.conda-env` 或 `FJSP_CONDA_ENV` 指向的路径）。

如果环境不存在，先运行：

powershell -ExecutionPolicy Bypass -File .\scripts\setup_env.ps1

需要 PyTorch 的脚本（`experiments/g6_attention_policy.py`）在本机已安装 PyTorch 的环境中运行，不要在项目环境或其他环境重复安装 PyTorch；不需要 PyTorch 时一律用项目专用环境。

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

提交前运行（或 `scripts/run_checks.ps1`）：

pytest
python experiments/p1_static_fjsp.py --time-limit 2
python experiments/p2_dynamic_protocol.py

失败必须如实报告，不允许假装成功。

## AI 编码规则

- 优先小步修改。
- 不要一次性重写整个项目。
- 不要越界实现 AGV、RL、GNN、运输或多目标优化。
- 所有新增功能必须配测试。
- 所有实验结果必须可复现。
- 所有算法结果必须过 feasibility checker。
