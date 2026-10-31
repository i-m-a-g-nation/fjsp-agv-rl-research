# 重构等价性核对（2026-10-31）

目的：确认把旧代码（分支 `archive/pre-restructure-2026-10-31`，提交 `9e8fc13`）重构为 `src/fjsp_lab/` 之后，
算法行为没有任何变化，从而 `experiments/archive/` 中的结果仍然代表当前代码。

方法：[check_equivalence.py](check_equivalence.py) 在同一进程中同时导入旧代码（`src.*`）和新代码（`fjsp_lab.*`），
用相同输入逐项比较输出（不是只比较平均值）：

| 项目 | 比较内容 | 规模 |
|---|---|---|
| G3A 网格 | 240 个案例的编号、分组、固定策略和完整数据 | 240 |
| 学习用划分 | train / validation / test / teacher_train 的实例、模式和因子 | 共 2000 |
| 派工规则 | 9 规则组合的完整排程（每个作业的机器、开始、结束和维护时刻） | 1280 个问题 |
| 构造环境与特征 | 随机轨迹上每一步的合法动作与 19 维特征（逐元素相等） | 每 7 个问题取 1 |
| NumPy 打分策略 | exp_036 的 policy_s0：贪心 + 8 次采样的完整排程；短训练的历史与权重 | — |
| GA / SA / IGA | 1000 次解码下的最优序列、评估计数、最优出现位置和排程 | 每 5 个问题取 1 |
| 以给定序列为初始种群的 IGA | 旧 `solve_seeded_iga` 与新 `initial_sequences` | 每 11 个问题取 1 |
| 教师动作重放 | IGA 排程 → 环境动作序列 | 每 13 个问题取 1 |
| 精确方法 | 旧枚举 = 新枚举 = CP-SAT 最优值（n=3, m=2）；确定性时间下的 CP-SAT 排程与状态 | 32 + 20 |
| 静态 FJSP | 30 个 FJSPLib 文件的解析结果和 7 条规则的完整排程 | 210 |
| Phase 2A 协议 | 27 个扰动案例及 3 条规则的重调度排程 | 81 |

结果见 [output.txt](output.txt)：全部 16 项一致（`ALL EQUIVALENT`）。另外，注意力策略试跑的检查点
（`experiments/runs/exp_043_pilot_s0/best.pt`，未归档）用新代码在验证集上重新计算贪心平均总延期为 25.38，与试跑记录完全相同。

已知且有意的接口变化（不影响数值）：`ScheduleResult` 等数据类型的位置；构造环境去掉了未使用的观测张量和截断接口，
`step()` 返回精简的 `Step`；维护 CP-SAT 只保留 solver_v2 验收规则；`solve_seeded_iga` 并入
`solve_metaheuristic(initial_sequences=...)`；动态事件对非整数时间/编号报错（旧代码只检查符号）。
