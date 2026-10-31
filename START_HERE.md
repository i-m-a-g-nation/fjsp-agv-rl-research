# 从这里开始

先看这一页即可；原有代码、论文、算例和实验结果都保留在原位置。

| 你现在要做什么 | 打开哪里 |
|---|---|
| 填模型 API | **当前工作树根目录的 `.env`**；配置方法见[模型接口说明](docs/model_interface.md) |
| 找代码、输入和结果 | [项目结构导航](docs/project_structure.md) |
| 一次启动有界科研批次 | [控制器说明](docs/research_controller_validation.md)；审计、候选或拒绝反馈模式 |
| 运行并理解人工审核 | [科研工作流说明](docs/research_workflow.md)；毕设参考求解看[专用使用说明](docs/graduation_workflow.md) |
| 判断课题到底完成了什么 | [研究验收对照](docs/research_acceptance_map.md)；具体工程证据看各验证文档 |

## 目前做到哪里

| 路线 | 已有能力 | 仍未完成 |
|---|---|---|
| 基础平台 | Phase 1 静态 FJSP，已加固整数/不可变输入、原实例绑定和调度归档；Phase 2A 动态事件、冻结历史、重调度 | 后续物流、AGV 等领域扩展；见[Phase 1 使用与评估](docs/reproducibility_phase1.md) |
| 大创 | 要求配置、受监督文献/候选实验路线、已有动态基线协议 | 物流协同、RL 训练及课题验收 |
| 毕设 | G1/G2；有界参考批量执行与归档；`solver_v2` 目标上界验收规则；G3A 参考对照用 v2 重跑完成（exp_035，480/480 接受）；R1/R2；逐动作打分策略（模仿学习 + REINFORCE）；采样解码在等回放次数下优于规则组合（exp_037）；G3B 正式对比完成（exp_038）；智能优化算法 GA/SA/改进 GA 完成（exp_040） | 论文主线已定为改进 GA 为主、RL 作对照（[论文主线](docs/graduation_thesis_outline.md)，待导师确认）；n 最大 24；元启发式文献、甘特图、论文正文；课题验收 |

## 当前卡点与下一步

- **分支**：`codex/phase2a-protocol` 已于 2026-10-30 快进合并到 `main`，此后在 `main` 上继续开发；该分支只作历史保留。
- **毕设 G3A（已完成）**：原批次因验收规则误判 5 份合法排程而 FAILED，记录保持不变。新增 `solver_v2` 后，[exp_035](experiments/results/exp_035_graduation_main_v2_v1/findings.md) 按原协议重跑全部 480 次请求，全部接受。n=8 全部证得最优：固定延期大于 0 时，联合维护使最优总延期平均降低约 30%–56%（取决于机器数和固定策略）；n=24 只有 1 秒限时观察、下界几乎为 0，不能证明最优差。详见 [G3 第 18 节](docs/graduation_g3_protocol_draft.md#18-用-solver_v2-重跑正式网格2026-10-30)。
- **毕设算法**：新的逐动作打分策略（共享 MLP，先模仿最好规则、再用自评 REINFORCE 微调）在 600 个未见测试实例上，平均总延期比 EDD 低约 13%、比 MDD/ATC 低约 4%–5%（3 个种子一致，p < 1e-10）；在证得最优的 G3 n=8 实例上，距最优差距约为单一规则的一半。加入采样解码后，[exp_037](experiments/results/exp_037_sampling_decoding_v1/findings.md) 在全新测试集上按相同回放次数比较：3 次回放比"逐实例三规则取最好"低约 5%，9 次回放比 9 规则组合低约 1%（3 个种子一致）。n24-m2 只是部分修好：3 次回放下 2 个种子领先约 3%、1 个种子落后。按墙钟时间算规则更便宜。详见 [exp_036](experiments/results/exp_036_scoring_policy_v1/findings.md)。旧 REINFORCE 记录保持不变。
- **毕设 G3B（已完成）**：[exp_038](experiments/results/exp_038_g3b_comparison_v1/findings.md) 在 G3 的 480 个正式实例上，最终模型 1 次回放比 MDD 低 8%、3 次回放比三规则取最好低 5.9%；n=24 时比 1 秒 CP-SAT 好 17%–29%，但比 60 秒 CP-SAT 差 6%–11%。策略的价值在于毫秒级速度，不在解的质量。
- **毕设智能优化算法（已完成，影响主线）**：[exp_040](experiments/results/exp_040_metaheuristics_v1/findings.md) 加入 GA、SA、改进 GA（IGA）。SA/IGA 约 0.5 秒达到 n=24 上 CP-SAT 60 秒的水平，n=8 达到证得最优；IGA 消融显示启发式初始解加局部搜索有效。**IGA 约 11 毫秒就比策略 9 次回放（约 82 毫秒）好 2.7%**，所以 exp_038 的"策略快速近似"定位不再成立。按因子看，协同维护在 n=8 上降低总延期 54%（证得最优）、n=24 上 35.5%，维护窗口越宽收益越大（宽窗 64%–68%，窄窗 7%–41%）。
- **大创**：运输、AGV、缓冲区与生产—物流仿真均未实现，[最小范围草案](docs/innovation_minimum_scope_draft.md)尚未获批。
- **下一步候选**（需用户决定优先级）：⓪ 论文主线已定（2026-10-31）：改进 GA 为主方法、RL 作对照，章节与缺口见[论文主线](docs/graduation_thesis_outline.md)；最优先的缺口是 n=50/100 大规模算例（需批准）、元启发式文献和甘特图；① 7 篇付费文献（含 D1、A2）已通读，研究空白在英文文献范围内成立，见[毕设文献地图](notes/literature_map_graduation.md)"核对发现"；ATC 的 k 值已用 [exp_039](experiments/results/exp_039_atc_k2_baseline_v1/findings.md) 复核：文献推荐的 k=2 在本问题上比 k=1 差 14%–16%，原对照更严格、已有结论不变；NP 难归约需导师确认，并请导师取舍候选创新点 I1–I4；② 在动态重调度场景下比较策略与 CP-SAT，把速度优势落到实处（对应 I4）；③ 冻结大创最小物流模型后开始实现。

逐轮的详细进度、预算账本和证据链接见[进度记录](docs/status_log.md)；带日期的验证文档都是当时的快照。

## 先把模型配在哪里

在仓库根目录编辑 `.env`，把密钥填入 `OPENAI_API_KEY=`。其他配置与检查统一看[模型接口说明](docs/model_interface.md)和[模板](.env.example)。当前三个控制器模式均离线运行，不需要 API。

`.env` 是本机忽略文件，不会提交，也不会随分支或另一份工作树检出带过去。`.env.example` 才是版本化模板。

## 文档怎么读

日常先读本页；要运行看[控制器说明](docs/research_controller_validation.md)，要核对毕设假设看[领域模型](docs/graduation_model_draft.md)。找文件看[结构导航](docs/project_structure.md)，开发规则看 [AGENTS.md](AGENTS.md)。`docs/superpowers/` 是开发过程记录，无需逐份阅读，但其中部分计划文件被实验脚本按哈希引用，请勿移动或改写。

完整背景、历史实验表和环境说明在 [中文 README](README.zh-CN.md) / [English README](README.md) 与[实验说明](experiments/README.md)。
