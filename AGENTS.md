# FJSP-AGV-RL Research Project Rules

本项目研究柔性作业车间调度 FJSP，后续扩展 AGV、动态扰动与强化学习。

当前阶段：Phase 1 与 Phase 2A 已完成工程交付并进入维护；毕设路线按下文“已放行的扩展”逐步推进。当前进度与下一步只在 `START_HERE.md` 维护。

## 已放行的扩展（毕设路线）

以下内容已在用户确认的毕设范围内实现，代码在 `src/fjsp_lab/maintenance/`，模型见 `docs/models/graduation_model.md`，各阶段的批准时间见 `START_HERE.md` 与 git 历史（整理前的历史文档在标签 `pre-cleanup-2026-11-06`）：

- G1：同质平行机、每任务一道工序、0 时刻到达、每机一次必需维护（时间窗内）、总延期目标，及其数据与合法性检查器。
- G2：固定/联合维护的小规模 CP-SAT 参考模型与独立枚举核对。
- R1/R2：有限步、带动作掩码的调度构造环境及 EDD/MDD/ATC 规则基线。
- 智能优化算法：GA、SA、改进 GA（IGA）。
- 学习型构造策略（仅用于上述毕设简化模型）：NumPy 逐动作打分 MLP（模仿 + REINFORCE）；PyTorch 注意力策略（模仿 IGA 教师 + REINFORCE，共享基线，无 PPO）。

## 已放行的扩展（大创路线）

2026-11-01 用户批准大创第一阶段 L1，代码在 `src/fjsp_lab/logistics/`（只依赖 `fjsp`），模型见 `docs/models/logistics_model_zh.md`，建模依据见 `docs/plans/innovation_modeling_decisions.md`：

- L1：柔性作业车间 + 同质单载 AGV（显式空驶与载货行驶、L/U 站）+ 机器输入缓冲有限/无限 + 加工后阻塞；
  数据结构、事件仿真器、协同检查器、规则基线、静态小规模 CP-SAT 参考模型。**不含强化学习。**
- L1 扩展（2026-11-02 获批）：前瞻式死锁规避（规则基线的扩充）；大算例参考用的元启发式（SA 为参考方法，GA 为对照）。
- L2（2026-11-02 获批）：大创强化学习——单智能体逐候选打分策略（先模仿规避规则，再 REINFORCE、共享基线），前瞻式死锁规避作为动作掩码；先做小规模试训。不含 PPO、多智能体、动态事件。设计见 `docs/plans/innovation_rl_design.md`。

每个新阶段（例如正式 G3 批次、PPO、新的训练预算、大创的 RL 或动态事件阶段）仍需用户单独批准，已有批准不自动延伸。

## 当前禁止事项

除非用户明确要求，否则禁止实现：

- 超出 L1/L2 的 AGV 内容：路径冲突与碰撞、充电、异构或多载 AGV；大创的 PPO、多智能体强化学习与动态事件（尚未获批）。
- 毕设简化模型与大创 L2 以外的强化学习，以及 DQN、PPO、GNN、多智能体强化学习。
- 能耗目标。
- 多目标 Pareto 优化。

这些是后续阶段。

## 代码结构

- 库代码只在 `src/fjsp_lab/`：`fjsp`（Phase 1）、`dynamic`（Phase 2A，依赖 `fjsp`）、`maintenance`（毕设，生产部分复用 `fjsp` 检查器）、`logistics`（大创 L1，生产部分复用 `fjsp` 检查器）。子包之间不得反向依赖。
- 实验脚本在 `experiments/`（`p1_*`、`p2_*`、`g*_*`、`l1_*`、`l2_*`），共用 `experiments/_common.py`；测试在 `tests/`，按子包分目录。
- 文档：`README.md`（入口）、`START_HERE.md`（进度，唯一维护处）、`docs/overview.md`（全景与流程图）、`docs/methods.md`（原理）、
  `docs/glossary.md`（术语）；`docs/models|protocols|plans|literature|manuscripts` 分别放模型、协议、计划、文献、论文稿。
  新增子包、实验批次或方法时，同步更新 overview 的图与表、methods 的对应小节和 glossary 的新术语。
- 已删除的旧文档（`docs/history/`、早期文献笔记、CI 工作流等）在标签 `pre-cleanup-2026-11-06` 中可查。

## 新会话接手

1. 依次读 `START_HERE.md`、本文件、相关的协议或计划文档；不要凭记忆假设进度。
2. 先跑一遍检查确认环境与代码状态（`pytest`，项目专用环境）；PyTorch 相关测试在 PyTorch 环境里单独跑。
3. 有一个 `git stash`（`stash@{0}`）保存着重构前另一会话的未提交修改，用户选择不提交；未经用户同意不要应用或删除。

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

FJSP 实例统一为 `jobs[job_id][op_id] = [(machine_id, processing_time), ...]`；所有算法必须返回统一 ScheduleResult（记录至少含 job_id、op_id、machine_id、start、end、processing_time）。

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

## 求解器结果的表述

CP-SAT 求解必须设 time limit。只有 solver status 为 OPTIMAL 时才能说最优；FEASIBLE 只能说限时可行参考解。

## 测试要求

提交前运行（或 `scripts/run_checks.ps1`）：

pytest
python experiments/p1_static_fjsp.py --time-limit 2
python experiments/p2_dynamic_protocol.py

失败必须如实报告，不允许假装成功。

新增功能须配测试，但只为有意义的行为写测试：合法性检查器的每类违规、每个算法输出过检查器、确定性/可复现、关键数值回归。不写只为凑覆盖率的测试。
