# 当前代码的归档结果

均由提交 `1563f43`（manifest 中 `git_dirty: false`）在项目环境运行。

| 结果 | 结论 |
|---|---|
| `p1_static_fjsp/` | 31 个实例 × 8 种方法共 248 份调度全部通过检查器；CP-SAT（10 s）15 个 OPTIMAL、16 个 FEASIBLE，18 个达到 FJSPLib 上界 |
| `p2_dynamic_protocol/` | 243/243 次重调度通过静态与动态检查器，重复运行排程一致；81 组 makespan 与归档 exp_019 完全相同 |
| `g1_cpsat_fixed_vs_joint/` | 480/480 次 CP-SAT（1 s）接受；每个实例的总延期与归档 exp_035 完全相同（两次都为 410 个 OPTIMAL） |

尚未用新代码重跑：`g1 --long`、`g2`–`g6`（对应归档 exp_036–038、exp_040 与注意力策略试跑）。
