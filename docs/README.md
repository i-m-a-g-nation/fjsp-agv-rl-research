# 文档索引

建议的阅读顺序：[项目全景](overview.md) → [模型与算法原理](methods.md) → 按需查 [术语表](glossary.md)。
当前进度只在 [START_HERE](../START_HERE.md) 维护。

## 导读

| 文档 | 内容 |
|---|---|
| [overview.md](overview.md) | 项目全景：研究问题、总体结构图、四个子包、毕设与大创各自的流程图、实验证据链、时间线、目录说明 |
| [project_map.html](project_map.html) | 同一组流程图的网页版，用浏览器打开即可（需联网加载 Mermaid 绘图库） |
| [methods.md](methods.md) | 各个模型与算法的通俗解释：派工规则、CP-SAT、GA/SA/IGA、强化学习、死锁规避、评价方法 |
| [glossary.md](glossary.md) | 术语表：调度、维护、物流、求解方法、强化学习、统计、工程与项目代号 |

## models/：数学模型

| 文档 | 内容 |
|---|---|
| [graduation_model.md](models/graduation_model.md) | 毕设模型的假设、确认过程、变量与约束、固定与联合维护、手算小例 |
| [thesis_ch2_model_zh.tex](models/thesis_ch2_model_zh.tex)（[PDF](models/thesis_ch2_model_zh.pdf)） | 毕设论文第 2 章草稿：多窗口模型、性质证明、NP 难性、构造过程完备性 |
| [logistics_model_zh.md](models/logistics_model_zh.md) | 大创 L1 模型规格：AGV、运输、阻塞、工位容量、检查器、与基准的对应 |
| [math_model_phase1_zh.tex](models/math_model_phase1_zh.tex)（[PDF](models/math_model_phase1_zh.pdf)） | Phase 1 静态 FJSP 数学模型 |
| [math_model_phase2a.tex](models/math_model_phase2a.tex)（[PDF](models/math_model_phase2a.pdf)）、[phase2a_dynamic_model_zh.md](models/phase2a_dynamic_model_zh.md) | Phase 2A 动态模型（英文正式版与中文阅读版） |

## protocols/：实验协议（实验前写好的设计与判定规则）

| 协议 | 对应实验 |
|---|---|
| [phase2a_experiment_protocol.md](protocols/phase2a_experiment_protocol.md) | Phase 2A 动态重调度（243 次运行） |
| [g3a_protocol.md](protocols/g3a_protocol.md)（附 [JSON](protocols/g3a_protocol.json)） | 毕设单窗口：固定 vs 联合维护网格 |
| [g4_periodic_protocol.md](protocols/g4_periodic_protocol.md) | 毕设周期性维护：规则、元启发式与 RL 的质量—时间对比 |
| [g5_supplement_protocol.md](protocols/g5_supplement_protocol.md) | 毕设补充：多种子、模仿消融、RL 热启动 IGA、n = 200 推广 |
| [l2_formal_protocol.md](protocols/l2_formal_protocol.md) | 大创强化学习的正式训练与测试 |

## plans/：计划与设计

| 文档 | 内容 |
|---|---|
| [thesis_outline.md](plans/thesis_outline.md) | 毕设论文大纲：任务书要求与证据对照、章节安排、可写的创新点 |
| [innovation_modeling_decisions.md](plans/innovation_modeling_decisions.md) | 大创建模决策：5 个建模问题的推荐答案与依据 |
| [innovation_rl_design.md](plans/innovation_rl_design.md) | 大创 L2 强化学习设计：决策过程、特征、网络、训练 |

## literature/：文献

| 文档 | 内容 |
|---|---|
| [graduation_literature_map.md](literature/graduation_literature_map.md) | 毕设文献地图：模型来源、派工规则、元启发式、学习型调度，以及本项目的定位 |
| [innovation_novelty_search.md](literature/innovation_novelty_search.md) | 大创查新报告（英文与中文数据库两轮） |

## manuscripts/：论文稿

| 文档 | 内容 |
|---|---|
| [innovation_paper_zh.tex](manuscripts/innovation_paper_zh.tex)（[PDF](manuscripts/innovation_paper_zh.pdf)） | 大创论文初稿（14 页）；标注"待核对/待补全"的参考文献需按原文补全 |

## 关于旧路径

2026-10-31 代码重构后，旧代码在分支 `archive/pre-restructure-2026-10-31`；`experiments/archive/` 里的结果与部分文档仍引用旧路径：

| 旧路径 | 现在的位置 |
|---|---|
| `src/data/`、`src/scheduling/`、`src/solvers/`、`src/vis/` | `src/fjsp_lab/fjsp/` |
| `src/dynamic/`、`src/research/protocol.py` | `src/fjsp_lab/dynamic/` |
| `src/graduation/*` | `src/fjsp_lab/maintenance/` |
| `notes/literature_map_graduation.md` | `docs/literature/graduation_literature_map.md` |

2026-11-06 整理时删除的旧文档（各阶段验收快照、早期文献笔记、长期路线图、CI 工作流等）保存在标签 `pre-cleanup-2026-11-06`，
可用 `git show pre-cleanup-2026-11-06:<路径>` 查看。
