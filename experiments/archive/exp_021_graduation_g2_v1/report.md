<!-- fjsp-generated-report track=graduation -->
# 毕设 G2 极小算例参考求解验证

状态：COMPLETED；核对通过 24/24。

| 算例 | 模式 | 调度合法 | 求解状态 | 总延期 | 枚举最优延期 | 核对 |
|---|---|---|---|---:|---:|---|
| one_machine | fixed | True | OPTIMAL | 4 | 4 | PASS |
| one_machine | joint | True | OPTIMAL | 0 | 0 | PASS |
| two_machines | fixed | True | OPTIMAL | 6 | 6 | PASS |
| two_machines | joint | True | OPTIMAL | 0 | 0 | PASS |
| idle_machine | fixed | True | OPTIMAL | 2 | 2 | PASS |
| idle_machine | joint | True | OPTIMAL | 2 | 2 | PASS |
| late_maintenance | fixed | True | OPTIMAL | 0 | 0 | PASS |
| late_maintenance | joint | True | OPTIMAL | 0 | 0 | PASS |
| tiny_seed_20261025 | fixed | True | OPTIMAL | 0 | 0 | PASS |
| tiny_seed_20261025 | joint | True | OPTIMAL | 0 | 0 | PASS |
| tiny_seed_20261026 | fixed | True | OPTIMAL | 1 | 1 | PASS |
| tiny_seed_20261026 | joint | True | OPTIMAL | 1 | 1 | PASS |
| tiny_seed_20261027 | fixed | True | OPTIMAL | 5 | 5 | PASS |
| tiny_seed_20261027 | joint | True | OPTIMAL | 5 | 5 | PASS |
| tiny_seed_20261028 | fixed | True | OPTIMAL | 0 | 0 | PASS |
| tiny_seed_20261028 | joint | True | OPTIMAL | 0 | 0 | PASS |
| tiny_seed_20261029 | fixed | True | OPTIMAL | 1 | 1 | PASS |
| tiny_seed_20261029 | joint | True | OPTIMAL | 1 | 1 | PASS |
| tiny_seed_20261030 | fixed | True | OPTIMAL | 8 | 8 | PASS |
| tiny_seed_20261030 | joint | True | OPTIMAL | 8 | 8 | PASS |
| tiny_seed_20261031 | fixed | True | OPTIMAL | 0 | 0 | PASS |
| tiny_seed_20261031 | joint | True | OPTIMAL | 0 | 0 | PASS |
| tiny_seed_20261032 | fixed | True | OPTIMAL | 0 | 0 | PASS |
| tiny_seed_20261032 | joint | True | OPTIMAL | 0 | 0 | PASS |

## 数据与判定

同一算例的两模式共享任务、交期、每机必需维护时长和完整窗口；固定模式另要求维护开始等于预设值。
每条生产/维护计划独立过 G1 检查；枚举也重新检查。核对通过要求 CP-SAT 为 OPTIMAL 且总延期等于枚举最优值。
合法 FEASIBLE 保留真实状态与合法指标，但不能作为已证最优的核对通过；非法调度的接受指标留空，诊断另存。
raw.csv 保存原始目标值、下界、按总延期计算的 gap 和求解耗时；schedules/ 保存完整生产、维护及校验诊断。
输入、配置和核对结果绑定确定性摘要；同值最优计划可不同，耗时和具体计划不要求跨运行或版本逐字节一致。
四组手算/边界例加八组预定种子的极小实例只验证建模正确性；不用于统计性能排名、RL效果或最终课题验收。
G3正式协议、工作流接入及大创生产—物流研究尚未完成。没有生成任何人工批准。

## 失败诊断

