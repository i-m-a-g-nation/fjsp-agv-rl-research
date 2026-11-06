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
| `g4_gantt/` | 甘特图示例（PNG/PDF）：n20-m2 固定 86 → 联合 66；n20-m4 固定 129 → 联合 67；n50-m4 两者都是 26 |

## G5 补充实验（提交 7999b06）

| 结果 | 内容 |
|---|---|
| `g5_attention_policy_seed1/`、`_seed2/` | 训练种子 1、2（含模仿阶段检查点 `best_bc.pt`） |
| `g5_bc_seed0/` | 种子 0 只跑模仿阶段 |
| `g5_policy_curves_seed{0,1,2}[_large]/` | RL 单实例计时（G5-T / G5-L），含热启动用的序列 |
| `g5_bc_curves_seed{0,1,2}[_large]/` | 只模仿模型的单实例计时 |
| `g5_search_curves/`、`_large/` | 规则、IGA、SA；CP-SAT 只 n = 20 |
| `g5_seeded_iga_seed{0,1,2}[_large]/` | RL 热启动 IGA |
| `g5_summary/` | 汇总、H1–H5、曲线图和 [findings.md](g5_summary/findings.md) |
| `g5_iga_retime_check/` | 空闲机器上抽样复测 IGA 计时（提交 1b405f1）和 [findings.md](g5_iga_retime_check/findings.md) |
| `g5_iga_speed_sensitivity/` | 假设 IGA 快 1.3/1.6/2 倍时重做 H1、H3–H5（提交 bf88014，探索性） |

## 大创（生产—物流协同）

各目录的提交见其 `findings.md` 与 `manifest.json`（均为 `git_dirty: false`）。第三方算例与布局只在本地 `instances/external/`，哈希记录在 manifest。

| 结果 | 提交 | 内容 |
|---|---|---|
| `l1_benchmark/` | `c981fcb` | Deroussi & Norre 10 个算例：参考解重放、CP-SAT 与规则，基准约定与"阻塞 + 缓冲 ∞/2/1/0"；[findings](l1_benchmark/findings.md) |
| `l1_decoupled/` | `e3cafa2` | 解耦基线（先排机器再排车）与联合 CP-SAT 的差距；[findings](l1_decoupled/findings.md) |
| `l1_large/` | `0e37383` | Brandimarte 6 个大算例：规则普通/死锁规避、缓冲效应、下界；[findings](l1_large/findings.md) |
| `l1_search/` | `8673ba7` | SA（参考）与 GA：小算例对照 CP-SAT，大算例对照规则与下界；[findings](l1_search/findings.md) |
| `l2_formal_train/` | `3cfc48a` | L2 策略 3 个种子的正式训练：检查点（含哈希）、训练曲线、验证集结果 |
| `l2_formal_test/` | `a685ac8` | L2 正式测试（测试集只用一次）：H1–H4 与描述性结果；[findings](l2_formal_test/findings.md) |
