# 从这里开始

当前进度与下一步只在本页维护。代码结构见 [README](README.md)，开发规则见 [AGENTS.md](AGENTS.md)，实验索引见 [experiments/README.md](experiments/README.md)。

## 新会话接手须知（先读这一节）

1. 依次读本页、[AGENTS.md](AGENTS.md)（规则与禁止事项）、相关的协议或计划文档；不要凭记忆假设进度。
2. 先跑一遍检查，确认环境和代码状态：`pytest`（项目专用环境，应为 170 passed、2 skipped）。
   PyTorch 相关测试在 PyTorch 环境里单独跑。
3. **需要用户批准的事**：
   - 任何新阶段：新的训练预算、更大规模、PPO、大创 AGV 建模等，已有批准不自动延伸；
   - 每一次 `git push`；
   - 在任何环境里安装新包。
4. **证据规则**：
   - 正式实验先提交代码，再用 `--output-dir experiments/results/<名称>` 运行，manifest 中 `git_dirty` 必须为 false；
   - 计时实验运行时不要在本机并行跑其他重计算（G4 就因此重跑过）；
   - 预先登记的假设要如实报告；看到结果后补充的分析标明"探索性"。
5. `experiments/archive/` 与 `experiments/results/` 中已归档的文件不得修改。
6. 有一个 `git stash`（`stash@{0}`）保存着重构前另一会话对 START_HERE、文献地图的未提交修改，用户选择不提交，未经用户同意不要应用或删除。

## 环境

| 用途 | 环境 |
|---|---|
| 除注意力策略外的全部代码与测试 | 项目专用 Conda 环境（`.conda-env` 或 `FJSP_CONDA_ENV`） |
| `experiments/g6_attention_policy.py`、`g8_g4_policy_curves.py`（PyTorch，GPU） | 本机已有的 PyTorch 环境；不重复安装 PyTorch |

## 各路线状态（2026-11-01）

| 路线 | 已有 | 未完成 |
|---|---|---|
| Phase 1 静态 FJSP | 实例/读取、7 条规则、CP-SAT、检查器、甘特图；30 个 FJSPLib 实例；极端输入回归测试 | —（维护中） |
| Phase 2A 动态 | 三类事件、冻结、基线重调度、动态检查器；243 次协议运行全部通过 | 物流/AGV 等扩展 |
| 毕设（平行机 + 维护） | 单窗口与周期性多窗口模型、检查器、CP-SAT（与枚举核对）、EDD/MDD/ATC、GA/SA/IGA、NumPy 打分策略、注意力策略（解码器 MDP）；G3A 与 G4 实验；甘特图示例；论文大纲（RL 主线） | 导师确认、消融（需批准）、文献、论文正文 |
| 大创（生产—物流协同） | 共用底座（FJSP、动态层、检查器分层方式、RL 方法可迁移） | 运输、AGV、缓冲区、仿真、协同算法、论文均未开始；[最小范围草案](docs/plans/innovation_scope_draft.md)未获批 |

## 关键结果

- **固定 vs 联合维护**：
  - G3A 中 n=8 证得最优，联合维护降低约 30%–56%（[exp_035](experiments/archive/exp_035_graduation_main_v2_v1/findings.md)）；
  - G4 中 n=20/50/100 平均降低 49%/11%/7%，窗口越宽收益越大。
- **G4 质量—时间对比**（[findings](experiments/results/g4_summary/findings.md)）：
  - n=100、0.2–2 s 内 RL 显著优于 IGA/SA，与最好解的差距约为 IGA 的 1/3；
  - n=50 时与 IGA 持平；n=20 和长时间预算时 IGA/SA 更好；
  - 预先登记的 H1 不成立（单次 GPU 推理就需要 0.15–0.32 s），H2 部分成立，H3 成立。
- **RL 训练**：先模仿 IGA-5000，再做 1696 步 REINFORCE；验证集均值 52.17，低于教师（53.88）和 MDD（63.28）。
- **单窗口小规模**（exp_036–041，归档）：IGA 优于早期打分策略；用来说明 RL 的适用范围。
- **基座可靠性**：
  - 极端输入（10¹² 时间、空闲机器、零余量窗口、超长作业等）全部正确求解或明确拒绝；
  - 64 个小问题上，两种构造方式都能达到证得的最优值；
  - 以上都在回归测试中。

## 下一步（待用户决定）

1. **毕设**：请导师确认[论文大纲](docs/plans/thesis_outline.md)的主线与创新点。之后可选：
   - 消融：只做模仿的检查点测试集评估、多训练种子（需批准训练预算）；
   - 加快单实例推理（CPU/编译），把 RL 曲线左移；
   - 文献补充（含知网）；
   - 写正文。
2. **大创**：先确认[最小范围草案](docs/plans/innovation_scope_draft.md)中的 5 个建模问题并批准范围，再新建 `fjsp_lab.logistics`（只依赖 `fjsp`），做法沿用"原检查器不改、外加一层检查"。用户希望 2027 年 3 月前完成。
3. 可选：用新代码重跑单窗口 G3A 的 `g1 --long`、g2–g4。

## 已知局限（扩展前需注意）

- 构造环境和解码器"维护尽量提前、作业靠左"的简化只对正则目标（完工越早越好）成立；若改为提前也受罚、按时段计费等目标，需要重新设计。
- 两种构造方式能达到最优只在小规模上穷举验证过，没有数学证明。
- `ScheduleResult` 目前是可修改对象，靠实验脚本对每个结果再检查一遍兜底。
- 单窗口生成器最多支持 4 台机器；周期性生成器不限。

## 文档

- 模型：[毕设模型](docs/models/graduation_model.md)、[论文第 2 章草稿（模型与证明，LaTeX/PDF）](docs/models/thesis_ch2_model_zh.tex)、Phase 1/2A 数学模型（`docs/models/`）
- 协议：[G4 协议](docs/protocols/g4_periodic_protocol.md)、[G3A 协议](docs/protocols/g3a_protocol.md)、[Phase 2A 协议](docs/protocols/phase2a_experiment_protocol.md)
- 2026-10-31 重构：旧代码在分支 `archive/pre-restructure-2026-10-31`，新旧结果一致性见 [restructure_equivalence](experiments/archive/restructure_equivalence/)
- 计划：[路线图](docs/plans/ROADMAP.md)、[论文大纲](docs/plans/thesis_outline.md)、[大创草案](docs/plans/innovation_scope_draft.md)
- 文献：[毕设文献地图](notes/literature_map_graduation.md)
- 历史验收快照（引用旧路径）：`docs/history/`
