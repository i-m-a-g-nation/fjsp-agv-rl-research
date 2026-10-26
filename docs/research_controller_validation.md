# 科研控制器：审计与受限模板候选批次

同一`exp_027`入口提供两种显式模式。`audit_v1`核对文献与诊断冻结策略；`shared_scorer_v1`再生成已登记模板候选包、检查、训练和验证选择。自动找新论文、自由生成新算法或跨设计搜索仍未实现。本文数值是对应版本的快照；当前状态统一看[START_HERE](../START_HERE.md)。

| 模式 | 已注册任务数 | 批次内可执行的改动 |
|---|---|---|
| `audit_v1`（默认兼容入口） | 2 | 新增依据核对和诊断报告 |
| `shared_scorer_v1` | 5 | 报告、模板源码/补丁、检查、训练日志和权重、保留或拒绝决定 |

## 人类先读这里

审计模式输出报告；候选模式还输出可审查源码、add-only补丁、训练权重和验证选择。项目基线、领域模型、检查器和默认策略均不被覆盖。重复启动已结束的同一批次会核验身份与产物，不会重新训练。`executable: false`表示后续任务尚没有注册执行器。

## 第一份审计批次快照（原 exp027_v1）

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

运行受限候选批次，显式选择新模式并使用新目录：

```powershell
& $controllerPython experiments/exp_027_research_controller.py run --profile shared_scorer_v1 --output-dir experiments/runs/my-shared-scorer-batch
& $controllerPython experiments/exp_027_research_controller.py status --output-dir experiments/runs/my-shared-scorer-batch
```

同样的`run`命令（含相同profile）恢复同一批次。`--steps 1`只限制本次调用执行一个任务，下一次继续，累计预算不会增加。两模式默认共享120执行秒，任务上限分别2/5，模型调用和tokens均为0。已完成或失败的任务不自动重试。预算损坏、来源/输入/配置变化时拒绝恢复，需要保留旧记录并使用新批次；新增控制器代码也会使旧本地批次拒绝继续，旧只读归档保持。

默认只执行毕设已注册任务。`--track innovation` 会显示大创需要生产—物流能力，并停在没有已注册执行器的边界；不会把毕设生产—维护结果算作大创成果。

## 文件与状态

| 位置 | 用途 |
|---|---|
| `experiments/exp_027_research_controller.py` | 统一启动/状态入口 |
| `src/ai_workflow/research_controller.py` | 身份绑定、排他锁、持久预算、派发和恢复 |
| `src/ai_workflow/research_tasks.py` | 明确注册的工具、确定性决策、结果复核 |
| `src/ai_workflow/research_worker.py` | 凭据不继承的隔离进程入口 |
| `src/graduation/permutation_diagnostics.py` | 冻结验证集、相同物理状态置换诊断 |
| `src/graduation/candidate_templates/shared_scorer.py` | 共享32输入/16隐藏/1评分网络模板，545参数 |
| `src/graduation/candidate_training.py` | 使用原始已检查回合和奖励训练模板策略 |
| `src/ai_workflow/controlled_candidate.py` / `candidate_evidence.py` | 模板包、检查收据和完整产物验收 |
| `src/ai_workflow/candidate_comparison.py` | 有界训练、验证选模、归档基线复核及严格选择 |
| 批次 `spec.json` / `state.json` | 源码/输入/契约身份；任务、决定、停止原因 |
| 批次 `task_01.json` / `task_02.json` | 文献依据核对和完整诊断结果 |
| 批次 `budget.sqlite` | 实际执行与未结算预占；崩溃不会自动退还 |

`READY` 表示可以执行，`RUNNING` 表示任务已经登记，`YIELDED` 表示本次调用主动分段，`STOPPED` 必须结合 `stop_reason` 阅读。`COMPLETED` 只用于通过检查的工具任务。大创、毕设的 `research_status` 均保持 `not_achieved`；原三审入口与批准记录保持独立。

## 受限候选模式的边界

程序只能生成源码版本中登记的模板，不能执行论文或模型输出中的任意代码。模板复制到批次`candidate/policy.py`，同时生成`candidate.patch`和来源manifest；复制后的代码须保持登记模板的字节身份。每项任务在受管理子进程中执行。

门禁实际计算全部545参数的有限差分和192次同物理状态分布比较；收据、检查内容、输入和文件哈希一致才允许训练。固定训练8例、验证4例，fixed/joint×seed17/29各64回合，共256回合/1536步；初始及每16回合验证，选择最早的最小均值检查点。

比较使用归档的同64回合预算none策略、规则和CP参考并重新回放/核对，不把它们说成新训练或新求解。每模式包含全部8个策略验证结果，候选均值严格更低才保留为批次产物，否则选择none。完整日志、检查点、32份策略验证计划、48规则/8CP参考和384次训练后对称性比较缺一，则不能作保留决定。生产默认策略与原三审批准保持独立。

当前贯通预先登记模板的生成、检查、训练与拒绝/保留；新假设和新模板仍需开发者实现、测试和登记。自动论文发现、自由代码生成尚无执行器，大创生产—物流范围仍需独立推进。

## 原审计模式验证快照

38 项专项测试通过，包括预算恢复、源/结果变化拒绝、排他锁、超时、部分初始化、拒绝空报告/截断报告，以及完整计划和相同物理状态映射。独立复核找出的预算重置、核验漏计时与报告分母漏洞均先有失败回归，再完成修正。

全量回归 **1276 通过、2 跳过、覆盖率 90.62%**，650.36 秒，80% 门槛保持；13 条第三方弃用警告，跳过项为 Windows 符号链接权限。独立计算 64 例/384 次概率比较并重放 128 份计划，4782 项核对零差异；终止后恢复的任务、预算和摘要完全相同。

[批次摘要](../experiments/results/exp_027_research_controller_v1/summary.json)、[完整编号诊断](../experiments/results/exp_027_research_controller_v1/task_02.json)、[独立复核](../experiments/results/exp_027_research_controller_v1/independent_check.json)、[验证记录](../experiments/results/exp_027_research_controller_v1/validation_record.json)、[归档哈希](../experiments/results/exp_027_research_controller_v1/archive_manifest.json)。归档供只读审阅；恢复使用原本地批次目录。源码字节（含换行）或检出路径变化时拒绝沿用原批次，当前未承诺跨系统原地恢复。

原 G1/G2、R1/R2、训练器、奖励、契约、依赖和历史证据保持；本轮只新增控制器、注册工具、诊断及相应测试/记录。

## 首次受限模板批次快照（2026-10-27完成验收）

程序连续完成五个已注册任务，36.5执行秒，0API/网络调用；原批次目录终止后恢复结果完全相同，未重复训练。新增256回合/1536步、52个检查点，全部策略计划通过原G1。545参数梯度门禁通过；训练后384状态比较的最大概率差约`5.55e-17`，仍不代表性能一定提高。

| 模式 | 候选验证均值 | 已归档none验证均值 | 程序决定 |
|---|---:|---:|---|
| fixed | 31.0 | 10.25 | 拒绝候选，保留none |
| joint | 17.75 | 7.5 | 拒绝候选，保留none |

四个分支所选回合依次为fixed/17=0、fixed/29=0、joint/17=0、joint/29=64；选择初始权重时明确记为未训练的检查点。结果只否定这一模板和当前小预算配置，不能否定共享评分的一般价值。程序停在`candidate_round_complete`，下一项为未注册的拒绝原因诊断，未更改默认策略或科研批准。

独立审查找出的“只写两个计数即可跳过检查”和“摘要无真实训练也可验收”两处漏洞均先复现失败，再用任务收据、来源/输入绑定及完整产物/分母核验修复。新增101项测试，全量 **1377通过、2跳过、13条第三方警告，覆盖率90.88%**，818.97秒。独立重放全部256次更新/1536步、52检查点、80区间验证计划、32所选策略计划、56规则/CP计划和384分布比较，2274项核对零差异。

[候选批次摘要](../experiments/results/exp_027_controlled_candidate_v1/summary.json)、[程序决定及完整记录](../experiments/results/exp_027_controlled_candidate_v1/task_05.json)、[独立重放](../experiments/results/exp_027_controlled_candidate_v1/independent_check.json)、[验证记录](../experiments/results/exp_027_controlled_candidate_v1/validation_record.json)、[归档哈希](../experiments/results/exp_027_controlled_candidate_v1/archive_manifest.json)。原审计快照及所有旧证据保留。
