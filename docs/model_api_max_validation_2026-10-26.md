# Max 思考与引用反馈验证：2026-10-26

**本次确实发送了 Flash 的 max 思考请求；两个短样本均通过本次检查。** 上次记录明确是 `thinking=disabled`，不代表 max 档效果；[原始非思考诊断](model_api_validation_2026-10-26.md)保留不改。

## 怎么确认是 max

本地 `.env` 与新模板现在显式设置：

```dotenv
LLM_MODEL_NAME=deepseek-flash
LLM_THINKING_MODE=enabled
LLM_REASONING_EFFORT=max
LLM_MAX_OUTPUT_TOKENS=8192
LLM_REQUEST_TIMEOUT_SECONDS=60
```

依照[官方思考模式文档](https://api-docs.deepseek.com/guides/thinking_mode/)，max 是思考开关与 effort 的组合。两个模型调用入口均有 SDK 内存 HTTP 测试；本次真实请求也用 HTTP hook 记录最终字段，均为：

```json
{"model":"deepseek-flash","thinking":{"type":"enabled"},"reasoning_effort":"max","max_tokens":8192}
```

路径为 `/chat/completions`，未发送 `max_completion_tokens`。两次服务端均返回 HTTP 200、`finish_reason=stop` 及非零 reasoning token 计数。这确认客户端请求了官方 max 且返回中有思考输出；不是对供应商内部计算过程的独立认证。没有保存或展示思考正文、鉴权请求头或密钥。

## 实际结果

使用与上次相同的人工构造输入，不获取真实论文，不建立新的工作流会话，也不生成代码或人工批准。

| 项目 | 本次结果 |
|---|---|
| 单机两任务，固定维护 | 总延期 4，正确 |
| 同题联合维护 | 总延期 0、维护开始 4，已通过已有 G1 检查器的计划重建 |
| 目标公式 | 正确提取总延期公式 |
| 未提供的 RL 内容 | 状态、动作、掩码、奖励和网络均为空 |
| 引用位置 | 7 条陈述 / 7 条可定位引用，首次提取即完整 |
| 证据状态 | 仍为 `unverified`，未自动认定论文内容、创新性或课题完成 |

本次只用了 2 次调用，没有触发第三次纠正。累计执行 53.234 秒；输出 token 实际合计 9975（含思考），预占 16384，诊断允许的上限是 3 次 / 24576 / 180 秒，每次超时 60 秒、SDK 重试 0。

提取请求的完成 token 是 **8156/8192**，其中 reasoning tokens 为 **7516**，最终回答部分约 640。它正常结束，但非常接近上限。为避免本地 max 配置仍沿用 4096/30 而截断，将本次已验证的 8192/60 做成显式环境配置入口；未配置时的构造器默认仍是 4096/30，硬上限保持 8192/60。该配置入口调整发生在诊断之后，诊断本身已经显式采用同样的 8192/60，未因此追加真实调用。

持久会话默认累计预算仍是 120 秒 / 16384 输出 token 预占。两个 8192 请求会用完输出预占；若“提取 + 一次纠正”均发生，后续生成可能因预算不足停止，这是保留的预算边界，不会自动放大。

本次同时改变了思考模式和输出/时间预算；样本只有两个，不能据此单独归因于 max、统计模型优劣或保证长论文质量。引用定位完整也不证明语义支持、变量归类或公式正确。

## 工作流实际完善了什么

- 每次在线提取都重新对照原文审计，逐字段发现缺失、无效和未消歧引用；最多反馈一次，沿用累计预算。
- 每次报告立即保存在会话的 `extraction-attempts.json`；第二次调用报错或预算耗尽也保留第一份材料及安全的错误类型。
- 两次完成提取仍不完整时，以 `EVIDENCE_INCOMPLETE` 停止，代码生成、沙箱和实验记忆均不执行。
- 完整提取仍进入原有 evidence 人审。显式降级策略保持 `degraded` 标签，失败原文提取历史不会被模板覆盖；预算失败类型保持不变。

独立审查发现并修复了“纠正异常丢失首次材料”，复审及最终配置审查未发现新可执行问题。真正需要人工判断的仍是来源支持关系、模型假设、研究范围与结论；本轮没有实现论文源码复用、RL 训练或性能驱动的自动研究循环。

## 可查证材料

- [真实调用记录](../experiments/results/model_api_max_validation_20261026_v1/result.json)：请求白名单字段、响应状态、usage、公开输入与提取结果。
- [离线复核](../experiments/results/model_api_max_validation_20261026_v1/offline_review.json)：维护计划重建、引用统计、原文/运行源码哈希及密钥排除检查。
- [脚本原样快照](../experiments/results/model_api_max_validation_20261026_v1/driver_snapshot.py.txt)：审计用，不是普通工作流入口。重跑须复制回 `.pytest_cache/model_api_max_validation_20261026.py` 并使用专用环境，会再次产生最多 3 次真实调用，输出不保证相同。
- [归档清单](../experiments/results/model_api_max_validation_20261026_v1/manifest.json)：保留每个文件的字节哈希；`runtime_sources/` 保存实际运行时的源码快照，以区分随后增加的环境预算入口。

最终专用环境完整回归 **770 项通过，覆盖率 89.57%**，用时 300.20 秒；13 条第三方弃用警告，80% 门槛保持不变。源代码在最终回归期间冻结。初次审查与后续实测各发现一处需要补齐的边界，完成修复后重新验证，最终结果包括这些改动；未用两个小样本替代回归测试。
