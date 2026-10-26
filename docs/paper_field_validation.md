# 真实论文单字段提取

这轮程序成功提取了两条带原文位置的事实，状态是 `EVIDENCE_READY_UNREVIEWED`。这表示引用定位完整；语义仍未获人审批准，也不代表论文复现、强化学习训练或课题完成。

| 字段 | 程序得到的内容 | 来源与项目影响 |
|---|---|---|
| 奖励常数 | `Rshape=1; Ropt=200` | 论文物理第15页；作者固定代码的 `final_reward=100`，继续分开记录，现有维护模型奖励保持 |
| 动作表示 | 所有可用任务的优先级，维度为当时可用任务数 `nt` | 论文物理第13页；不能直接替换本项目的任务—机器/强制维护动作 |

本次只给模型89字符的奖励段落和241字符的动作段落，加上来源标记；不是整篇论文提取，状态空间尚未完成。字段和片段范围由当前开发者预先选定，程序还不能自主发现论文或决定所有应读段落。

## 运行了什么，是否影响算法

沿用 `exp_023`，新增明确的 `field` 和 `excerpts` 请求类型。片段绑定整页文本SHA256、物理页码及原始半开字符区间；程序重新核对PDF/Git来源后生成不可覆盖的上下文。模型只看论文片段，作者代码另存为比较材料；项目目标和代码没有混入论文事实提取提示。

每次模型只回答一个字段，返回一条陈述及原文引句，或明确缺失。缺失、额外字段、无效引用、空答案、截断输出和越过片段的引用不能通过；页面标记也不能被当成论文证据。原来的整页提取入口继续支持。

程序保存请求、响应最终正文、数字usage、引用位置、失败状态和预算；不保存思考正文。只读试验不生成候选代码，不运行作者代码或训练，不改调度模型、奖励、维护窗口或合法性检查。执行状态与研究验收仍分开。

## 真实接口与预算

本轮是独立的新批次 `field-evidence-20261026-v1`。前一轮整页提取失败及已耗尽预算保留，未重置或覆盖。

- 实际发送 `deepseek-flash`、`thinking=enabled`、`reasoning_effort=max`；每次8192输出上限、60秒、网络重试0、引用纠正0。
- 批次上限2次调用、预占16384输出token、150主动执行秒。
- 实际2次调用均以 `stop`结束；引用2/2定位完整。累计10.765主动执行秒、实际生成515token，其中436为思考token。预占16384是预算保留值，不是实际生成量。
- JSON模式经 `extra_body`传到官方接口，实际HTTP体经离线SDK测试验证。这样保留 `length`响应的诊断，避免SDK提前解析并抛错。

同一论文此前的整页8K/16K请求失败，此次短片段与小结构请求成功。这是两个小字段的工程验证，不能推广成整篇论文准确率、模型优劣或算法性能结论。

## 人如何使用

请求：[paper_code_fields_v1.json](../experiments/requests/paper_code_fields_v1.json)。先在专用Conda环境核对解释器，运行不带 `--extract` 的预览：

```powershell
$paperPython = if ($env:FJSP_CONDA_ENV) { Join-Path $env:FJSP_CONDA_ENV 'python.exe' } else { '.\.conda-env\python.exe' }
& $paperPython -c "import sys; print(sys.executable)"
& $paperPython experiments/exp_023_paper_code_validation.py --request experiments/requests/paper_code_fields_v1.json --repository-cache experiments/results/exp_023_real_paper_code_v1/repository_cache --pdf-cache papers/auto_fetched/transformer4pmsp_2026-10-26/paper.pdf
```

默认不加载密钥、不调用模型；保存 `PREVIEW_READY`片段及代码比较上下文，总状态 `SOURCES_VERIFIED_UNREVIEWED`。本机无PDF时省略 `--pdf-cache`，入口按已固定的官方URL获取并验哈希。只有显式增加 `--extract`才读取本机 `.env`并计费；每次运行新建输出目录，已有目录会拒绝覆盖。不要把反复新建批次当作失败后无限续费机制。

人先读上面两条事实和[原文短片段](../experiments/results/exp_023_paper_fields_v1/contexts/)。重点审核：引句是否支持完整陈述；论文与源码不一致时各自真实写了什么；迁移设计是否保持总延期目标和强制维护约束。提取到论文事实本身不会批准迁移。

## 可核查证据与剩余工作

[本轮预算和结果](../experiments/results/exp_023_paper_fields_v1/batch_summary.json)、[实际响应与定位](../experiments/results/exp_023_paper_fields_v1/live_result.json)、[论文—代码对照](../experiments/results/exp_023_paper_fields_v1/paper_code_comparison.json)、[归档哈希](../experiments/results/exp_023_paper_fields_v1/manifest.json)、[原作者及许可](../experiments/results/exp_023_paper_fields_v1/ATTRIBUTION.json)。这是部分证据归档，完整PDF仍在本机，作者固定代码缓存复用上一轮归档；不能把此目录当成完整source_bundle。

完整回归：**973通过、2跳过、覆盖率89.78%**，246.02秒；80%门槛保持，13条第三方弃用警告。两处跳过均为Windows符号链接权限。独立审查无阻断问题；一个小限制暂留：若供应商返回违反其schema的usage元数据，SDK可能在回调前抛错，结果仍失败，但可能缺少最终正文诊断。

下一步补状态字段及语义支持检查，再提出保持维护动作和延期奖励的表示层候选。论文发现、片段自动选择、受控算法修改、训练/对照、结果驱动下一轮及统一控制器接入仍未完成；大创、毕设均未达成。
