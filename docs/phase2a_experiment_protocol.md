# Phase 2A 固定实验协议与复跑

本轮把现有动态底座接到固定基线实验。协议是本轮开发选定的 v1，尚不代表人已批准正式研究方案。当前只验证 FJSP 独立扰动后的重调度，不认证大创或毕设完成。

## 固定配置

机器可选集合及加工时间来自仓库原有 FJSPLib 文件，来源、许可证与参考值仍以 `instances/README.md` 和 `instances/fjsplib_bks.csv` 为准。动态问题改变了约束或任务，不能引用原静态 BKS/CP-SAT 值作为动态最优性依据。

| 项目 | v1 规定 |
|---|---|
| 协议文件 | `experiments/protocols/phase2a_v1.json` |
| 算例 | fattahi1、kacem1、mk01 |
| 初始调度 | 现有 `reschedule_from_state` 的 FIFO，时间从 0 开始 |
| 基线 | 现有动态 FIFO、SPT、EFT；不生成新算法 |
| 扰动 | 机器不可用至固定维修结束时刻、新工件到达、未来工序加工时间增加 |
| 种子 | 42、43、44，用于事件参数选择 |
| 重复 | 每条规则每个配置重复 3 次，用于耗时与确定性检查 |
| 计划规模 | 27 个算例/事件/种子配置、81 个规则组、243 次运行 |
| 停止规则 | 执行完有界配置网格；保留失败，不自动改参数或重试 |

每个扰动都从原初始调度单独开始，不能将本实验理解为连续在线仿真。每条规则使用同一状态、事件和冻结记录。比较结果以 FIFO 初始计划和当前三类生成扰动为条件，不代表规则在其他初始计划或实际车间中的普遍优劣。

名义事件时刻为 `max(1, C_initial // 3)`。机器故障从未来仍有工序的机器中按种子选取；若该机器正在加工，则等其本次加工结束才触发。不可用时长在 `[max(1,C//10), max(1,C//3)]` 内选取。它不模拟加工中断、故障损失或维护决策。

新工件复制按种子选取的现有工件完整路线，释放时刻为事件时刻。加工时间变更只选择尚未开始的工序，并将其原计划机器的加工时间增加到 `max(old+1, ceil(3*old/2))`。已完成和正在加工的工序按照既有 helper 冻结。

## 一条命令运行

先使用专用 Conda 环境，并运行 `python -c "import sys; print(sys.executable)"` 确认解释器；不得使用 base。

```powershell
python experiments/exp_019_phase2a_protocol.py
```

默认创建独立的 `experiments/runs/phase2a_protocol/<UTC时间>/` 目录，不覆盖旧结果；这个目录被 Git 忽略。也可以指定一个尚不存在的目录：

```powershell
python experiments/exp_019_phase2a_protocol.py --output-dir experiments/runs/my-phase2a-replay
```

`--no-plots` 只省略图片，不改变实验与调度散列。退出码 0 表示所有计划运行合法、重复调度一致且请求的图片保存成功；退出码 1 表示配置/读取错误、调度或场景失败、重复结果不一致或图片输出失败。单个运行失败继续保留其余有界网格结果，不提升失败行的有效性。

## 产物与指标

| 产物 | 含义 |
|---|---|
| `protocol.json`、`inputs/` | 本次实际读取的协议字节及算例字节快照 |
| `cases/` | 事件参数、初始调度、冻结记录、改变后的实例与动态状态；失败则记录诊断 |
| `schedules/` | 每次返回的调度、有效性、诊断和调度散列；无效结果不提供 accepted makespan |
| `raw.csv` | 完整计划网格，包含失败行 |
| `aggregate.csv` | 每个配置/规则的重复运行计数、makespan 和耗时中位数/范围 |
| `manifest.json` | 协议/算例/代码/产物散列、运行环境、结果计数和确定性摘要 |
| `report.md` | 基线结果和适用范围 |
| `gantt/` | 预先指定的首个种子、首轮 EFT 代表图；不是挑最优图 |

每次有效返回都额外经过静态和动态 checker，原算法内部的 checker 也保持不变。合法性包括冻结记录不变、释放时间和机器不可用约束。makespan 为全部完工时刻的最大值，单位跟随算例抽象时间单位。重调度耗时包含原算法内部检查，不含输入准备、额外外层核查、写盘和绘图；异常行只作诊断，不参与成功耗时统计。

损坏记录、不可序列化值和非有限数只保存为有界的 `diagnostic_only` 诊断，不保留有效 makespan 或调度散列，剩余网格继续运行。会话 `COMPLETED` 表示审核生命周期结束；若批量失败，实验状态仍为 `FAILED`、`eval_passed=false`，命令退出 1。

重复时序不同不影响调度摘要；确定性摘要绑定协议、算例、实际生成场景、每条有效调度及运行状态。不同种子也可能生成同一事件，manifest 另报不同场景快照数量。既不把 243 次运行当作 243 个独立质量样本，也不作显著性、动态最优性或泛化结论。

## 接到持久审核工作流

```powershell
python experiments/exp_018_ai_rag_workflow.py --track foundation --experiment-protocol experiments/protocols/phase2a_v1.json
```

这条路线按“范围审核 → 协议与输入证据审核 → 固定批量实验 → 结论审核”运行。它不建立 RAG、不读取模型密钥、不联网、不生成代码；不接受与 live、论文输入或 RAG 导出混用。范围审核显示协议、算例指纹和计划运行数。恢复时核对协议和算例；结论审核还核对 manifest 与全部已登记产物。

首次返回 3 并输出会话目录。真人阅读 `review-request.json`，填写该轮模板，再用 `--session-dir` 和 `--decision-file` 恢复；三轮各有独立哈希。测试里的 synthetic reviewer 只属于测试夹具。开发时直接运行 Experiment 019 也不等于批准科研结论。

范围内动态批量成功标记为 `PHASE2A_BASELINE`。foundation 的流程结束不代表完整科研验收；innovation、graduation 仍显示 `not_achieved`，完整审核后退出 2。详见 `docs/research_workflow.md`。

## 本轮实际记录

保存于 `experiments/results/exp_019_phase2a_protocol_v1/`：243/243 次调度合法，81 个规则组重复调度一致；27 个声明配置实际有 **23 个不同场景快照**。另一个新目录独立复跑，场景散列及确定性摘要相同：

`283d85b4218e24f9f2eb701e494ae53c61651a02ebdf0f4a1b8f3c74051a3893`

例如种子 42 的 mk01 新工件场景，FIFO/SPT/EFT 的 makespan 为 48/72/72。这是本场景下的规则差异，不支持“新算法优于基线”的结论。本轮没有新增调度算法。

代表甘特图已查看；小算例清晰，mk01 的短工序文字仍存在拥挤，逐条数值以 JSON/CSV 为准，图片尚不是论文定稿版式。
