# 从这里开始

当前进度与下一步只在本页维护。代码结构见 [README](README.md)，开发规则见 [AGENTS.md](AGENTS.md)，实验索引见 [experiments/README.md](experiments/README.md)。

## 新会话接手须知（先读这一节）

1. 依次读本页、[AGENTS.md](AGENTS.md)（规则与禁止事项）、相关的协议或计划文档；不要凭记忆假设进度。
2. 先跑一遍检查，确认环境和代码状态：`pytest`（项目专用环境，应为 222 passed、2 skipped）。
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

## 各路线状态（2026-11-03）

| 路线 | 已有 | 未完成 |
|---|---|---|
| Phase 1 静态 FJSP | 实例/读取、7 条规则、CP-SAT、检查器、甘特图；30 个 FJSPLib 实例；极端输入回归测试 | —（维护中） |
| Phase 2A 动态 | 三类事件、冻结、基线重调度、动态检查器；243 次协议运行全部通过 | 物流/AGV 等扩展 |
| 毕设（平行机 + 维护） | 单窗口与周期性多窗口模型、检查器、CP-SAT（与枚举核对）、EDD/MDD/ATC、GA/SA/IGA、NumPy 打分策略、注意力策略（解码器 MDP）；G3A 与 G4 实验；甘特图示例；论文大纲（RL 主线） | 创新点取舍、消融（需批准）、文献、论文正文 |
| 大创（生产—物流协同） | L1（2026-11-01 获批）：[物流模型](docs/models/logistics_model_zh.md)、`fjsp_lab.logistics`（算例读取、协同检查器、事件仿真器、联合/解耦规则、CP-SAT）；建模决策与两轮查新；[基准对齐与缓冲实验](experiments/results/l1_benchmark/findings.md)、[联合与解耦差距](experiments/results/l1_decoupled/findings.md)、[大算例与死锁规避](experiments/results/l1_large/findings.md)、[元启发式参考](experiments/results/l1_search/findings.md)；L2 强化学习（2026-11-02 获批）：`logistics.policy`、[正式训练](experiments/results/l2_formal_train/)与[正式测试](experiments/results/l2_formal_test/findings.md) | 论文初稿已完成（[大创论文](docs/manuscripts/innovation_paper_zh.tex)，待补全文献与定稿）；阻塞感知邻域（可选）；动态事件（需批准） |

## 关键结果

- **大创 L1**（[findings](experiments/results/l1_benchmark/findings.md)）：
  - 模型语义与公开 FJSPT 基准对齐：Deroussi & Norre 的 10 个参考解重放后全部复现报告值；
  - CP-SAT 在 9 个算例上证得与参考值相同的最优值；fjsp7 找到 108，比公开的 112 更好（最优值在 [104, 108]）；
  - 阻塞 + 无缓冲使最优值平均上升 6.8%–12.8%，B ≥ 1 时影响不到约 1%（算例小）；
  - 规则比 CP-SAT 差 24%–51%；联合贪心规则 EFT 不优于解耦规则（探索性）；
  - **联合与解耦的差距**（[findings](experiments/results/l1_decoupled/findings.md)）：先排机器、再优化车辆，平均比联合 CP-SAT 差 10%（不计运输）或 5%（计入载货行驶）；
    阻塞 + 无缓冲时升到 17%–20%，且有 2–3/10 的机器方案根本无法执行；95 个可执行情况里联合全部严格更好；
  - **大算例**（[findings](experiments/results/l1_large/findings.md)，Brandimarte 6 个 + Homayouni & Fontes 布局）：B ≤ 2 时普通规则常死锁（B=0 几乎全部）；
    前瞻式死锁规避 420 次全部给出合法调度；缓冲效应明显（最好规则相对基准 +4%/+6%/+12%/+52%，对应 B=∞/2/1/0）；CP-SAT 不再适用；
  - **元启发式参考**（[findings](experiments/results/l1_search/findings.md)）：SA 在小算例上距证得最优约 8%–12%（规则 24%–51%），大算例上比最好规则好 2%–8%；
    以 SA 为参考的缓冲效应 +4%/+3%/+9%/+41%（B=∞/2/1/0），与规则结论一致；阻塞时搜索效率低（邻域多退回优先级解码）。
- **大创 L2 正式测试**（[findings](experiments/results/l2_formal_test/findings.md)，[协议](docs/protocols/l2_formal_protocol.md)，3 个训练种子，测试集只用一次）：
  - 预先登记的 H1–H4 在 3 个种子上全部成立：贪心策略优于 EFT；采样 32 次优于逐实例最好规则；同等时间下采样 32 次优于 SA（大算例 27–28/30，小算例幅度只有约 2%）；
  - 大算例（Brandimarte，比训练算例大）：采样 32 次比逐实例最好规则好 16%，比大预算 SA 参考好约 10%（24–26/30）；贪心与大预算 SA 持平；
  - 小算例：采样 32 次距证得最优约 12.5%（贪心约 21%），仍比大预算 SA 差约 3%；
  - B=0 最弱（大算例上仍比大预算 SA 差 4%）；大算例采样 32 次平均 11 s（有限缓冲时 16–20 s）。
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

1. **毕设**：方向由用户（学生）决定，不需导师确认（2026-11-04 说明）；主线已定为 RL（2026-10-31），创新点表述见[论文大纲](docs/plans/thesis_outline.md)，由用户取舍。
   - **G5 补充实验（2026-11-04 批准，进行中）**：[协议](docs/protocols/g5_supplement_protocol.md)。新测试集（种子 1003/1004）与 n=200 推广集；
     训练种子 1、2 与只模仿检查点（E1/E2）、RL 热启动 IGA（E3）、规模推广（E4）；预先登记 H1–H5。
     运行顺序：训练（GPU）→ 策略推理 → 搜索曲线与热启动 IGA（CPU，与训练错开）→ `g12_g5_summary.py`；
   之后可选：
   - 加快单实例推理（CPU/编译），把 RL 曲线左移；
   - 文献补充（含知网）；
   - 写正文。
2. **大创**：L1 代码已完成（[物流模型](docs/models/logistics_model_zh.md)；建模依据见[建模决策建议](docs/plans/innovation_modeling_decisions.md)，查新见[查新报告](docs/plans/innovation_novelty_search.md)）。接下来：
   - 基准对齐与缓冲实验已完成（见关键结果），算例在本地 `instances/external/FJSPT`（无许可证，不入库）；
   - 解耦优化对照已完成（见关键结果）；
   - 大算例实验与前瞻式死锁规避已完成（见关键结果），布局在本地 `instances/external/HomayouniFontes`；
   - 元启发式参考（SA/GA，2026-11-02 获批）已完成，见关键结果；
   - **L2 强化学习（2026-11-02 获批）**：[设计](docs/plans/innovation_rl_design.md)、`logistics.generator`、`logistics.policy` 已实现；
     两次试训（只用训练/验证集，未归档，`experiments/runs/l2_policy_pilot_v1|v2`）：模仿 + REINFORCE 60 轮后，贪心策略比单一规则 EFT 好约 8%，
     与"逐实例 4 条规则取最好"基本持平（1.016）；每实例采样 8/32 次取最好可好约 5%/8%。B=0 时最弱。验证集同时用于选模型，数字偏乐观；
   - **L2 正式训练与测试已完成**（[协议](docs/protocols/l2_formal_protocol.md) 2026-11-03 获批；结果见关键结果）。测试集已使用，不得再用于调参；
   - **论文初稿**（2026-11-04）：[innovation_paper_zh.tex](docs/manuscripts/innovation_paper_zh.tex)（[PDF](docs/manuscripts/innovation_paper_zh.pdf)），14 页；参考文献中标注"待核对/待补全"的条目需按原文补全，投稿前再做一次数据库检索；
   - 可选的后续（均需批准）：针对 B=0 的改进、加快大算例采样（并行或减少 `is_safe` 回放）、消融（只模仿 / 无掩码）；
   - 之后的动态事件等阶段需用户单独批准（方向同样由用户决定，不需导师确认）。用户希望 2027 年 3 月前完成。
3. 可选：用新代码重跑单窗口 G3A 的 `g1 --long`、g2–g4。

## 已知局限（扩展前需注意）

- 构造环境和解码器"维护尽量提前、作业靠左"的简化只对正则目标（完工越早越好）成立；若改为提前也受罚、按时段计费等目标，需要重新设计。
- 两种构造方式能达到最优只在小规模上穷举验证过，没有数学证明。
- 单窗口生成器最多支持 4 台机器；周期性生成器不限。

## 文档

- 论文稿：[大创论文初稿](docs/manuscripts/innovation_paper_zh.tex)
- 模型：[毕设模型](docs/models/graduation_model.md)、[论文第 2 章草稿（模型与证明，LaTeX/PDF）](docs/models/thesis_ch2_model_zh.tex)、Phase 1/2A 数学模型（`docs/models/`）
- 协议：[G4 协议](docs/protocols/g4_periodic_protocol.md)、[G3A 协议](docs/protocols/g3a_protocol.md)、[Phase 2A 协议](docs/protocols/phase2a_experiment_protocol.md)
- 2026-10-31 重构：旧代码在分支 `archive/pre-restructure-2026-10-31`，新旧结果一致性见 [restructure_equivalence](experiments/archive/restructure_equivalence/)
- 计划：[论文大纲](docs/plans/thesis_outline.md)、[大创草案](docs/plans/innovation_scope_draft.md)
- 文献：[毕设文献地图](notes/literature_map_graduation.md)
- 历史验收快照（引用旧路径）：`docs/history/`
