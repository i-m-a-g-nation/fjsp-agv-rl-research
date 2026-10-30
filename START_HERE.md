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
| 毕设 | G1/G2；有界参考批量执行与归档；R1/R2、可逆编码及有界REINFORCE试训 | 求解器报告目标与返回解不一致已复现，修复待验证；训练效果仍弱于EDD；完整G3/RL比较与课题验收 |

## 当前卡点与下一步

- **分支**：`codex/phase2a-protocol` 已于 2026-10-30 快进合并到 `main`，此后在 `main` 上继续开发；该分支只作历史保留。
- **毕设卡点**：正式参考尝试 480 次请求中 5 次出现“求解器报告目标 ≠ 返回计划重算延期”，整批记为 FAILED；475 份有效计划已独立重算通过。关闭预处理的一次对照证据不足，补救方案未确认。
- **毕设算法**：有界 REINFORCE 试训仍弱于 EDD；学习率反馈候选已被拒绝。PPO、正式 G3 对照与课题验收未完成。
- **大创**：运输、AGV、缓冲区与生产—物流仿真均未实现，[最小范围草案](docs/innovation_minimum_scope_draft.md)尚未获批。
- **下一步候选**（需用户决定优先级）：① 确定一致性错误的处理规则或保持模型语义的补救，再做正式 G3 比较；② 推进毕设最终算法；③ 冻结大创最小物流模型后开始实现。

逐轮的详细进度、预算账本和证据链接见[进度记录](docs/status_log.md)；带日期的验证文档都是当时的快照。

## 先把模型配在哪里

在仓库根目录编辑 `.env`，把密钥填入 `OPENAI_API_KEY=`。其他配置与检查统一看[模型接口说明](docs/model_interface.md)和[模板](.env.example)。当前三个控制器模式均离线运行，不需要 API。

`.env` 是本机忽略文件，不会提交，也不会随分支或另一份工作树检出带过去。`.env.example` 才是版本化模板。

## 文档怎么读

日常先读本页；要运行看[控制器说明](docs/research_controller_validation.md)，要核对毕设假设看[领域模型](docs/graduation_model_draft.md)。找文件看[结构导航](docs/project_structure.md)，开发规则看 [AGENTS.md](AGENTS.md)。`docs/superpowers/` 是开发过程记录，无需逐份阅读，但其中部分计划文件被实验脚本按哈希引用，请勿移动或改写。

完整背景、历史实验表和环境说明在 [中文 README](README.zh-CN.md) / [English README](README.md) 与[实验说明](experiments/README.md)。
