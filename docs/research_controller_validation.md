# 外层科研控制器：一条命令运行一个有界批次

本轮把两个已有方向接到程序入口：核对文献片段依据，再诊断冻结策略。任务派发、读取结果和停止决定由程序执行。当前注册表只有两种离线任务；自动找新论文、生成并应用候选代码、跨算法反复训练仍未实现。它是完整自动科研目标的一个中间里程碑。

## 人类先读这里

运行结果会新增一份批次记录、两份报告和下一项任务建议。**不会改动算法源码或训练权重**。本轮的下一项是设计共享评分候选，但报告中的 `executable: false` 表示程序尚不能自行实现它。重复启动已经结束的同一批次只核验状态，不会重新实验。

| 程序做的事 | 本次结果 |
|---|---|
| 核对 exp026 结果、源码及验证分母 | 旧均值候选两模式均未改善，跳过重复训练 |
| 核对归档论文状态片段 | 2 条引用位置仍匹配；语义未获人审，归档不是完整 PDF 来源包 |
| 调用编号置换诊断 | 16 个原始策略/算例组合，4 种编号排列，共 64 例 |
| 在相同物理状态比较策略分布 | 384 次比较中 285 次超过 `1e-10`，最大单动作概率差约 0.293 |
| 检查完整计划 | 64 份重新贪心计划、64 份映射回放计划均通过原 G1；奖励和总延期重新核对 |
| 根据新结果决定下一步 | 生成 `design_shared_scorer_candidate` 建议，停于 `implementation_required` |

编号诊断说明当前模型会使用编号相关信息，值得检验共享评分结构；**没有证明这是性能差的唯一原因，也没有证明换结构会改善结果**。身份排列和均匀合法分布对照均无差异。本轮没有训练、模型 API、网络请求、探测集或最终测试评价。

实际批次执行计费时间为 9.187 秒，预算 120 秒、最多两个任务、模型调用与 tokens 均为 0。专用进程负责任务，父进程限制剩余时间并拥有进程树。终止后的状态查询/完整性核验不再启动新的执行计费片段；本地 I/O 检查按检查点中断，任务进程有硬超时。

## 怎样启动、查看、继续

在项目根目录使用专用 Conda 环境：

```powershell
$controllerPython = if ($env:FJSP_CONDA_ENV) { Join-Path $env:FJSP_CONDA_ENV 'python.exe' } else { '.\.conda-env\python.exe' }
& $controllerPython -c "import sys; print(sys.executable)"
& $controllerPython experiments/exp_027_research_controller.py run --output-dir experiments/runs/my-research-batch
& $controllerPython experiments/exp_027_research_controller.py status --output-dir experiments/runs/my-research-batch
```

同样的 `run` 命令恢复同一批次。`--steps 1` 只限制本次调用执行一个任务，下一次继续第二个；累计预算不会因此增加。已经完成或失败的任务不自动重试。预算文件丢失、损坏、来源/输入/配置变化时拒绝恢复，需要新批次并保留旧记录。

默认只执行毕设已注册任务。`--track innovation` 会显示大创需要生产—物流能力，并停在没有已注册执行器的边界；不会把毕设生产—维护结果算作大创成果。

## 文件与状态

| 位置 | 用途 |
|---|---|
| `experiments/exp_027_research_controller.py` | 统一启动/状态入口 |
| `src/ai_workflow/research_controller.py` | 身份绑定、排他锁、持久预算、派发和恢复 |
| `src/ai_workflow/research_tasks.py` | 明确注册的工具、确定性决策、结果复核 |
| `src/ai_workflow/research_worker.py` | 凭据不继承的隔离进程入口 |
| `src/graduation/permutation_diagnostics.py` | 冻结验证集、相同物理状态置换诊断 |
| 批次 `spec.json` / `state.json` | 源码/输入/契约身份；任务、决定、停止原因 |
| 批次 `task_01.json` / `task_02.json` | 文献依据核对和完整诊断结果 |
| 批次 `budget.sqlite` | 实际执行与未结算预占；崩溃不会自动退还 |

`READY` 表示可以执行，`RUNNING` 表示任务已经登记，`YIELDED` 表示本次调用主动分段，`STOPPED` 必须结合 `stop_reason` 阅读。`COMPLETED` 只用于通过检查的工具任务。大创、毕设的 `research_status` 均保持 `not_achieved`；原三审入口与批准记录保持独立。

## 这轮解决了什么，还差什么

以前需要聊天代理分别启动文献工具和实验诊断；现在这个有限批次可以一次启动、自行派发并据结果停止。决策是源码中的显式规则，当前仅针对已有 exp023/exp026 归档，不是自由规划的 AI 研究员，也未接入新的在线文献提取。

下一项工程工作是增加受限候选实现适配器：在隔离目录产出可审查补丁，固定目标、环境和检查器，先验收再执行同预算训练/验证，失败保留并回退。只有这一环接入后，程序才能从“发现结构问题”进一步自行推进到“实现候选并比较”；仍不能保证科研收益。大创还需单独处理原计划书的生产—物流范围。

## 验证记录

38 项专项测试通过，包括预算恢复、源/结果变化拒绝、排他锁、超时、部分初始化、拒绝空报告/截断报告，以及完整计划和相同物理状态映射。独立复核找出的预算重置、核验漏计时与报告分母漏洞均先有失败回归，再完成修正。

全量回归 **1276 通过、2 跳过、覆盖率 90.62%**，650.36 秒，80% 门槛保持；13 条第三方弃用警告，跳过项为 Windows 符号链接权限。独立计算 64 例/384 次概率比较并重放 128 份计划，4782 项核对零差异；终止后恢复的任务、预算和摘要完全相同。

[批次摘要](../experiments/results/exp_027_research_controller_v1/summary.json)、[完整编号诊断](../experiments/results/exp_027_research_controller_v1/task_02.json)、[独立复核](../experiments/results/exp_027_research_controller_v1/independent_check.json)、[验证记录](../experiments/results/exp_027_research_controller_v1/validation_record.json)、[归档哈希](../experiments/results/exp_027_research_controller_v1/archive_manifest.json)。归档供只读审阅；恢复使用原本地批次目录。源码字节（含换行）或检出路径变化时拒绝沿用原批次，当前未承诺跨系统原地恢复。

原 G1/G2、R1/R2、训练器、奖励、契约、依赖和历史证据保持；本轮只新增控制器、注册工具、诊断及相应测试/记录。
