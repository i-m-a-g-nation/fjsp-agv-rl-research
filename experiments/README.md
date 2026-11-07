# 实验

每个脚本对应一个实验步骤。脚本按研究线编号：`p*` 底座，`g*` 毕设，`l*` 大创。各批实验怎样串起来，见 [项目全景](../docs/overview.md) 第 4–6 节。

## 运行约定

- 每次运行写入一个**新**目录：默认 `experiments/runs/<名称>-<UTC时间>`（`runs/` 不入库）；要归档时用
  `--output-dir experiments/results/<名称>`。已存在的目录不会被覆盖。
- 每个输出都有 `manifest.json`：git 提交、是否有未提交改动（`git_dirty`）、Python 与包版本、`src/fjsp_lab` 全部源码和脚本的 SHA-256。
  正式结果要求先提交代码，使 `git_dirty` 为 false。
- 所有返回的调度都会再经过检查器。
- 环境：标"项目"的用项目专用 Conda 环境；标"PyTorch"的用本机已安装 PyTorch 的环境（见 [AGENTS.md](../AGENTS.md)）。
- 计时实验运行时，本机不要并行跑其他重计算。

## 底座

| 脚本 | 回答什么问题 / 做什么 | 环境 | 时长 |
|---|---|---|---|
| `p1_static_fjsp.py` | 7 条规则与 CP-SAT 在玩具算例和 30 个 FJSPLib 算例上是否都给出合法调度、离已知最好值多远；输出玩具甘特图 | 项目 | ~5 min |
| `p2_dynamic_protocol.py` | 按固定协议 `inputs/phase2a_v1.json` 做 3 算例 × 3 事件 × 3 种子 × 3 规则 × 3 次 = 243 次重调度，是否全部合法、可复现 | 项目 | <1 min |

## 毕设

### 单窗口阶段（G3A/G3B，结果在 `archive/`）

| 脚本 | 回答什么问题 / 做什么 | 环境 | 时长 |
|---|---|---|---|
| `g1_cpsat_fixed_vs_joint.py` | 固定 vs 联合维护：240 组算例 × 两种方式，CP-SAT 1 s；`--long` 另加 n = 24 主网格 60 s × 4 线程 | 项目 | 8 min（+20 min） |
| `g2_scoring_policy.py` | 早期 NumPy 打分策略：3 个种子训练（模仿最好规则 + REINFORCE），测试集上与规则比较 | 项目 | ~30 min |
| `g3_metaheuristics.py` | GA/SA/IGA × 预算 1k/10k/50k 次评估 × 种子 0–4，G3A 全部 480 个算例 | 项目 | ~20 min |
| `g4_comparison.py` | 单窗口论文主表：规则、打分策略、元启发式、CP-SAT 汇总（读取 g1–g3 的输出） | 项目 | ~2 min |

### 周期性维护与强化学习（G4）

| 脚本 | 回答什么问题 / 做什么 | 环境 | 时长 |
|---|---|---|---|
| `g5_teacher_data.py` | 生成强化学习的示范数据：2 万个训练算例上 IGA 的解（G4 为 5000 次评估）+ 验证集参考值 | 项目 | ~6 min |
| `g6_attention_policy.py` | 训练注意力策略：先模仿 IGA，再 REINFORCE；只用验证集选模型 | PyTorch | ≤2 h |
| `g7_g4_search_curves.py` | 规则、GA/SA/IGA、CP-SAT 在 576 个测试算例上"随时间的最好值"；`--methods/--processes` 可只重跑部分方法 | 项目 | ~2 h |
| `g8_g4_policy_curves.py` | 注意力策略逐算例计时：GPU 贪心 + 采样 4/16/64 次，CPU 贪心 + 采样 4 次 | PyTorch | ~20 min |
| `g9_g4_summary.py` | 汇总 G4：质量—时间曲线、预先登记的 H1–H3、分规模检验、曲线图 | 项目 | <1 min |
| `g10_gantt_examples.py` | 甘特图示例：每种规模挑协同降幅为中位数的算例，画 IGA 的固定与联合两种方案 | 项目 | ~1 min |

### 补充实验（G5）

G5 复用 `g7`（`--grid g5/g5-large`、`--cpsat-max-tasks`）与 `g8`（`--grid`、`--checkpoint best_bc`、`--save-sequences`）。

| 脚本 | 回答什么问题 / 做什么 | 环境 | 时长 |
|---|---|---|---|
| `g11_g5_seeded_iga.py` | RL 能否帮助搜索：用策略给出的排列热启动 IGA，总时长 10 s（含 RL 推理时间） | 项目 | ~2 h / 种子 |
| `g12_g5_summary.py` | 汇总 G5：曲线、预先登记的 H1–H5、种子差异、模仿消融、协同维护 | 项目 | <1 min |
| `g13_iga_retime_check.py` | 计时是否可信：空闲时抽样重跑 36 个 IGA，与 G4/G5 的记录比速度 | 项目 | ~3 min |
| `g14_g5_iga_speed_sensitivity.py` | 若 IGA 实际快 1.3/1.6/2 倍，G5 的结论还成立吗（探索性） | 项目 | <1 min |

## 大创

| 脚本 | 回答什么问题 / 做什么 | 环境 | 时长 |
|---|---|---|---|
| `l1_benchmark.py` | 模型是否与公开 FJSPT 基准一致；阻塞与缓冲 ∞/2/1/0 的影响；CP-SAT 与规则对比。需本地数据 `instances/external/FJSPT` | 项目 | ≤50 min |
| `l1_decoupled.py` | "先排机器再派车"比联合 CP-SAT 差多少（D0 不计运输 / D1 计入载货行驶） | 项目 | ≤100 min |
| `l1_large.py` | 大算例（Brandimarte 6 个 + Homayouni & Fontes 布局）上规则会不会死锁、前瞻式规避是否总能成功；与下界对比 | 项目 | ~5 min |
| `l1_search.py` | SA（参考）与 GA：小算例对照 CP-SAT 最优，大算例对照最好规避规则与下界 | 项目 | ~1 h |
| `l2_policy_pilot.py` | 强化学习试训（只用训练/验证集，不归档） | 项目 | 视预算 |
| `l2_formal_train.py` | 正式训练：3 个种子，验证集选模型，记录检查点哈希 | 项目 | ~1.6 h |
| `l2_formal_test.py` | 正式测试（测试集只用一次）：核对检查点哈希；与规则、SA 比较；H1–H4 | 项目 | ~45 min |

## 数据划分

`fjsp_lab.maintenance.generator` 按种子区间生成，训练、验证、测试互不重叠：

| 用途 | 种子 |
|---|---|
| G3A 早期打分策略：训练 / 验证 / 测试 | 10000–11999 / 20000–20199 / 30000–30599 |
| G3A 注意力策略教师训练 | 100000–119999 |
| G4 训练 / 验证 | 200000–219999 / 230000–230299 |
| G4 测试（288 个案例 × 固定/联合） | 实例种子 1001、1002 |
| G5 测试 / n = 200 推广集 | 实例种子 1003、1004 |

测试集不用于训练、选模型或调参；预先登记的假设只在训练结束后检验一次。之后对测试集的再次读取都是事后诊断，
不作为独立证据：`g10` 按测试集结果挑甘特图案例，`g13` 按测试集记录抽样复测计时，`g14` 在 G5 结果上做速度敏感性分析。

G4/G5 的测试网格中，加工时间和交期分位数只由 `(n, 实例种子)` 决定，同一 `(n, 种子)` 下的所有案例（及其固定/联合两种模式）
共用一份基础数据，因此实例数不等于独立样本数（G4 与 G5-T 各 6 组基础数据，G5-L 2 组）。

## inputs/

- `phase2a_v1.json`：Phase 2A 协议。
- `dynamic_events_*.json`：三个事件文件示例（在 `tests/test_dynamic.py` 中回放）。

## results/ 与 archive/

- `results/`：重构后代码产生的归档结果，索引与各目录结论见 [results/README.md](results/README.md)。
  每个目录绑定它自己 manifest（或 `summary.json`）里记录的提交，不一定是当前代码：G4 的结果行、教师数据和模型
  早于 `957f3a8`（不可变调度重构），只能在其提交上逐项重跑；G5 的源码哈希与当前代码一致。
- `archive/`：2026-10-31 重构前旧代码产生的结果，**逐字节未改动**。其 manifest 绑定旧路径（`src/graduation/…` 等），
  按哈希核验需切到分支 `archive/pre-restructure-2026-10-31`。重构后的代码在相同输入上给出完全相同的结果，
  核对记录见 [archive/restructure_equivalence/](archive/restructure_equivalence)。

旧编号与现在脚本的对应：

| 旧结果（archive/） | 内容 | 现在对应 |
|---|---|---|
| `exp_001`–`exp_013`，`phase1_*` | Phase 1 规则、CP-SAT、基准矩阵、验收 | `p1_static_fjsp.py` |
| `exp_014`–`exp_017`，`exp_019`，`exp_020` | Phase 2A 事件、协议、顺序回放 | `p2_dynamic_protocol.py`；事件文件与回放在测试中 |
| `exp_021_graduation_g2_v1`，`exp_034` | 维护模型 CP-SAT 与枚举核对 | `tests/maintenance/test_maintenance_algorithms.py` |
| `exp_035_graduation_main_v2_v1` | G3A 固定 vs 联合（CP-SAT 1 s） | `g1_cpsat_fixed_vs_joint.py` |
| `exp_036`，`exp_037` | 打分策略训练与采样解码 | `g2_scoring_policy.py` |
| `exp_038_g3b_comparison_v1` | 策略 vs 规则 vs CP-SAT 60 s | `g4_comparison.py`（含 g1 `--long`） |
| `exp_039_atc_k2_baseline_v1` | ATC k = 2 复核 | `rules.solve_dispatch_rule(atc_k=2)` 可复现 |
| `exp_040_metaheuristics_v1` | GA/SA/IGA | `g3_metaheuristics.py` + `g4_comparison.py` |
| `exp_041_seeded_iga_v1` | RL 初始解的 IGA | `solve_metaheuristic(..., initial_sequences=...)` |
