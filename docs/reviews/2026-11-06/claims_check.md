# 归档证据核对：START_HERE / docs/methods 的关键数字（只读重算）

- 核对时间：2026-11-06。核对对象：`START_HERE.md` 与 `docs/methods.md` 的 11 条数字声称 + 6 个 manifest 抽检。
- 方法：只用 `open(..., 'rb')`、`csv.DictReader`、`json.load`、`git show`/`git merge-base`（只读）读取归档文件；解释器为项目专用 Conda 环境（本机路径略）（Python 3.11.15）。未运行任何实验脚本，未改动 `experiments/results/`、`experiments/archive/` 及任何项目文件（本文件除外）。
- 结果概览：11 条数字声称中 **9 条成立、2 条基本成立但口径/舍入有偏差**；6 个 manifest 的 commit 全部在 `main` 历史中，源码与输入 SHA-256 逐文件复核一致。

## 核对表

| # | 声称 | 出处 | 原始数据（文件 / 列 / 取法） | 重算结果 | 结论 |
|---|---|---|---|---|---|
| A1 | 毕设联合维护 vs 固定维护：n=20/50/100 平均降低总延期约 **49% / 11% / 7%** | `START_HERE.md:23`；`docs/methods.md:240`（“G4 中”） | G4 无 `g4_comparison` 结果目录；实际是 `g4_summary/summary.json` 的 `H3_joint_vs_fixed_on_best_known`（findings 即由此生成）。原始行：`g4_search_curves/rows.jsonl` + `g4_search_curves_retimed/rows.jsonl`（IGA/SA 重计时覆盖）+ `g4_policy_curves/rows.jsonl`。对每个 `case_id` 的 fixed/joint 配对：`best_known` = min(MDD/ATC/EDD、IGA/GA 末值、SA 全部 8 个时间预算、CP-SAT incumbent、RL GPU 与 CPU 的全部贪心+采样点)；只取 `fixed.best_known > 0` 的配对，算 `(fixed−joint)/fixed` 的**算术平均**；n 分组把 α=10/20、β=25/50、τ=75/125、m=2/4/8、profile 全部合并 | n=20：69/96 对 → **49.45%**（中位 44.25%，69 好/0 差）；n=50：44/96 → **10.72%**（中位 5.05%，29/0）；n=100：40/96 → **6.94%**（中位 3.07%，31 好/1 差）。与 findings 的 49.4/10.7/6.9 逐位吻合 | **成立（数字可复现），但口径必须写明**：是“仅固定方案延期>0 的配对、按实例相对降幅”的均值，不是总延期之和的降幅（该口径为 43.2%/11.2%/8.3%），也与时间预算无关（best-known 取所有方法所有预算）。G5 新数据同口径为 46.7%/17.1%/12.9%（`g5_summary/summary.json`），n=50/100 明显不同，不宜外推 |
| A2 | RL 相对只做模仿，总延期降低约 **11%** | `START_HERE.md:26`；`docs/methods.md:238`；`g5_summary/findings.md` “只模仿与 RL（E2）” | `g5_policy_curves_seed{0,1,2}/rows.jsonl` 的 `device.greedy.value`（RL）vs `g5_bc_curves_seed{0,1,2}/rows.jsonl` 同列（只模仿）；每个 run 576 行 = 288 案例 × fixed/joint，n=20/50/100 各 192 行 | seed0：52.72 vs 59.07 → **10.74%**；seed1：52.48 vs 59.14 → **11.26%**；seed2：52.76 vs 59.49 → **11.30%**；三种子均值 **11.10%**。`summary.json.imitation_ablation` 的 `mean_rl/mean_bc` 与上表一致 | **成立**（约 11%）。口径：GPU 单次贪心、576 实例（fixed+joint 合并）均值、三训练种子；G5 预先登记的配对检验 H2 也成立（52.7 vs 59.1，Holm p≈4e-21） |
| A3 | 其中 n=100 约 **13%** | `START_HERE.md:26`；`g5_summary/findings.md` | 同上，取 `num_tasks=100` 的 192 行 | greedy n=100：**12.94% / 13.13% / 11.41%**（seed0/1/2），三种子均 **12.49%**；sample16 点为 14.45%/11.07%/15.56%（均 13.69%） | **口径不同 / 略偏乐观**：实际约 12.5%（11.4–13.1%），只有 seed0 或 2 位有效数字才是“13%”；建议写“约 12–13%”或给出种子范围 |
| B1 | 大创 L2：采样 32 次比逐算例最好规则好约 **16%** | `docs/methods.md:305`；`l2_formal_test/findings.md`；`l2_formal_test/summary.csv` | `l2_formal_test/rows.csv`：`sample32_s{0,1,2}` / `best_rule`；`best_rule` 是每算例 4 条规则（EFT、FIFO+NV、SPT+NV、MWKR+NV）的最小值；T2 = 6 个大算例 × 5 配置 = 30 组合；口径是**每条 ratio 的均值**（`_ratio()`，不是均值之比） | T2 `all`：seed0/1/2 = 0.8428 / 0.8277 / 0.8393 → 低 **15.72% / 17.23% / 16.07%**（均值 16.34%） | **成立**（约 16%） |
| B2 | L2：采样 32 次比大预算 SA 好约 **10%** | `docs/methods.md:305-306`；`l2_formal_test/findings.md` | 同文件 `sample32_s*` / `sa_reference`；`sa_reference` 由 `l2_formal_test.py:124-135` 从 `l1_benchmark` 的 CP-SAT 与 `l1_search` 的 SA（两种子取优；T1 每次 5000、T2 每次 1000 次评估）合并得到 | T2 `all`：0.9111 / 0.8960 / 0.9074 → 低 **8.89% / 10.40% / 9.26%**（均值 9.52%） | **基本成立，但“约 10%”偏高 0.5 个百分点**：三种子均值 9.5%，仅 seed1 达 10.4%。另“大预算 SA”只是 1000/5000 次评估的 SA，不代表收敛最优 |
| B3 | L2：小算例距证得最优约 **12.5%** | `docs/methods.md:306`；`l2_formal_test/findings.md`；`summary.csv` | `l2_formal_test/rows.csv`：T1 中 `cpsat_status == OPTIMAL` 的 43/50 个组合（`n_optimal=43`），`sample32_s{0,1,2}` / `cpsat` | seed0/1/2 = 1.1250 / 1.1266 / 1.1239 → 高于最优 **12.50% / 12.66% / 12.39%**（中位 11.94%/12.29%/11.84%；贪心为 20.5–21.3%） | **成立**（约 12.5%）。限制：只在 CP-SAT 证得最优的 43/50 组合上算，且是 makespan 比值均值，最优值很小的组合会放大比例 |
| B4 | L1：fjsp7 找到 **108**（公开 **112**） | `START_HERE.md:35`；`docs/methods.md:288`；`l1_benchmark/findings.md` Q2 | `l1_benchmark/rows.csv`：`method=reference-replay` 的 fjsp7 行 `makespan=112, reported=112, status=ACCEPTED`；`method=CP-SAT, config=bench` 的 fjsp7 行 `status=FEASIBLE, makespan=108, bound=104`（60.1 s）；同算例在 `config=block-inf / block-2` 下 CP-SAT `status=OPTIMAL, makespan=108`（54.2 / 28.4 s）。bench 配置 CP-SAT 9/10 为 OPTIMAL（fjsp1–6、8–10） | 10 条 replay 的 `makespan` 与 `reported` 全部相等（134/114/120/114/94/138/112/178/144/174）；fjsp7 的 108 与 112 如上；`status` 计数 OPTIMAL 9、FEASIBLE 1 | **成立（108 确实优于 112），但表述应更严格**：bench 约定下 CP-SAT 只得到限时可行解 108（下界 104）；“108 最优”是在阻塞+无限缓冲/阻塞+B=2 的更强约束下证得的，故 bench 约定下最优值 ∈[104,108]，未证明 108 为 bench 最优。另该次 CP-SAT 是 60 s 预算，不是 10 s |
| B5 | L1 大算例：以 SA 为参考，缓冲 ∞/2/1/0 的 makespan 比基准约定高 **4% / 3% / 9% / 41%** | `docs/methods.md:290`；`l1_search/findings.md` Q3 | `l1_search/rows.csv`，`part=large`（60 行 = 6 算例 × 5 配置 × 2 seed，`method=SA`，`evaluations=1000`）。对每个配置、每个算例取 2 个 seed 的最优 makespan，再对 6 个算例求相对 `bench` 的平均增幅 | block-inf **4.20%**、block-2 **3.00%**、block-1 **8.97%**、block-0 **40.65%**；与 `l1_search/summary.csv` 的 `mean_increase_vs_bench_best_of_seeds`（0.042/0.030/0.0897/0.4065）一致；逐算例增幅在 −4.9% ~ +78.4% | **成立（四舍五入后 4/3/9/41）**。限制：仅 6 个大算例、每配置 2 个 SA 种子、1000 次评估；B=∞ 与 B=2 只差 1.2pp 且逐算例有负值。规则基线给出的估计是 +6.0%/+11.5%/+51.8%，与 SA 差 3–11pp → 只有“无缓冲大幅变差”稳健 |
| C1 | 底座：**248** 个调度全部通过检查 | `START_HERE.md:43`；`docs/methods.md:86` | `p1_static_fjsp/rows.csv`：248 行 = 31 算例（30 个 FJSPLib + 玩具 `toy_3x3`）× 8 方法；`feasible` 列；`manifest.json` 的 `all_feasible`、`schedules` | 行数 **248**；`feasible` 分布 `{True: 248}`；manifest `all_feasible=true, schedules=248` | **成立** |
| C2 | 底座：CP-SAT **10 秒内 15 个证得最优** | `START_HERE.md:43`；`docs/methods.md:86` | `p1_static_fjsp/rows.csv`，`method=CP-SAT` 的 31 行：`status`、`seconds`、`gap_to_ub`；`manifest.time_limit` | `status` = OPTIMAL **15**、FEASIBLE 16；manifest `time_limit=10.0`；15 个 OPTIMAL 中最大耗时 **8.42 s**（<10 s）；`gap_to_ub==0` 共 **18** 行（与 methods 的“18 个达到公开已知最好值”一致） | **成立**。边界说明：有一行 FEASIBLE 的墙钟为 **10.03 s**（超时后收尾），若“10 秒内”指每次运行墙钟 ≤10 s 则严格不成立；“15 个证得最优”本身成立 |
| C3 | 底座：**243** 次重调度全部通过检查 | `START_HERE.md:44`；`docs/methods.md:105`；`p2_dynamic_protocol.py:51-56` | `p2_dynamic_protocol/rows.csv`：`feasible`、`issues` 列；该脚本 `feasible = 静态检查 and 动态检查`，两者都过才不写 `issues`；`manifest.json` 的 `expected_runs/passed_runs/status`。交叉核对 `archive/exp_019_phase2a_protocol_v1/raw.csv`（重构前归档） | 行数 **243**；`feasible` 全 True；`issues` 全空；manifest `expected_runs=passed_runs=243, status=COMPLETED`；归档 `exp_019` 同为 243 行、`feasible` 全 True、manifest 243/243 | **成立**（静态与动态检查同时通过） |
| D | manifest 抽检（6 个）：commit、`git_dirty`、是否在 main 历史、是否可用于复现 | `AGENTS.md` “分支与证据规则”；各结果目录 | 见下方“manifest 抽检明细表” | 6 个 commit 全部存在且为 HEAD(`main`) 祖先；`git_dirty` 全 false；6 个 manifest 记录的源码 SHA-256 与 `git show <commit>:<path>` 内容逐文件一致（33/33、33/33、43/43、44/44、47/47、47/47）；`g4_summary` 输入 3/3、`g5_summary` 输入 20/20 与 source 47/47 亦一致 | **可用于复现**（代码状态可由 commit 唯一确定，输入数据未变）。但有 3 处工程隐患，见下 |

## manifest 抽检明细

| manifest | `git_commit` | `git_dirty` | 在 main 历史（`merge-base --is-ancestor`） | 源码 hash 复核 |
|---|---|---|---|---|
| `p1_static_fjsp` | `1563f43b513883fc1db57f361f1cd05539e42ccf` | false | 是 | 33/33 匹配 |
| `p2_dynamic_protocol` | `1563f43b513883fc1db57f361f1cd05539e42ccf` | false | 是 | 33/33 匹配 |
| `l1_benchmark` | `c981fcbbeff294fad3cc3c56074aa6eabcaca8df`（嵌在 `provenance` 内） | false | 是 | 43/43 匹配 |
| `l1_large` | `0e37383f343c057aaa17c11b01e9bca8ca665c1c`（嵌在 `provenance` 内） | false | 是 | 44/44 匹配 |
| `l2_formal_test` | `a685ac83636a45749d4e55046d5360b3b2ae8d74`（嵌在 `provenance` 内） | false | 是 | 47/47 匹配 |
| `g5_policy_curves_seed0` | `7999b065bfab2f6afb95d8a14a86ca10843c3ba1` | false | 是 | 47/47 匹配 |

- 另核对了其余相关 commit，全部为 HEAD(`main`) 祖先：`l1_search 8673ba7`、`l2_formal_train 3cfc48a`、`g4_policy_curves d9e53c7`、`g4_search_curves be01963`、`g4_search_curves_retimed 49cce27`、`g4_summary 150b652`（`g4_summary` 没有 `manifest.json`，commit 只写在 `summary.json.git_commit`）。
- 输入数据完整性：`g4_summary/summary.json.inputs_sha256` 对 3 个 `rows.jsonl` 全部匹配；`g5_summary/summary.json.inputs_sha256` 对 20 个 `rows.jsonl` 全部匹配（核对时按 `experiments/` 为基目录解析）。
- 复现性结论：上述 commit 都在 `main` 上，源码 hash 与提交内容一致、归档行文件 hash 与汇总记录一致，因此“归档结果 ↔ 代码状态 ↔ 原始行”三者可闭环核验，不是事后拼凑的证据。

## 证据可靠性总评

12 项核对全部完成：11 条数字声称中 9 条成立，2 条（n=100“约 13%”、L2“比大预算 SA 好约 10%”）是口径/舍入偏高（实为 12.5% 与 9.5%），没有发现无法重算或与原始行矛盾的声称；6 个 manifest 的 commit 均在 `main` 历史中，源码与输入 SHA-256 逐文件复核为零不匹配，说明证据链本身真实、可追溯。

但结论级数字普遍依赖口径选择：G4 的 49%/11%/7% 是“仅固定方案延期>0 的配对、按实例相对降幅、best-known 取全部方法与全部时间预算”的均值，中位数只有 44%/5%/3%，换成总延期和口径为 43%/11%/8%，而 G5 新数据同口径是 47%/17%/13%，说明“约 11%/约 7%”对数据集与口径敏感，宜作为本数据集观察值而非稳定机制引用。

L1 的 4%/3%/9%/41% 仅由 6 个大算例 × 每配置 2 个 SA 种子得出，逐算例增幅 −4.9%~+78%，且规则基线与 SA 给出的 B=2/B=1/B=0 估计相差 3–11 个百分点，只有“无缓冲显著变差”是稳健结论；“420 次全部合法”也只是脚本内检查器接受（`l1_large` 只存 `status`，未存调度明细），复现需重跑仿真。

两个最应修补的证据弱点：一是 L1 大算例依赖 `instances/external/HomayouniFontes/` 的 4/5/6/8 机布局文件（本次核对时 4 个文件 hash 与 manifest 一致），但该目录被 `.gitignore` 排除、新克隆无法重跑 L1 大算例；二是 provenance 结构不统一（`l1_*`/`l2_*` 的 commit 藏在 `provenance` 下、`g4_summary` 无 manifest、`g4`/`g5` 的 `inputs_sha256` 路径基准分别是项目根与 `experiments/`），批量自动核查会把一半 manifest 误判为“无 commit/输入缺失”，建议在复现脚本中固化解析规则并把外部布局的来源与获取方式写入文档。
