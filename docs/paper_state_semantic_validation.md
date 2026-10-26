# 状态事实提取与模型语义复核

后续[纯编码器及R2轨迹回放](graduation_state_encoding_validation.md)已实现，零模型调用。本页保留状态事实提取时的范围和未实施候选记录。

**程序完成了两组“提取→引用定位→单独模型复核”。** 四次真实调用均正常结束；两条状态陈述都有原文位置，模型复核判为supported。它们仍是`unverified`、`human_approval=false`，不代表原方法复现、毕设验收或大创完成。

| 事实 | 项目中如何处理 |
|---|---|
| 论文任务特征为加工时间、交期、任务族 | R1已有加工时间/交期/是否安排；当前课题无任务族和换型，不新增 |
| 论文把全部机器信息矩阵拼接到已有矩阵 | R1已有所有机器及维护字段；只提出改变编码方式，不宣称新增全局信息 |

这只是两条状态事实；机器全部特征、状态维度、网络、训练细节和完整MDP均未由本轮提取完整覆盖。此前奖励/动作记录保留在[上一轮结果](paper_field_validation.md)。

## 这次工作流真正增加了什么

`exp_023`新增显式`semantic_review:true`。每个字段先提取并做原文位置检查，通过后立即保存，再用同一模型另发一次请求检查整条陈述的含义。项目合同、作者代码和适配方案不进入复核提示。

| 情况 | 程序行为 |
|---|---|
| 引用缺失、无效或没有有效陈述 | 不调用语义复核，停止后续单元，保留提取材料 |
| supported且复核引句有效 | 保存`model_supported_unreviewed`；执行可结束，但证据不升为verified |
| partial/unsupported/insufficient_evidence | `SEMANTIC_REVIEW_FLAGGED`，停止后续单元 |
| 复核超时、解析失败、预算耗尽或来源改变 | 保留已成功提取及已获得响应，按失败/超预算结束 |

模型不能通过输出字段批准研究；额外字段、重复字段、捏造引用、页面标记引用及越过片段的引用均拒绝。原引用也重新审计。每次复核绑定陈述和源文本哈希，使用同一个累计预算。网络不自动重试，无自动加预算或降级。

这是**同一Flash模型的两次不同任务调用**，存在相关错误风险，不是独立模型证明。定向测试以离线响应验证控制流，不测模型准确率；本轮真实样本只有两个正例，尚无在线负例或准确率评测。

## 实际来源、配置与预算

- 来源仍为Li等人的`10.1007/s10845-024-02470-8`，作者仓库提交`b4b46b92aa67556391b7e2613ac1213dafe16c60`，未执行作者代码或权重。
- 物理第12页（印刷页4746），整页文本SHA256`5ade0e88ac3817b730ef96a643eb7a1833f89a66dc3f0dbb758e64e06e91b3e5`；原始字符区间`[1817,1875)`与`[3310,3431)`，分别58和121字符，另附来源标记。
- 新批次`state-semantic-20261026-v1`，限4次/32768输出预占/300主动秒；每次Flash enabled/max、8192上限/60秒、网络重试0/引用纠正0。旧批次结果和额度均未覆盖。
- 实际4次、14.188主动秒，生成988token，其中779为思考；预占32768不是实际生成量。某次提取返回0思考token，保留原始usage；请求仍显式enabled/max，不按思考token数推断配置。
- 原生离线预览0模型调用。源码、合同、环境、领域checker和依赖均保持。

## 如何运行与人读哪里

使用[固定请求](../experiments/requests/paper_state_semantic_v1.json)，同样先核对专用Conda解释器：

```powershell
$paperPython = if ($env:FJSP_CONDA_ENV) { Join-Path $env:FJSP_CONDA_ENV 'python.exe' } else { '.\.conda-env\python.exe' }
& $paperPython -c "import sys; print(sys.executable)"
& $paperPython experiments/exp_023_paper_code_validation.py --request experiments/requests/paper_state_semantic_v1.json --repository-cache experiments/results/exp_023_real_paper_code_v1/repository_cache --pdf-cache papers/auto_fetched/transformer4pmsp_2026-10-26/paper.pdf
```

默认只获取/验来源并保存预览，不加载密钥或调用模型。显式增加`--extract`才运行两组提取/复核，并使用新建输出目录。请求预检要求最低调用/token预算足够容纳整个计划，不能隐式塞入纠正次数。

人先读上表两条事实、[两个原文短片段](../experiments/results/exp_023_state_semantic_v1/contexts/)，再看[28×13编码候选](graduation_state_encoding_candidate.md)。重点核对来源陈述与适配决定是否混淆、维护和总延期目标是否完整保留。该候选只是方案，尚无编码器、网络、训练或算法效果。

## 证据与当前距离

完整专用环境回归：**1005通过、2跳过、覆盖率89.84%**，255.36秒，13条第三方弃用警告；80%门槛保持。两项跳过均为Windows符号链接权限。独立增量审查未发现可执行问题，运行时文件在预览、真实调用和完整回归期间保持哈希一致。

[预算和逐项复核](../experiments/results/exp_023_state_semantic_v1/batch_summary.json)、[完整公开响应/定位](../experiments/results/exp_023_state_semantic_v1/live_result.json)、[源码对照](../experiments/results/exp_023_state_semantic_v1/state_code_alignment.json)、[候选方案JSON](../experiments/results/exp_023_state_semantic_v1/candidate_proposal.json)、[归档哈希](../experiments/results/exp_023_state_semantic_v1/manifest.json)、[归属与许可](../experiments/results/exp_023_state_semantic_v1/ATTRIBUTION.json)。归档是部分材料，完整PDF在本机，固定代码缓存复用首轮归档；这不是完整source_bundle。

程序已能在指定来源和字段上执行提取/定位/模型复核/保存或停止；论文主动发现、片段自动选择、受控改码、训练比较、结果驱动下一轮尚未贯通。该工具链也未自动接入018所有LangGraph节点。大创物流协同未实现；毕设仍缺训练与正式比较。

下一步先实现独立纯编码器，证明观察可无损往返、原R2轨迹和结果保持，再考虑网络训练。不能把接口检查当成算法提升。
