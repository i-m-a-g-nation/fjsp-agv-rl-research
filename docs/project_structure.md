# 项目结构导航

最新增量：[状态提取/语义复核](paper_state_semantic_validation.md)，共享JSON调用在`src/ai_workflow/model_json.py`，复核在`src/ai_workflow/semantic_review.py`；[编码候选](graduation_state_encoding_candidate.md)仍为方案。

最新工具入口：[单字段真实提取](paper_field_validation.md)，程序在 `experiments/exp_023_paper_code_validation.py`，来源工具在 `src/ai_workflow/source_bundle.py`，小结构提取在 `src/ai_workflow/field_extraction.py`。两条短片段max提取及引用定位通过；语义待审，尚无原方法执行或候选应用。此前[整页失败记录](real_paper_code_validation.md)保留。

日常入口是[START_HERE](../START_HERE.md)。本次整理增加导航，不搬动研究目录、数据或历史结果。

## 按工作找文件

| 要做的事 | 位置 | 用法 |
|---|---|---|
| 填模型连接信息 | 根目录 `.env`，模板[`.env.example`](../.env.example) | 本机配置；不提交密钥，详见[模型接口](model_interface.md) |
| 改基础 FJSP 调度 | [`src/data/`](../src/data/)、[`src/scheduling/`](../src/scheduling/)、[`src/solvers/`](../src/solvers/) | 实例、统一结果、严格检查器、规则及 CP-SAT |
| 改动态重调度 | [`src/dynamic/`](../src/dynamic/) | Phase 2A 事件、状态、冻结记录及剩余工序重调度 |
| 改毕设领域模型 | [`src/graduation/`](../src/graduation/) | 同质平行机、交期/总延期、维护；G1/G2、R1 环境和 R2 规则 |
| 改科研执行流程 | [`src/ai_workflow/`](../src/ai_workflow/) | 要求契约、文献/RAG、受限候选、预算、会话与人工审核；不等于算法训练器 |
| 找可执行实验 | [`experiments/`](../experiments/) | `exp_001`–`exp_022` 分别处理不同阶段；按下表挑入口 |
| 找输入 | [`instances/`](../instances/)、[`experiments/protocols/`](../experiments/protocols/)、[`experiments/requests/`](../experiments/requests/) | 静态算例、动态固定协议、毕设参考请求 |
| 找保存的实验依据 | [`experiments/results/`](../experiments/results/) | CSV、报告、计划、manifest；结合输入、源码身份和检查结果阅读 |
| 验证变更 | [`tests/`](../tests/)、[`scripts/`](../scripts/) | pytest、专用环境与检查脚本；规则见[AGENTS.md](../AGENTS.md) |

`src/vis/` 绘制甘特图。`environment.yml` 和 `pyproject.toml` 定义环境与依赖；默认专用环境为根目录 `.conda-env`，自定义位置使用 `FJSP_CONDA_ENV`，不使用 base。

## 三条路线怎样对应代码

| 路线 | 主要代码/入口 | 读状态时的边界 |
|---|---|---|
| 基础平台 | 静态 `src/data` / `scheduling` / `solvers`；动态 `src/dynamic` | Phase 2A 已有动态底座；不能据此声称 AGV、物流或 RL 已实现 |
| 大创 | `src/ai_workflow` 中 innovation 要求配置与受监督路线 | 文献/静态候选及已有动态协议只是基础证据，研究目标未验收 |
| 毕设 | `src/graduation`；`src/ai_workflow/graduation_backend.py` 对接 G1/G2 | 三审只接 G1/G2；R1/R2 独立使用，无 Gym/PPO 训练，正式 G3 未执行 |

算法返回结果仍须通过对应合法性检查。`OPTIMAL` 才能作本地最优证明；`FEASIBLE` 仅为限时可行参考。工作流 `COMPLETED` 只表示一次执行与审核结束。

## 常用实验与证据

| 目的 | 实验入口 | 解释文档/保存证据 |
|---|---|---|
| 静态基础与求解器对照 | [`exp_001`](../experiments/exp_001_toy_instance.py)、[`exp_002`](../experiments/exp_002_solver_check.py) | [Phase 1 复现清单](reproducibility_phase1.md) |
| 动态固定协议 | [`exp_019`](../experiments/exp_019_phase2a_protocol.py) | [协议与验证](phase2a_experiment_protocol.md)；`results/exp_019_phase2a_protocol_v1/` |
| 连续动态事件 | [`exp_020`](../experiments/exp_020_sequential_reschedule.py) | [顺序重放验证](phase2a_sequential_validation.md)；`results/exp_020_sequential_reschedule_v1/` |
| 毕设 G2 参考解 | [`exp_021`](../experiments/exp_021_graduation_solver_check.py) | [G2 验证](graduation_g2_validation.md)；`results/exp_021_graduation_g2_v1/` |
| 毕设 R2 规则开发验证 | [`exp_022`](../experiments/exp_022_graduation_rule_smoke.py) | [R2 验证](graduation_r2_validation.md)；`results/exp_022_graduation_rules_v1/`；小例不是正式性能实验 |
| 受监督三审入口 | [`exp_018`](../experiments/exp_018_ai_rag_workflow.py) | [通用工作流](research_workflow.md) / [毕设 G1/G2 路线](graduation_workflow.md) |

上表 `results/` 均相对于 `experiments/`。运行产生的 `experiments/runs/`、`experiments/ai_memory/` 是本地忽略目录，不保证随 Git 克隆存在；每次运行使用新目录，保留已有证据。

## 文档、笔记和研究证据分别看哪里

- **已实现能力及验证证据**：`docs/*_validation.md`、[Phase 2A 交付自检](phase2a_acceptance.md)、[验收对照](research_acceptance_map.md)，以及相应 `experiments/results/` 原始产物。报告要结合源码/输入身份阅读。
- **模型与设计草案**：`docs/math_model_*`、`docs/*_draft.*`。文件存在不代表功能落地或协议已冻结，尤其 [G3 草案](graduation_g3_protocol_draft.md) 和 [RL 方案](graduation_rl_design_draft.md)。
- **文献与阅读材料**：[`papers/`](../papers/) 是文献分类索引；[`notes/`](../notes/) 保存阅读、审查及讨论笔记。内容需核对原文，不能替代实验结果或验收。
- **开发历史**：[`docs/superpowers/`](superpowers/) 保存开发规格、计划与过程记录；[review_status.md](review_status.md) 汇总审查历史。日常不必逐份阅读，先从对应能力的使用/验证文档进入。
- **未来目标**：[自动科研迭代需求](autonomous_research_loop_requirements.md) 记录尚待实现的目标，不是现有执行器的使用手册。
