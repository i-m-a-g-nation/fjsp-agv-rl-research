# 重构后代码的归档结果

本目录的结果都由 2026-10-31 重构之后的代码产生，但**各自绑定不同的提交**，不一定是当前代码。
每个目录的提交记录在其 `manifest.json`（训练与汇总目录记录在 `summary.json`），全部为 `git_dirty: false`；
按哈希核验时要切到该提交。读结论前请先看文末的[读法与勘误](#读法与勘误)。

## 底座与单窗口回归（提交 `1563f43`）

| 结果 | 结论 |
|---|---|
| `p1_static_fjsp/` | 31 个实例 × 8 种方法共 248 份调度全部通过检查器；CP-SAT（10 s）15 个 OPTIMAL、16 个 FEASIBLE，18 个达到 FJSPLib 上界 |
| `p2_dynamic_protocol/` | 243/243 次重调度通过静态与动态检查器，重复运行排程一致；81 组 makespan 与归档 exp_019 完全相同 |
| `g1_cpsat_fixed_vs_joint/` | 480/480 次 CP-SAT（1 s）接受；每个实例的总延期与归档 exp_035 完全相同（两次都为 410 个 OPTIMAL） |

单窗口 G3A 阶段尚未用新代码重跑的：`g1 --long`、`g2`–`g4`，以及单窗口上的注意力策略试跑
（对应归档 exp_036–038、exp_040）；这些结论仍以 `experiments/archive/` 为准。

## 周期性维护与 G4

G4 的提交都早于 `957f3a8`（不可变调度重构）。当前代码只验证过单窗口 K = 1 与旧代码等价（`periodic_k1_regression/`），
所以 G4 的结果行、教师数据和模型只能在下表的提交上逐项重跑；G4 的汇总可以用当前 `g9` 从归档结果行精确复算。

| 结果 | 提交 | 内容 |
|---|---|---|
| `periodic_k1_regression/` | `60729a5` | 多窗口扩展后，单窗口结果与原代码 16 项全部一致 |
| `g4_teacher_data/` | `74cdf56` | 2 万个训练实例的 IGA-5000 教师轨迹（`train.jsonl` 可重新生成、不入库，哈希见 manifest）+ 验证集 |
| `g4_attention_policy/` | `858a32b` | 注意力策略（解码器 MDP），验证集选出的检查点 |
| `g4_search_curves/` | `be01963` | 第一次搜索曲线运行（与训练同时进行，IGA/SA 计时偏慢，只采用其中的规则、GA、CP-SAT） |
| `g4_search_curves_retimed/` | `49cce27` | 机器空闲时重跑的 IGA、SA |
| `g4_policy_curves/` | `d9e53c7` | RL 单实例计时 |
| `g4_summary/` | `150b652` | 汇总、曲线图和 [findings.md](g4_summary/findings.md) |
| `g4_gantt/` | `775ebbb` | 甘特图示例（PNG/PDF）：n20-m2 固定 86 → 联合 66；n20-m4 固定 129 → 联合 67；n50-m4 两者都是 26 |

## G5 补充实验（运行与汇总为提交 `7999b06`，训练为 `6b0656b`）

`7999b06` 之后源码只加了参数校验和注释，默认行为不变，所以 G5 可以用当前代码重跑（源码哈希会与 manifest 不同）。

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
| `g15_cluster_robustness/` | 按基础数据聚类的稳健性检验（G4、G5、L2）与 G4 的 Holm 校正（提交 cc1fd08，事后、探索性）和 [findings.md](g15_cluster_robustness/findings.md) |

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

## 读法与勘误

各结果目录内的文件（含 `findings.md`）是归档证据，按原样保留，不再修改；下面这些更正与补充说明以本节为准，
详细说明见 [START_HERE.md](../../START_HERE.md) 的"已知局限"。

- **测试实例不是独立样本（G4、G5）**：加工时间和交期分位数只由 `(n, 实例种子)` 决定，同一 `(n, 种子)` 下 48 个案例
  （G5-L 为 32 个）× 固定/联合共用一份基础数据。G4 与 G5-T 各只有 6 组基础数据（n = 100 只有 2 组），G5-L 只有 2 组。
  各 findings 中的 Wilcoxon p 值把每个实例当作独立样本，偏乐观；胜/平/负与均值照常可读。
  L2 同理：T1 10 个算例、T2 6 个算例，同一算例的 5 种配置不独立。按基础数据聚类后：G5 的 H1–H5 都不可能显著（组数太少），
  方向基本一致，H5 只在一组上成立；L2 的 H1–H3 仍成立，H4 不成立。见 [g15_cluster_robustness](g15_cluster_robustness/findings.md)。
- **G4 的检验**（`g4_summary/`）是双侧 Wilcoxon，没有做 Holm 校正，也没有实现协议为 H1 预先登记的 p < 0.01 阈值，只作描述；
  例如 H2 中"2 s 时 RL 优于 IGA（p = 0.012）"与 H2 的登记方向相反，在 H2 族内按双侧 Holm 为 0.036，只能作事后观察。
  按登记方向的单侧检验与 Holm 见 [g15_cluster_robustness](g15_cluster_robustness/findings.md)：H1 只在 0.2 s 对 SA、GA 成立，H2 只在 10 s 成立。
- **`g5_summary/findings.md` 中"RL + IGA 在 n ≥ 50、1 s 以后所有方法中最好"过宽**：同一文件的表中，n = 50、10 s 时
  SA 为 0.008，RL + IGA 为 0.009–0.012。准确说法：n = 100 时 1 s 以后、n = 200 时 10 s 最好；n = 50 时 1 s 最好。
- **测试集的再次使用**：测试集没有用于训练或选模型，但 `g4_gantt/`（按测试集结果挑案例）、`g5_iga_retime_check/`、
  `g5_iga_speed_sensitivity/` 都是看过测试结果之后的事后诊断，不作为独立证据。
- **计时口径**：RL 主曲线按 GPU 计时，搜索算法按 CPU 计时，单线程 CPU 推理另列为 `RL-cpu`；G5 的 H3（10 s）
  没有做 IGA 速度敏感性检验，`g5_iga_speed_sensitivity/` 中 H3 在 f > 1 时没有新数据。
