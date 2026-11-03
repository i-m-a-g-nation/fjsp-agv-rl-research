# 实验

每个脚本写入一个**新**目录（默认 `experiments/runs/<名称>-<UTC时间>`，`runs/` 不入库）；要归档时用
`--output-dir experiments/results/<名称>`，已存在的目录不会被覆盖。每个输出都有 `manifest.json`，记录 git 提交、
是否有未提交改动、Python/包版本，以及 `src/fjsp_lab` 全部源码和脚本的 SHA-256。所有返回的调度都会再次经过检查器。

## 脚本

| 脚本 | 内容 | 环境 | 时长（参考） |
|---|---|---|---|
| `p1_static_fjsp.py` | 玩具实例 + 30 个 FJSPLib：7 条规则与 CP-SAT（默认 10 s/实例），对照 FJSPLib 上下界；玩具甘特图 | 项目 | ~5 min |
| `p2_dynamic_protocol.py` | Phase 2A 固定协议 `inputs/phase2a_v1.json`：3 实例 × 3 事件 × 3 种子 × 3 规则 × 3 次 = 243 次重调度 | 项目 | <1 min |
| `g1_cpsat_fixed_vs_joint.py` | G3A 240 组 × 固定/联合，CP-SAT 1 s；`--long` 另加 n=24 主网格 60 s × 4 线程 | 项目 | 8 min（+20 min） |
| `g2_scoring_policy.py` | NumPy 打分策略：3 个种子训练（模仿最好规则 + REINFORCE），验证集选模型，测试集与规则按相同回放次数对比 | 项目 | ~30 min |
| `g3_metaheuristics.py` | GA/SA/IGA × 预算 1k/10k/50k × 种子 0–4，G3A 全部 480 个实例 | 项目 | ~20 min |
| `g4_comparison.py` | 论文主表：规则、打分策略、元启发式、CP-SAT 1 s/60 s 在 G3A 上汇总；读取 g1/g2/g3 的输出 | 项目 | ~2 min |
| `g5_teacher_data.py` | 注意力策略的教师数据：2 万个训练实例的 IGA-10k 轨迹 + 验证集参考值 | 项目 | ~6 min |
| `g6_attention_policy.py` | 注意力策略：模仿 IGA 教师 + REINFORCE，只用验证集选模型 | PyTorch | ≤2 h |
| `g7_g4_search_curves.py` | G4：规则、GA/SA/IGA（随时间的最好值轨迹）、CP-SAT（各个可行解）在 576 个测试实例上；`--methods/--processes` 可只重跑部分方法 | 项目 | ~2 h |
| `g8_g4_policy_curves.py` | G4：注意力策略单实例计时（GPU 贪心 + 采样 4/16/64；CPU 贪心 + 采样 4） | PyTorch | ~20 min |
| `g9_g4_summary.py` | G4：质量—时间曲线、H1–H3、探索性分组检验、曲线图 | 项目 | <1 min |
| `g10_gantt_examples.py` | 甘特图示例：每种规模选协同降幅为中位数的案例（规则先定后画），画 IGA 的固定与联合两种方案 | 项目 | ~1 min |
| `l1_decoupled.py` | 大创 L1：解耦基线（D0 不计运输 / D1 计入载货行驶；先排机器再优化车辆，30 s + 30 s × 8 线程）与已归档的联合 CP-SAT 对比，同样 10 算例 × 5 配置 | 项目 | ≤100 min |
| `l1_large.py` | 大创 L1：Brandimarte mk01–05、mk07 + Homayouni & Fontes 整数布局，2 台车，5 种配置；各规则普通与前瞻式死锁规避两种模式；与无求解器下界对比。需本地布局 `instances/external/HomayouniFontes` | 项目 | ~5 min |
| `l1_search.py` | 大创 L1：SA（参考）与 GA 元启发式；A 部分 10 个小算例 × 5 配置对照 CP-SAT，B 部分 6 个大算例 × 5 配置对照最好规避规则与下界；8 进程并行 | 项目 | ~1 h |
| `l2_policy_pilot.py` | 大创 L2 试训：模仿 + REINFORCE，只用训练/验证集，`--rl-epochs`、`--samples` 可改预算；不归档 | 项目 | 视预算而定 |
| `l2_formal_train.py` | 大创 L2 正式训练（[协议](../docs/protocols/l2_formal_protocol.md)）：3 个种子顺序训练，每个种子 18 进程采样，验证集选模型；写检查点与哈希 | 项目 | ~1.6 h |
| `l2_formal_test.py` | 大创 L2 正式测试：核对检查点哈希；T1（10 小算例）与 T2（Brandimarte 6 个）× 5 配置；规则、贪心/采样 8/32、同等时间与同等评估次数 SA；H1–H4 | 项目 | ~45 min |
| `l1_benchmark.py` | 大创 L1：Deroussi & Norre 10 个 FJSPT 算例；参考解重放；CP-SAT 60 s × 8 线程与联合/解耦/随机规则，在基准约定和"阻塞 + 输入缓冲 ∞/2/1/0"下对比。需本地数据 `instances/external/FJSPT`（无许可证，不入库） | 项目 | ≤50 min |

实例划分（`fjsp_lab.maintenance.generator.SPLITS`）按种子区间互不重叠：训练 10000–11999、验证 20000–20199、
测试 30000–30599（6 种规模各 100）、教师训练 100000–119999。测试集只在训练结束后使用一次。

## inputs/

- `phase2a_v1.json`：Phase 2A 协议。
- `dynamic_events_*.json`：三个事件文件示例（在 `tests/test_dynamic.py` 中回放）。

## results/ 与 archive/

- `results/`：当前代码（`fjsp_lab`）产生的结果。
- `archive/`：2026-10-31 重构前旧代码产生的结果，**逐字节未改动**。它们的 manifest 绑定的是旧路径
  （`src/graduation/…` 等），要按哈希核验请切到分支 `archive/pre-restructure-2026-10-31`。重构后的代码在相同输入上
  与旧代码给出完全相同的结果，核对方法与记录见 [archive/restructure_equivalence/](archive/restructure_equivalence)。

旧编号与新脚本的对应：

| 旧结果（archive/） | 内容 | 现在对应 |
|---|---|---|
| `exp_001`–`exp_013`，`phase1_*` | Phase 1 规则、CP-SAT、基准矩阵、验收 | `p1_static_fjsp.py` |
| `exp_014`–`exp_017`，`exp_019`，`exp_020` | Phase 2A 事件、协议、顺序回放 | `p2_dynamic_protocol.py`；事件文件与回放在测试中 |
| `exp_021_graduation_g2_v1`，`exp_034` | 维护模型 CP-SAT 与枚举核对、solver_v2 验收规则 | `tests/maintenance/test_maintenance_algorithms.py` |
| `exp_035_graduation_main_v2_v1` | G3A 固定 vs 联合（CP-SAT 1 s） | `g1_cpsat_fixed_vs_joint.py` |
| `exp_036`，`exp_037` | 打分策略训练与采样解码 | `g2_scoring_policy.py` |
| `exp_038_g3b_comparison_v1` | 策略 vs 规则 vs CP-SAT 60 s | `g4_comparison.py`（含 g1 `--long`） |
| `exp_039_atc_k2_baseline_v1` | ATC k=2 复核 | 结论已定；`rules.solve_dispatch_rule(atc_k=2)` 可复现 |
| `exp_040_metaheuristics_v1` | GA/SA/IGA | `g3_metaheuristics.py` + `g4_comparison.py` |
| `exp_041_seeded_iga_v1` | RL 初始解的 IGA | `solve_metaheuristic(..., initial_sequences=...)` |
| 原 exp_042/043（未归档的试跑） | 教师数据、注意力策略试跑 | `g5_teacher_data.py`、`g6_attention_policy.py` |

已删除的旧结果（AI 工作流、论文字段抽取、旧 NumPy RL 诊断、G3A 第一次失败批次及补救开发等，exp_018、022–033、model_api_*）
只在备份分支里。
