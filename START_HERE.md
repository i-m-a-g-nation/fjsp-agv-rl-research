# 从这里开始

先看这一页即可；原有代码、论文、算例和实验结果都保留在原位置。

| 你现在要做什么 | 打开哪里 |
|---|---|
| 填模型 API | **当前工作树根目录的 `.env`**；配置方法见[模型接口说明](docs/model_interface.md) |
| 找代码、输入和结果 | [项目结构导航](docs/project_structure.md) |
| 运行并理解人工审核 | [科研工作流说明](docs/research_workflow.md)；毕设参考求解看[专用使用说明](docs/graduation_workflow.md) |
| 判断课题到底完成了什么 | [研究验收对照](docs/research_acceptance_map.md)；具体工程证据看各验证文档 |

## 目前做到哪里

| 路线 | 已有能力 | 仍未完成 |
|---|---|---|
| 基础平台 | Phase 1 静态 FJSP；Phase 2A 动态事件、冻结历史、重调度与合法性检查 | 后续物流、AGV 等扩展 |
| 大创 | 要求配置、受监督文献/候选实验路线、已有动态基线协议 | 物流协同、RL 训练及课题验收 |
| 毕设 | G1 生产/维护检查；G2 固定/联合 CP-SAT 参考；R1 无训练构造环境；R2 EDD/SPT/Random | Gym/PPO 适配与训练、正式 G3 对照及课题验收 |

R1/R2 目前通过独立 API 和 `exp_022` 开发验证使用，尚未接入三审工作流。仓库程序仍是受监督执行器；聊天中的编码代理能改代码，不代表程序已经能自主读论文、改算法和训练。

## 先把模型配在哪里

在**当前打开的这份工作树**根目录编辑 `.env`，把密钥填入 `OPENAI_API_KEY=`。其余首选值已放在[`.env.example`](.env.example)：官方 DeepSeek 地址、`deepseek-flash`、显式开启 max 思考，以及本地 RAG。检查命令见[模型接口说明](docs/model_interface.md)。

`.env` 是本机忽略文件，不会提交，也不会随分支合并带到另一份检出目录。`.env.example` 才是版本化模板。现在无需先合并到 main 才能配置或检查这份工作树。

2026-10-26 已完成[首次真实 API 诊断](docs/model_api_validation_2026-10-26.md)：接口已连通；非思考模式样本出现一个计划/指标不一致及引用缺项。检查器拒绝错误指标，算法源码未因此改变；这不表示自动科研循环已经完成。

同日已切换并验证[max 思考及引用反馈](docs/model_api_max_validation_2026-10-26.md)：真实请求 enabled/max，两个短样本通过；在线引用缺项最多纠正一次，仍不完整即停止代码生成。每次请求明确采用 8192 tokens / 60 秒，累计会话预算不变。

最新[单字段真实提取](docs/paper_field_validation.md)：短片段下 Flash enabled/max 两次正常返回，奖励常数及动作表示引用2/2定位完整；仍待语义审核，无训练或算法应用。此前[整页提取失败](docs/real_paper_code_validation.md)及预算完整保留，现有维护模型保持。

完整背景、历史实验表和环境说明仍在 [中文 README](README.zh-CN.md) / [English README](README.md)。
