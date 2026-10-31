# 当前代码的归档结果

均由提交 `1563f43`（manifest 中 `git_dirty: false`）在项目环境运行。

| 结果 | 结论 |
|---|---|
| `p1_static_fjsp/` | 31 个实例 × 8 种方法共 248 份调度全部通过检查器；CP-SAT（10 s）15 个 OPTIMAL、16 个 FEASIBLE，18 个达到 FJSPLib 上界 |
| `p2_dynamic_protocol/` | 243/243 次重调度通过静态与动态检查器，重复运行排程一致；81 组 makespan 与归档 exp_019 完全相同 |
| `g1_cpsat_fixed_vs_joint/` | 480/480 次 CP-SAT（1 s）接受；每个实例的总延期与归档 exp_035 完全相同（两次都为 410 个 OPTIMAL） |

尚未用新代码重跑：`g1 --long`、`g2`–`g6`（对应归档 exp_036–038、exp_040 与注意力策略试跑）。

## 周期性维护与 G4

| 结果 | 内容 |
|---|---|
| `periodic_k1_regression/` | 多窗口扩展后，单窗口结果与原代码 16 项全部一致 |
| `g4_teacher_data/` | 2 万个训练实例的 IGA-5000 教师轨迹（`train.jsonl` 可重新生成、不入库，哈希见 manifest）+ 验证集 |
| `g4_attention_policy/` | 注意力策略（解码器 MDP），验证集选出的检查点 |
| `g4_search_curves/` | 第一次搜索曲线运行（与训练同时进行，IGA/SA 计时偏慢，只采用其中的规则、GA、CP-SAT） |
| `g4_search_curves_retimed/` | 机器空闲时重跑的 IGA、SA |
| `g4_policy_curves/` | RL 单实例计时 |
| `g4_summary/` | 汇总、曲线图和 [findings.md](g4_summary/findings.md) |
