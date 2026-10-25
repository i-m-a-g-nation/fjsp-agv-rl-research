# 毕设 G2：固定/联合维护参考模型

用户在明确的 G2 提案后回复“开始”，本轮沿用已确认首版：同质平行机、每任务一道不可抢占工序、全部任务release0、每机一次必需维护（含空闲机）、完整维护区间在窗口内、无共享维修班组。G2 是本次获准的专用模型增量，不改写 AGENTS 或既有工作流人审范围。

## 已实现的求解与核对

`src.graduation.solve_parallel_maintenance(data, mode=..., time_limit=10.0, num_workers=1, seed=42)`：任务—机器 optional interval、ExactlyOne，机器上生产与一个必需维护区间统一 NoOverlap；固定模式预先约束维护开始，联合模式允许在相同窗口内选择。两模式都优化生产分配与顺序，唯一目标是总延期。

每个任务的延期由精确 max 约束表达；抽取后从完成时刻独立重算，再核对求解器原始目标，并通过 G1 生产/维护检查。不能通过删除维护、改交期或改变目标改善结果。makespan仍仅为生产最大完成时刻，gap根据总延期计算。

仅OPTIMAL、FEASIBLE可返回计划，原状态保留；UNKNOWN、INFEASIBLE、MODEL_INVALID、提取错误或检查器拒绝均不返回有效计划。`solver_objective_value` 保存原始目标，另保存下界、gap、求解耗时。时间预算须有限正数，线程数1..64、整数种子0..2^31-1；默认单线程/seed42/10秒。为避免整数域溢出及浮点诊断丢失整数精度，CP-SAT对H的保守聚合界及交期限制为2^50，超限拒绝；此为工程限制。

`src.graduation.enumerate_parallel_maintenance(data, mode=..., max_states=200000)`：独立枚举维护开始、机器分配、生产排列及每机维护插入位置，直接累计正延期，不调用 CP-SAT 或复用其模型。上限5任务、3机器、200000状态，先检查维护窗口组合数再建立笛卡尔积，超限不返回部分搜索中的“最优”。枚举也检查数值域并在结束后验证最终计划。

枚举的完备性：任意可行计划都对应某个机器分配、各机任务顺序、维护位置及整数开始时刻。固定这些选择后，将维护前任务从0开始左移、维护后任务从维护结束连续排，不会破坏可行性或增加任一任务延期。因此只需枚举这些最早生产安排，就能保留最优目标值。该论证依赖release0、无跨机路线和其他共享资源；不能直接推广至后续大创模型。

## 验证内容

- 手算证人：单机固定/联合4/0，双机6/0。
- 边界：紧窗口强制先维护时，闲置机仍维护；维护在生产结束后执行时，生产makespan不计维护结束。
- 12个固定种子测试实例覆盖不同p、d、q、窗口、固定开始与机器数，CP-SAT和枚举逐个一致；均证最优时联合目标不大于固定目标。
- 无解状态禁止提取，FEASIBLE不升级，错误目标/领域checker拒绝不放行，枚举预算耗尽和宽窗口预分配均明确失败。
- 实验021使用4组手算/边界例及另外8个预定种子实例，两模式共24次核对。原始数据和结果是模型正确性证据，不用于性能排名或规模外推。

## 如何重跑与阅读结果

使用`.conda-env`或`FJSP_CONDA_ENV`专用环境，先核对解释器：

```powershell
$g2Python = if ($env:FJSP_CONDA_ENV) { Join-Path $env:FJSP_CONDA_ENV 'python.exe' } else { '.\.conda-env\python.exe' }
& $g2Python -c "import sys; print(sys.executable)"
& $g2Python experiments/exp_021_graduation_solver_check.py
```

默认输出到新的`experiments/runs/graduation_g2/<时间>/`；可用`--output-dir`指定新目录，禁止覆盖旧证据。`inputs/`保留任务/维护快照，`schedules/`保存生产、维护、枚举计划及失败诊断，`raw.csv`记录状态和实际指标，`report.md`便于阅读，`manifest.json`绑定源代码/提交、OR-Tools版本、输入、输出哈希与核对摘要。manifest不自引用哈希。

`schedule_accepted`仅表示领域合法；`validation_status=PASS`还要求双方OPTIMAL、总延期相等并满足手算期望。合法FEASIBLE保留合法指标但核对不通过；非法计划没有接受指标，原始错误计划仅作诊断。确定性摘要绑定输入、配置、状态及目标核对；允许同值最优计划顺序和计时不同。

## 当前边界和人审

G2不是G3正式研究比较，也尚未接入LangGraph验收后端。完整毕设任务书及最终算法要求仍待核对；大创的运输、AGV、缓冲区、RL和学术成果要求保持未达成。

人需要读懂：任务/维护假设是否符合题目，总延期与makespan的区别，两模式是否仅改变维护开始约束，求解状态与下界能支持什么结论，以及手算/枚举一致不等于研究创新或真实车间适用性。

完整回归、审查及最终存档记录完成后见`review_status.md`和本轮执行记录。
