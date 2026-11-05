# 文档

| 目录 | 内容 |
|---|---|
| `models/` | 数学模型：Phase 1 静态 FJSP（中/英 PDF 与 LaTeX）、Phase 2A 动态模型、[毕设模型](models/graduation_model.md)、[毕设第 2 章草稿](models/thesis_ch2_model_zh.tex)（[PDF](models/thesis_ch2_model_zh.pdf)）、[大创物流模型](models/logistics_model_zh.md) |
| `protocols/` | 预先确定的实验协议：[G3A](protocols/g3a_protocol.md)（固定 vs 联合维护网格，含 solver_v2 验收规则说明）、[G4](protocols/g4_periodic_protocol.md)（周期性维护质量—时间对比）、[L2 正式训练与测试](protocols/l2_formal_protocol.md)、[Phase 2A](protocols/phase2a_experiment_protocol.md) |
| `manuscripts/` | 论文稿：[大创论文初稿](manuscripts/innovation_paper_zh.tex)（[PDF](manuscripts/innovation_paper_zh.pdf)） |
| `plans/` | [论文大纲](plans/thesis_outline.md)；大创：[最小范围草案](plans/innovation_scope_draft.md)、[建模决策](plans/innovation_modeling_decisions.md)、[查新报告](plans/innovation_novelty_search.md)、[RL 设计](plans/innovation_rl_design.md) |
| `history/` | 各阶段当时的验收与验证快照（G1/G2/R1/R2、Phase 1/2A 验收、研究验收对照）及 2026-07 长期路线图 `ROADMAP_2026-07.md`；文中代码路径是重构前的旧路径，结论以对应归档结果为准 |

当前进度只在 [START_HERE](../START_HERE.md) 维护。代码与文档中的旧路径对应关系：

| 旧路径 | 新位置 |
|---|---|
| `src/data/`、`src/scheduling/`、`src/solvers/`、`src/vis/` | `src/fjsp_lab/fjsp/` |
| `src/dynamic/`、`src/research/protocol.py` | `src/fjsp_lab/dynamic/` |
| `src/graduation/*`（data、result、feasibility、solver_v2、enumeration、rl_environment、dispatch_rules、action_features、metaheuristics、scoring_policy、attention_policy、teacher_data、reference_main_protocol） | `src/fjsp_lab/maintenance/` |
| `experiments/results/` | `experiments/archive/` |
