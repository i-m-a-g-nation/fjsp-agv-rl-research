# 毕设维护模型 / 算法 / 实验只读审查

审查对象：`src/fjsp_lab/maintenance/`（全部）、`tests/maintenance/`、`experiments/g1`–`g14`、`docs/models/graduation_model.md`、`docs/protocols/g4_periodic_protocol.md`、`g5_supplement_protocol.md`、`docs/plans/thesis_outline.md`、`docs/methods.md` 5.3/5.4、`START_HERE.md`、`experiments/results/` 中相关归档。
环境：项目专用 Conda 环境（本机路径略）（Python 3.10，numpy 2.4.5，ortools 9.15.6755，scipy 1.17.1；**无 PyTorch**）。未修改任何被 git 跟踪的文件；只写了本报告及 `tmp/review/runs/` 下的复算输出。
本次实际执行：`pytest tests/maintenance -q`（77 passed, 3 skipped，31.32 s）；解码器穷举；预算计数实验；用当前 `g9`/`g12` 从归档 rows 复算；对照归档做规则/数据哈希核验。

---

## 一、总体判断

代码工程质量高，模型、检查器、精确方法、解码器和预算记账这些“硬底座”基本可信；我**没有找到解码器非法反例、预算作弊、测试集训练泄漏或 CP-SAT 建模错误**。

但**论文结论层面的统计推断和复现声明有明显问题**，而且这些问题集中在最关键的 G4/G5 主表上：

1. **G4/G5 的“576/192/128 个测试实例”远非独立样本**：同一 `(n, seed)` 的 16–24 个因子组合共享同一份加工时间和交期分位数，n=100 时实际只有 2 组基础随机工作负载。H1–H5 的 Wilcoxon/Holm p 值把因子重复当独立样本，显著性被系统性夸大。这是本次审查发现的最严重问题。
2. **G4 的统计分析与预注册协议不一致**：`g9` 用双侧 Wilcoxon 且**完全没有 Holm 校正**；预注册的 H1 阈值 p<0.01 没有在代码中实现；G4 结论里“2 s 时 RL 优于 IGA（p=0.012）”本身已超过 0.01，且是在 9 个 H1 比较 + 6 个 H2 比较中挑出的。
3. **G4 结果由重构前代码产生，当前代码不是那套代码**：G4 的 search/policy/teacher 归档提交在 `957f3a8`（不可变 schedule 重构）之前，当前源码与 G4 归档源哈希有 16 个 `src` 文件不同；`results/README.md:3` “均由提交 1563f43 运行”是错的。G4 的**汇总**可以用当前 `g9` 从归档 rows 精确复算（我验证了），但 **G4 的 rows/模型本身没有在现有代码上验证过可重跑**；G5 才是现有代码的复现。

结论：**作为工程交付，可接受；作为论文证据，G4/G5 的“显著”“可复现”措辞需要收紧，非独立性问题必须披露或改用 cluster 级检验。** 解码器、精确方法、预算记账、RL 实现本身没有阻断性错误。

---

## 二、优点（有证据）

- **模型与本项目文档一致**：同质平行机、每任务单工序、0 时刻到达、每窗一次完整维护、窗口互不重叠；`instance.py:25-55,74-87` 校验；`feasibility.py:117-141` 检查完整窗口、固定起点、维护/生产互斥、总延期独立重算。
- **生成器确定性**：`generator.py:46-49` 用 SHA-256 派生种子，`random.Random` 采样；`test_maintenance_model.py:61-70` 验证同参数同实例；回归测试锁定了 G3A 首例的完整记录（`test_maintenance_model.py:73-80`）。
- **解码器“任意排列合法”在实践中成立**：我另写一次性片段，对 324 个小型/中型单窗口与周期实例、两种模式、**1 026 720 个排列**逐一解码并过 G7 检查器，0 反例；另对 m=1、零余量窗口、三窗口邻接等边界 2 164 个排列 0 反例；对 n=100/200 大规模随机排列与随机 SequenceEnv episode 也全部合法。`metaheuristics.py:102-148` 的实现与不变量（见第四节）足以解释。
- **精确方法可信**：CP-SAT 用 `AddMaxEquality` 精确表达 `t_j=max(0,C_j-d_j)`，维护窗口是必选 `NewIntervalVar` 且 `NoOverlap`（`cpsat.py:101-114`）；枚举独立实现（`enumeration.py:25-97`）；测试在 16 个单窗口 + 16 个周期小例、两模式下核对 CP-SAT = 枚举（`test_maintenance_algorithms.py:36-43`），并核对 CP-SAT 最优 = 全排列/环境最优（`:225-236`）。本次测试 77 通过。
- **预算记账没有发现作弊**：解码计数在 `TokenDecoder.decode`（`metaheuristics.py:107`），局部搜索的每个候选都经 `tracker.evaluate`（`:230-240`），三者共用 `Tracker.left`（`:199-223`），最终建 plan 的 1 次 decode 被显式扣除（`:150-157`），且 `SearchOutcome.evaluations` 在扣减前读取（`:330-331`）。实测 GA/SA/IGA 在预算 500 时均恰用 500 次，局部搜索包含在内。
- **RL 训练实现没有发现梯度泄漏/符号错误**：采样阶段整体 `torch.no_grad()`（`attention_policy.py:108`），记录特征/选择后在 `reinforce_step` 重新打分回传（`:217-247`）；共享基线是同一算例 K 次采样均值（`:227-232`）；`advantage=(T-mean)` 乘以 `logπ` 后 `.backward()`，而 `g6` 的 `optimizer.step()` 做梯度下降，方向等价于最小化期望 T，**符号正确**（`g6_attention_policy.py:109-114` 与 `attention_policy.py:245-247`）；BC 交叉熵、Adam、clip 1.0 均按文档。掩码用 bool `padding` + `masked_fill(..., -inf)`，softmax 只在合法候选上（`attention_policy.py:70-73,93-100,114-121`）。
- **数据泄漏（训练/验证/测试）在种子层面不成立**：`generator.py:146-151,250-260` 的区间互不重叠；`g6` 只读 `train.jsonl`/`validation.jsonl`（`:88-93`），`checkpoint` 只在 `val_rows` 上算贪心均值（`:98-107`），从不读测试；`g8` 加载验证集选出的 checkpoint 并校验 SHA（`g8_g4_policy_curves.py:84-88`）；`g5` 的 checkpoint/teacher 数据哈希我已核对通过。
- **归档哈希与复算质量好**：teacher 数据 20 000/300 行，manifest 文件哈希与 g4 policy summary 的 data manifest 哈希一致；6 个 checkpoint SHA 均与归档一致；用当前 `g9` 从 G4 归档 rows 复算，`curves.csv` 360 行逐字节一致；用当前 `g12` 从 G5 归档 rows 复算，`curves.csv` 720 行、`hypotheses.csv` 20 行逐字节一致。
- **质量—时间曲线的语义基本正确**：IGA/GA 的 trace 只在改进时记录 `(seconds, evaluations, best)`（`metaheuristics.py:217-223`），`g9` 取 `seconds<=t` 的最小值（`g9_g4_summary.py:50-57`）；SA 为每个预算单独跑（`g7_g4_search_curves.py:61-67`）；RL 用贪心 + 采样 4/16/64 的点（`g8_g4_policy_curves.py:57-69`）；CP-SAT 用 incumbent 轨迹（`g7:70-75`）。

---

## 三、问题清单

### 严重（影响论文结论有效性）

**S1. G4/G5 测试实例高度不独立，p 值/显著性被夸大。**
- 证据：`generator.py:46-49` 的加工时间/交期分位数键是 `n, seed, field`；`build_instance`（`:59-76`）与 `build_periodic_instance`（`:185-207`）里 `p` 与 `u` 只由 `(n,seed)` 决定，`alpha/beta/profile` 只改维护，`tau/m` 只改交期或维护，**不改加工时间**。G4 测试网格是 `n∈{20,50,100}×m∈{2,4,8}×profile2×α2×β2×τ2×seed{1001,1002}`（`generator.py:246-249`），G5 只换 seed 1003/1004（`:259`）。因此 n=100 的 192 个“实例”（96 case × 2 模式）只共享 **2 组**基础 `p/u` 随机流；n≥50 的 384 个实例只有 4 组；G5-L 的 128 个实例只有 2 组。固定/联合两种模式也共享同一份基础数据。
- 影响：`g9` 的 H1/H2（`g9_g4_summary.py:72-85,126-131`）和 `g12` 的 H1–H5（`g12_g5_summary.py:32-34,135-155`）把它们当独立配对样本，Wilcoxon 的 p 值（如 G5 H1 seed0 的 `p_holm=1.19e-8`、G4 n=100 探索性 `p≤3e-6`）在“基础工作负载”层面没有对应的独立重复。效应方向和配对胜/负仍可描述，但“显著”“普遍”不能按现有 p 值写。G3A 协议已经明确警告过同类问题（`docs/protocols/g3a_protocol.md:35,58,84`：“格数不是独立样本数”“同一基础随机流重复使用”），**G4/G5 协议与 findings 没有继承这一披露**（`g4_periodic_protocol.md`、`g5_supplement_protocol.md`、两份 findings 均无）。
- 修复：以 `(n, instance_seed)`（最多 6 个基础工作负载，n=100 只有 2 个）为聚类单位做 cluster-level 置换/加权检验，或把结论降级为“在这些测试算例上配对更优”；至少在 G4/G5 findings、论文第 5 章明确写出“288 case 不是独立样本、同一 p/u 流被 16–24 个因子组合复用”。若要真正的 576 个独立实例，应给每个 case 独立实例种子（代价是失去因子配对）。
- 这条不否定代码正确性，但**直接影响“显著优于”“H1–H5 成立”的统计表述**。

**S2. G4 主表统计没有 Holm 校正，且未实现预注册的 p<0.01 阈值。**
- 证据：`g4_periodic_protocol.md:62-68` 预注册 H1 为“配对 Wilcoxon，p<0.01”；`g9_g4_summary.py:72-85` 的 `wilcoxon_test` 使用 `scipy.stats.wilcoxon(nonzero)`（默认双侧），`h1` 在 3 个预算 × 3 个对照上共 9 次检验（`:126`），`h2` 6 次（`:127`），另有 24 个探索性检验（`:129-131`），**全文件没有 Holm/Bonferroni**。`g4_summary/findings.md:23` 的“2 s 时 RL 优于 IGA（p=0.012）”既未过 0.01，也未做多重校正；同一段还写了多个方向相反/不显著的结论。
- 影响：G4 的“H2 部分成立”、以及“n=100、0.2–2 s 显著优于 IGA/SA”的探索性表述都依赖未校正/事后选择的 p 值。n=100 的探索性 p≤3e-6 较大，但同样受 S1 的非独立性问题影响。H1 本身结论“不成立”不受影响。
- 修复：G4 与 G5 一样，在每个假设族内做 Holm（或预注册单一检验/固定顺序），并把“p<0.01”写进代码而不是只在文档里；描述性/事后分析明确标 post hoc。
- `g4_comparison.py:101-118` 和 `experiments/_common.py:96-108` 的 `paired` 也没有多重校正（G3A/单窗口表若只作描述可接受，但不能据此写“显著”）。

**S3. G4 的结果不是当前代码产生的，`results/README.md` 的复现声明错误。**
- 证据：`experiments/results/README.md:3` 写“均由提交 1563f43 运行”，但 G4 的 `g4_search_curves/manifest.json` 是 `be01963`，`g4_policy_curves` 是 `d9e53c7`，`g4_attention_policy/summary.json` 是 `858a32b`，`g4_teacher_data` 是 `74cdf56`，`g4_summary` 是 `150b652`；这些都早于 `957f3a8`（不可变 schedule 重构）。我比较当前 `src` 与 G4 归档源哈希：**16 个 `src` 文件不同**（含 `metaheuristics.py`、`sequence_env.py`、`attention_policy.py`、`generator.py`、`feasibility.py` 等）；而 G5 各 manifest 的 `source_sha256` 与当前源码 **0 个不同**。`periodic_k1_regression/README.md` 只核对了 **K=1 单窗口**与重构前代码的 26 项等价，不覆盖 G4 的周期性多窗口。
- 影响：G4 的**汇总**可从归档 rows 复算（我已验证），但 G4 的 rows/模型**无法用当前代码逐项重跑验证**；论文若写“当前代码可复现 G4”，不成立。G5 是当前代码的复现，但只换了测试种子，不能替代 G4 的代码等价性验证。另 `results/README.md:11` 自己又写“尚未用新代码重跑 g1 --long、g2–g6”，与第 3 行矛盾。
- 修复：修正 README（逐目录列 manifest 提交，不要写“均由 1563f43”）；补一次**小规模多窗口 K>1 重构等价性**（当前只测 K=1），或明确论文中 G4 结果绑定到 `858a32b`–`150b652`，G5 绑定 `7999b06`/当前代码。

### 中

**M1. 测试集并非“只用一次”。** `experiments/README.md:79` 写“测试集只在训练结束后使用一次”，`g5_supplement_protocol.md:36` 也写“两个测试集只在训练完、选定后使用一次”；但实际上 G4 测试结果被 `g10_gantt_examples.py:24-53`（按测试集 IGA 结果挑中位案例画图）和 `g13_iga_retime_check.py:27-40`（按测试集记录抽样重跑）再次使用，G5 测试被 `g7/g8/g11/g12/g14` 反复读取。用于模型选择/调参的部分确实没有（G4/G5 模型只按验证集选），所以不构成训练泄漏；但“只用一次”的措辞不实，且 g10 按测试集结果选图例是 test-set 选择性使用。修复：改为“测试集只用于一次主假设评估；g10/g13 为事后诊断，不参与模型选择”，或把 g10/g13 抽到独立的新种子集。

**M2. IGA 计时差异未被完全消化，H3 实际没有做速度敏感性。**
- 证据：`g4_summary/findings.md:9-12` 说明第一次搜索与训练并行、IGA 慢约 1.75 倍，改用 `g4_search_curves_retimed`；`g5_summary/findings.md:28-32` 承认 G5 的 IGA n=100 速率（7.3k/s）低于 G4 retimed（11.7k/s）；`g13_iga_retime_check.py:44-48` + `g5_iga_retime_check/summary.json` 给出 G4 n=100 速度比中位 0.63、G5 0.99（同一实例单次运行可差约 1.6 倍）；`g14_g5_iga_speed_sensitivity.py:31-40` 只把 IGA 变快 f=1.3/1.6/2.0 重做检验，**H3 因 trace 只到 10 s 而不可能取到更晚点**（`g5_iga_retime_check/findings.md:60-61`），f>1 时 H3 的数值与 f=1 相同却仍被代码标成“holds/tested”（`g14:82-86`）。
- 影响：H1/H4/H5 对 IGA 变快 2 倍稳健（我核对了 `g5_iga_speed_sensitivity/tests.jsonl`：H1 Holm≤1.3e-6、H4≤5.9e-12、H5 仍 2/3 种子），但 **H3（RL+IGA 在 10 s 优于 IGA）没有速度敏感性证据**；G4 的 2 s 结论也只有一次计时（未对 GA/规则/CP-SAT 重测）。论文应把 H3 标为“时间预算内、单一计时环境下的结果”。
- 修复：对 G5 的 IGA 用 f<1（变慢）或在 10 s 之外延长 trace 才能检验 H3；至少 g14 不应把 H3 的 f>1 行计入“已检验”。

**M3. 主表用 GPU，搜索用 CPU；结论依赖硬件口径。**
- 证据：`g8_g4_policy_curves.py:89` 对 CPU 模型 `torch.set_num_threads(1)`；`g8:57-69` 的 GPU 点计入特征/环境步进；`g4_summary/findings.md:13-15,53-54` 明确 CPU 单实例推理反而更快（n=100 贪心 CPU 0.167 s vs GPU 0.315 s）。`g4_summary/curves.csv` n=100 t=0.2 s 的 RL(GPU) 覆盖 0、RL-cpu 覆盖 91.7%；G4 预注册 H1（t≤0.2 s）失败部分原因就是 GPU 启动开销。`docs/methods.md:230-233` 的“亚秒到秒级”若不写硬件会误导。
- 影响：主表“RL 优势区间”是 GPU 口径；换成 CPU 会把曲线左移（对 RL 更有利的早期点、更不利的长预算点）。G5 H1 在 1 s 仍成立（GPU），但论文应同时给 CPU 主表或明确“部署时用 CPU 推理”。
- 修复：把 RL-cpu 作为主口径之一并列报告；或在协议中预先固定推理硬件；注明训练时间不进入质量—时间预算（目前只在旁边描述）。

**M4. `g6` 默认参数与 G4 实际训练参数不同，1696 步无法从 summary 直接核出。**
- 证据：`g6_attention_policy.py:34-51` 默认 `rl_batch=32, eval_every=10, max_minutes=120, rl_steps=1000`；G4 实际 summary 的 `arguments` 是 `rl_batch=16, eval_every=20, max_minutes=240, rl_steps=100000`，`bc_epochs=8, rl_samples=16`，`elapsed_minutes=240.06`，history 最后一条是 step 1680/238.78 min；G5 修正记录（`g5_supplement_protocol.md:125-127,146-147`）才写明用 `--rl-steps 1696`。因此“8 轮 BC / 16 算例 ×16 采样”可直接从 summary/code 核实，**“1696 步”只能由协议/修正记录 + 240 min 截止推断，summary 没有记录最终 step 或 `rl_steps` 之外的停止原因**。
- 修复：在 `g6` summary 里记录 `completed_rl_steps`、停止原因（时间/步数）、每步耗时；把 G4/G5 的实际参数写进 manifest（目前 summary 有，但默认值容易让人误用）。

**M5. provenance 只哈希了 `src` + `_common` + 主脚本，未覆盖被 import 的分析模块。**
- 证据：`experiments/_common.py:67-85` 的 `provenance` 只收集 `src/fjsp_lab/**/*.py`、`_common.py`、当前脚本；而 `g12_g5_summary.py:27` 从 `g9_g4_summary` 导入 `value_at/policy_points`，`g14:18-19` 从 `g9/g12` 导入 `holm/one_sided`，`g13:24` 从 `g7` 导入 `run_instance`。修改 `g9` 的 `value_at` 会改变 `g12` 的结论，但 `g12` 的 manifest 源哈希不会变。
- 影响：归档的 source hash 不能完整绑定分析代码；复算时若 g9/g12 漂移，旧 summary 不能靠哈希发现。修复：provenance 递归收集脚本目录内被 import 的 `g*.py`（或用 `module.__file__`），或把共享分析函数移到 `src`/独立库并哈希。

**M6. 若干脚本硬编码归档路径 / import 时读历史文件，降低可移植与可复现性。**
- 证据：`g10_gantt_examples.py:25` 硬编码 `experiments/results/g4_search_curves_retimed/rows.jsonl`（不接受 CLI）；`g13_iga_retime_check.py:27-29` 硬编码 `RESULTS` 和四个目录；`g14_g5_iga_speed_sensitivity.py:26-28,102-109` 硬编码结果路径并在**模块 import 时**读 `g5_summary/summary.json` 得到 `H2_P`；`g4_comparison.py` 只按 `--cpsat/--policy/--meta` 工作、不哈希所有输入脚本。修复：全部走 `--...-dir` 参数并在 manifest 中哈希；避免 import 时产生 I/O。

**M7. 测试覆盖缺口（不是现有实现错误，但影响后续改动安全）。**
- 无“任意排列都合法”的穷举/属性测试（我本次外部补做，测试集里只有小规模“空间含最优”的检查 `test_maintenance_algorithms.py:225-236`，不是合法性覆盖）。
- 无“局部搜索计入评估次数”的直接测试；`test_maintenance_algorithms.py:85-91` 只检查 `evaluations<=600` 和同 seed 复现。
- 无 `g9`/`g12` 统计函数（Holm、单侧、配对符号）的单元测试；`g12` 的 Holm 实现正确但没被测试锁住。
- `build_periodic_instance` 的“slack<0 抛 ValueError”（`generator.py:199-201`）没有测试；`build_instance` 的 m=1、beta=0 也没有直接测试（我的边界实验覆盖了，但没进仓库）。
- PyTorch 测试在项目环境全部 skip（`test_learned_policies.py:96` 的 `importorskip`），本次 `pytest` 3 skipped 即这些；没有 CI/独立环境证据在本机可执行。
- 无 `g6` 训练、`g8` 推理、`g11` 热启的回归/冒烟测试（依赖 GPU 可理解，但至少应有小 CPU 冒烟）。
- 修复：加 1) 小实例随机排列 + 检查器属性测试；2) 预算计数精确断言（含 IGA 局部搜索）；3) Holm/单侧函数单测；4) 生成器负边界测试；5) CPU 小规模 g6→g8→g11 冒烟。

**M8. 文档与代码/结果不一致。**
- `experiments/results/README.md:3` 的“均由提交 1563f43”错误（见 S3）；`:11` 与后文/实际 G5 自相矛盾。
- `docs/methods.md` 4.5（`docs/methods.md:172-174`）说“n≥50 基本证不出”，但 G4 归档 346/576 次 CP-SAT 为 OPTIMAL，其中 n=100 有 109 次（绝大多数是 0 延期、tau=125 的松实例）；应改为“正延期的大实例基本证不出，0 延期松实例可证 0 最优”。
- `metaheuristics.py:13` 的“fixed: end <= f_ik”正确，但 `cpsat.py:9-13` 仍写“presolve may relax t_j=max(0,.)”，而实际模型用 `AddMaxEquality`（`:101-103`）精确表达；验收规则（`:39-50`）是保守的 bracketing，不会接受错值，但文档会让人误以为模型本身是松弛的。
- `g4_comparison.py` 是单窗口 G3A 表，名字与周期 G4 冲突；`experiments/README.md` 有说明，但脚本名/别名容易混。
- `docs/methods.md:196-197` 称特征含“MDD/ATC 值”；`sequence_env.py:194` 的 `mdd_key` 实际是 `max(d,finish)-min_tail`，不是 MDD 的 `max(d,t+p)-t`（`features.py:69` 才是）。网络可用 `start_delay` 组合回来，但特征名/文档“MDD 值”不精确。
- `docs/methods.md:5.1`（`:183-189`）说“回报 = −总延期”，但 `SequenceEnv` 没有 per-step reward 字段（`sequence_env.py:55-58,136-156`），只在 `g6` 用终止 T 构造 advantage；概念等价，文档应写“终止回报”。

### 轻

- `docs/methods.md:196` 说 20 个特征（`SEQUENCE_FEATURE_NAMES`，`sequence_env.py:35-40`）正确；`features.py` 是 19 个（`features.py:20-29`，`attention_policy.py:12` 也写 19）。用户/读者若把 `features.py` 当主方法特征会混淆，建议在 docs 明确“主方法用 sequence 的 20 维，action 环境是 19 维”。
- `metaheuristics.py:230-240` 的局部搜索注释写“first-improvement”，实际循环 20 次并接受 `candidate_value <= value`（含等值、非严格更优），不是“遇到第一个改进就停”。不影响公平计数，但实现/文档措辞不一致。
- `solve_metaheuristic` 的时间预算在 `TokenDecoder` 构造前开始（`metaheuristics.py:316-321`）；若 `g11` 的 `remaining` 只有 0.01 s 而 n=200 的 decoder 初始化超过它，`_genetic` 可能在首次评估前 `return`，随后 `best_sequence is None` 抛 `MetaheuristicError`，g11 没有回退到 warm best。归档运行未触发，但边界上会中断。
- `g14` 的 H3 在 f>1 时实际没有新数据（见 M2），输出仍带 `holds`；建议在代码里把 H3 的 f>1 行标 `not_testable`，不要只依赖 findings 说明。
- `maintenance/env.py:31` 让构造环境依赖 `maintenance.cpsat.numeric_domain_ok`（进而 import ortools）；`env`/`rules` 并不需要精确求解器。逻辑上能用，但分层不干净，且让 sequence env 与 action env 的数值域限制不对称（`sequence_env` 不检查）。
- `g4_summary` 复算时 H1 t=0.2 s 的 SA p 值与归档差最后 1 位（0.001593394586423243 vs 0.0015933945864232428，同一 scipy 1.17.1）；不影响结论，但说明“逐字节复现”只在 curves.csv 级别，p 值级别有浮点/平台末位差。
- `g4_gantt`/`g10` 选择“中位降低”案例时用了测试集 IGA 结果（见 M1）；图例数值不能当独立证据。
- `experiments/README.md` 的中文内容与当前 docs 有编码/路径旧引用（`g1 --long` 等），属文档维护问题。

---

## 四、算法正确性专项（逐项结论）

### 4.1 解码器（关键）——**结论：对满足实例合法性的输入，任意排列都解码为合法调度；本次未找到反例。**

实现：`metaheuristics.py:102-148`。
- 每个机器的状态是 `tails[i]`（最后占用结束时刻）与 `nxt[i]`（下一个未做窗口）；`limit` 固定模式 = `fixed_start`，联合模式 = `U-q`（`:84-88`）。
- 读工件（`:114-134`）：在每台机器上从 `(tails[i], nxt[i])` 起，若放上去会越过 `limit[i][k]`，就把窗口 k 的维护安排在 `_maintenance_start`（固定=fixed，联合=max(tail,L)，`:99-100`），推进 tail 与 k，直到工件可放下；在所有机器中选**完工最早**的一台。`inserted` 只在选中机器上提交（`:127-130`）。
- 读维护 token（`:135-142`）：`while nxt[machine] <= window` 依次插入该机器到目标窗口之前的全部窗口；每个窗口只做一次。
- 读完后的补维护（`:143-147`）：每台机器把 `nxt..K_i-1` 依次插入。
- `result()`（`:150-157`）用同一 decoder 生成 plan、独立重算并过 `require_feasible`。

不变量（足以保证合法性）：
1. 对每台机器，在窗口 `nxt` 未做前，`tails <= limit[nxt]`（初始 0 ≤ fixed_start/L；工件放置条件强制；维护后 tail = fixed_k+q ≤ U_k 或 max(tail,L)+q ≤ U_k，而 U_k ≤ L_{k+1} ≤ limit_{k+1}）。
2. 同机窗口互不重叠且 `L_{k+1} >= U_k`（`instance.py:81-84`），所以固定起点单调、维护区间不越 U。
3. token 处理保证每窗口只做一次；最后补维护在 `tails <= limit[nxt]` 下启动，因此 `start+q <= U`。
4. `result()` 用独立 `build_plan` + 检查器验证，且要求重算总延期与解码累计一致（`:154-157`）。

本次证据：324 个实例 × 2 模式 × 全排列/抽样共 1 026 720 次解码，0 次检查器拒绝、0 次总延期不一致；边界（m=1、零余量、三窗口邻接、`[0,2)` 宽等于维护时长、交期 0）2 164 次全合法；n=100/200 随机排列也合法。Pytest 的 `test_both_construction_spaces_contain_a_proven_optimum`（`:225-236`）在 tiny 上验证了“最优值可达”，我另验证了 tiny 上 **SequenceEnv 可达调度集合 = 全排列解码调度集合**（6 个 case/mode 组合均相等），支持“RL 与 IGA 搜索同一解码空间”的说法（至少这些实例上）。

限制：token 必须是 `0..n+W-1` 的排列；`decode` 本身不校验（内部调用都保证），公开的 `decoded_value` 若被外部传入非排列会得到缺任务/重复任务，交给检查器会拒绝。这不是“任意排列”的反例，但建议在 `decode` 入口加 permutation 校验或明确文档。

### 4.2 预算记账——**结论：没有发现“隐性多算/少算”；三者同预算公平。**

- 每次 `decode` 计数（`metaheuristics.py:107`）；`_Tracker.left = budget - evaluations`（`:212-215`），所有循环在 `left>0` 才继续（`:250-268, 288-295`）；局部搜索每个候选 `tracker.evaluate`（`:230-240`）；最终 `result()` 的 1 次 decode 被扣除（`:150-157`），且 `SearchOutcome.evaluations` 在扣减前读取（`:330-331`）。
- 本次实测：同一个 50×4 周期实例、预算 500、seed 3，GA/SA/IGA 的 `evaluations` 均为 500，`best_evaluation` 分别 499/23/488；没有超预算。测试 `test_maintenance_algorithms.py:85-91` 也检查 ≤600 和同 seed 复现。
- G3 用解码次数预算（`g3_metaheuristics.py:23,36`），G4/G5 用时间预算（`g7:34-39,54-67`；`g5` 同）；算法实现里时间/次数只通过 `Tracker.left` 统一切换，没有按算法分支改计数。SA 的 20 次“温度校准”也计入（`:276-280`）。
- 轻微边界：`g11` 的极小 `remaining` 可能导致 decoder 初始化耗尽时间后无评估，见“轻”第 3 条；不是计数作弊。

### 4.3 RL 实现——**结论：静态审查未发现梯度泄漏、基线/策略混用或掩码失效；符号正确。**

- 状态/候选：`SequenceEnv`（`sequence_env.py:92-171`）状态 = tails/nxt/unscheduled/sequence；候选 = 未排工件 + 每台有 pending 窗口的机器一个维护 token，≤ n+m（`:129-134`），线性增长成立。结束于“所有工件已放”，然后补维护（`:154-171`）；终局 plan 由 decoder 重算并过检查器。
- 掩码：`attention_policy.py:70-73` 用 `padding` bool 做 `src_key_padding_mask` 和 `masked_fill(-inf)`；`_batch` 正确构造 padding（`:93-100`）；`_run` 只把 `legal` 中的动作交给 env（`:113-126`）；softmax 前非法候选为 −inf。没有在全候选上 softmax 再 mask 的错误。
- 梯度：采样 `_run` 在 `torch.no_grad()` 下（`:108`），记录特征/选择；`reinforce_step` 重新 forward 并 `log_softmax.gather`，梯度只来自重算（`:243-246`），没有把采样图或旧 logits 带入。
- 基线与策略分离：`advantage = values - values.mean(dim=1)`（`:227-232`），`values` 是 detached float；baseline 不参与梯度；按 `teacher_tardiness+1` 缩放（`:230-231`，g6 传入 `:141-143`）。注意 baseline 是同一批 K=16 的均值（非留一），有很小偏差但属 POMO 常规做法。
- 符号：`g6` 的 `update` 是 `zero_grad → backward → clip → optimizer.step()`（`:109-114`）；Adam 做下降，而 loss 是 `advantage*logπ`，等价于对 `-advantage*logπ` 上升，即最小化 T，**方向正确**（与 scoring_policy 的 `baseline-sample` + `ascend` 一致，`scoring_policy.py:218-239`）。
- 学习率/裁剪：BC 1e-3、RL 1e-4、clip 1.0（`g6:39-51,112`），与 `docs/methods.md:209-226` 一致；BC 8 轮、RL 每批 16 算例 × 16 采样、每 20 步验证、共享均值基线，均与 `g4_attention_policy/summary.json` 的 `arguments` 和 `docs/methods.md` 5.3/5.4 一致。“1696 步”只能由 summary history 最后 1680/238.78 min + 240.06 min 截止 + G5 修正记录 `g5_supplement_protocol.md:146-147` 推断，summary 没有直接字段（见 M4）。
- 空间完备性：`sequence_env.py:1-6` 自己写“是否总含最优未证明，只在 tiny 穷举”；这与 `docs/methods.md:189-192` 的“RL/IGA 同空间”不冲突（同解码空间 ≠ 同最优保证）。agent 的空间（`env.py:3-7`）才有“可证包含最优”；主方法用的是 sequence，论文应继续保留这个限定。
- 未核：PyTorch 不在本环境，`test_learned_policies.py` 的 torch 测试（`:94-143`）3 项 skip；`g6` 训练、`g8` 推理、`g11` 热启本次只做了静态审查 + 归档 evidence，未实跑。

### 4.4 数据泄漏——**结论：种子划分和 g6 的验证集选择没有泄漏；但测试集复用与非独立性问题另计（S1/M1）。**

- `SPLITS`（`generator.py:146-151`）：train 10000–11999、validation 20000–20199、test 30000–30599、teacher_train 100000–119999；G4 train 200000–219999、validation 230000–230299；G4 测试种子 1001/1002（`:246-249`），G5 1003/1004（`:259`）。数值区间互不重叠；`test_maintenance_model.py:83-89,182-193` 也做了部分断言。
- `g6` 只读 train/validation，`checkpoint` 只对 `val_rows` 求贪心均值（`g6:88-107`）；我没有发现任何 test row 进入 g6。G4/G5 测试只在 `g7/g8` 之后被 `g9/g12` 读取；checkpoint 选择没有用测试。
- 但测试实例的**基础 p/u 流**由 `(n,seed)` 决定，因子组合共享（S1）；这是“非独立”，不是“训练泄漏”。G4/G5 的 H1–H5 把 192/576 个实例当独立样本，是更实质的问题。
- 测试集复用见 M1（g10/g13/g14；g14 只读归档，不再求解）。

### 4.5 精确方法——**结论：CP-SAT 模型精确、窗口必选且不重叠；枚举独立且穷尽；测试核对了二者。**

- CP-SAT：`cpsat.py:91-103` 每个任务每机一个 optional interval，`AddExactlyOne`；`:104-113` 每个窗口一个强制 `NewIntervalVar`（`start ∈ [L, U-q]`，固定模式 `start==fixed_start`），`AddNoOverlap` 含维护；`:114` minimize Σ `late`；`:101-103` `AddMaxEquality(late,[0,end-due])` 精确，不是松弛。`:130-148` 从解提取、独立重算、`check_objective_metadata` 要求 `0≤bound≤T≤objective`，OPTIMAL 时三者相等；随后过领域检查器。
- 枚举：`enumeration.py:25-44` 对每个维护起点组合、机器分配、工件顺序、维护插入“cut”位置做左移放置；`starts` 覆盖 `[L,U-q]` 所有整数；不可行的插入直接拒绝；`:64-65` 在 `itertools.product` 前检查状态预算。左移对总延期 WLOG，故枚举确实覆盖最优。
- 测试：`test_maintenance_algorithms.py:36-43` 在 16 单窗口 +16 周期 tiny、两模式下要求 CP-SAT=枚举；`:214-236` 另外用全排列/环境穷举核对 CP-SAT 最优；`:46-50` 固定/联合最优关系；`:60-66` 验收规则；`test_maintenance_model.py:155-167` 周期多窗口检查器。Pytest 全过。
- 我另从归档核验：G4 中双方都 OPTIMAL 的 161 对、G5 中 63 对，联合最优 ≤ 固定最优，0 违反；G4 CP-SAT 346/576 为 OPTIMAL，其余 FEASIBLE 且正延期大例基本没有证明最优，与“限时参考”定位一致。

### 4.6 元启发式——**结论：GA/SA/IGA 结构正确，同预算，随机可复现；只有两处轻量实现/注释偏差。**

- GA：OX（`metaheuristics.py:189-196`）保留父 A 一段、按父 B 顺序填其余，生成合法排列；锦标赛 min（`:226-228`）；精英 2 个直接进下一代（`:255-260`）；变异 swap/insert（`:171-186`）。
- SA：从 EDD+维护 token 最后的排列出发（`heuristic_sequences()[1]`，`:159-168,273`）；用 20 个正差样本标定 `T0=mean/ -ln(0.5)`（`:276-280`）；几何降温（`:286-295`）；接受准则 `delta<=0 or U<exp(-delta/T)`（`:292`）；有/无时间限制两种降温都实现。正确。
- IGA：初始种群放入 6 个启发式排列（`:159-168,245`），每代对最好子代做 20 次插入局部搜索（`:266-268,230-240`）；接受等值（见“轻”）。
- 预算：见 4.2；`test_maintenance_algorithms.py:95-101` 验证 IGA 停止点无关的搜索路径（g13 依赖此性质）。
- 随机性：`random.Random(seed)`，无全局随机；同 seed 同序列（测试 `:90-91`）；我重复运行也一致。

### 4.7 模型与数据（问题 1）——**结论：实现与文档一致；生成器确定；参数语义正确；边界处理基本到位。**

- 同质平行机/单工序/0 到达/每窗一次/窗口内完整维护：`instance.py:1-9,25-55,74-87`；`feasibility.py:3-14,117-141`；`to_fjsp_instance` 每个任务一道 op、所有机器同 p（`instance.py:126-129`）。
- 生成器确定性：`generator.py:46-49` SHA-256 + `random.Random`；`test_generator_is_deterministic...` 与 G3A 首例记录回归；G4/G5 grid 的 `g4_cases`/`grid_cases` 也由纯函数生成。
- `alpha`（维护时长占 W 或周期的百分比）、`beta`（窗口余量）、`tau`（交期系数）、`mode`（固定/联合）语义与文档一致：`build_instance:59-76`、`build_periodic_instance:185-207`；单窗口 `q=ceil(αW/100)`、`s=ceil(βW/100)`、`d=ceil(τWu/10000)`；周期 `q=ceil(αT/100)`、`s=min(ceil(βT/100), T-q-floor(25T/100))`、`L=kT+floor(vT/100)`、`U=L+q+s`。窗口互不重叠（`:81-84` 与 slack cap）。
- 边界：窗口宽度 < 维护时长由 `MaintenanceRequirement` 直接拒绝（`instance.py:50-51`）；m=1 由 `build_instance` 支持（`:64-65`），周期版也支持；交期极紧/极松在 `tau=75/125,u∈[50,150]` 内可产生 d<p 或 d>W；测试 `EDGE_CASES`（`:187-211`）覆盖 m=1、零余量、交期 0、1e12 时间；我的外部测试补了 m=1、beta=0、beta=75 等。
- 注意：生成器/训练集 m≥2（`SIZES`/`G4_SIZES`），m=1 只出现在人工边界例；单窗口生成器限制 m≤4（`build_instance:64-65`），周期生成器不限制；文档 START_HERE 已写。

---

## 五、可复现性专项

**能复现的（已实测）**
- **G5 汇总**：用当前 `g12` 从归档 G5 rows 复算，`curves.csv` 720 行、`hypotheses.csv` 20 行与归档逐字节一致；`summary.json` 的 `hypotheses/seed_spread/imitation_ablation/joint_vs_fixed` 完全一致。说明 `g9`+`g12` 分析代码与归档一致（G5 manifest 的 `source_sha256` 与当前源码 0 差异）。
- **G4 汇总**：用当前 `g9`、正确的输入顺序（`g4_search_curves` 主 + `g4_search_curves_retimed` 覆盖 IGA/SA）复算，`curves.csv` 360 行逐字节一致；H2/H3、exploratory 数值一致（H1 的 SA p 值有最后 1 位差异，见轻条）。所以 G4 的**分析与数字**可从归档 rows 复现。
- **数据/模型哈希**：`g4_teacher_data` 的 `train.jsonl`/`validation.jsonl` 与其 manifest、`g4_attention_policy/summary.json` 的 `data_manifest_sha256` 全部一致；`best.pt`/`best_bc.pt`（6 个）与 g8/g5 manifest 记录的 SHA-256 全部一致；G4 归档 rows 的 `inputs_sha256` 一致。
- **规则/生成器一致性**：随机抽 6 个 G4 case/mode（含 n=20/50/100、固定/联合），用当前代码重跑 EDD/MDD/ATC，总延期与归档行全部相同。
- **测试**：`pytest tests/maintenance` 77 passed, 3 skipped。

**不能/未验证的**
- **G4 的 rows 与模型不是当前代码生成**（S3）：当前源码与 G4 归档有 16 个 `src` 文件差异；G4 的 `g4_search_curves`/`g4_policy_curves`/`g4_attention_policy` 提交在 `957f3a8` 之前；`periodic_k1_regression` 只覆盖 K=1 单窗口。要真正重跑 G4 需在 `858a32b`/`be01963`/`d9e53c7` 上或补多窗口等价性测试。G4 的曲线/Search 值本身可能因重构语义变化而不一致；目前只能核到“分析复算一致”。
- **G5 的 rows/训练**：G5 manifest 源哈希与当前一致，说明行生成代码就是当前代码；但计时曲线依赖机器速度，我在本机没有重跑（且 RL 需要 GPU/PyTorch），所以只能核到分析与哈希，不能核运行数值可重复。Checkpoint 是归档哈希，不是重新训练。
- **RL 运行时行为**：无 PyTorch，attention policy 的 mask/softmax/gradient、g6 训练循环、g8 推理、g11 热启**未实跑**，只做了静态审查与归档 evidence 核验。
- **G7 的 576×10s 重跑**未做（成本约数小时），只做了小样本规则/IGA 路径一致性（g13 findings 已覆盖 IGA 路径）；G7 的 CP-SAT trace/model build 计时未重测。
- 单次运行速度波动约 1.6 倍（`g5_iga_retime_check/findings.md:35-43`），所有质量—时间结论都带这个不确定性；G4/G5 findings 已部分披露，但论文正文需保留。

**结论**：**G5 的“分析 + 结果”在当前代码上可重建；G4 的“分析”可重建、“行/模型”不能声称当前代码重建。** 论文若写“代码复现 G4/G5 全部结果”，不成立；应写“G4 结果归档于 `858a32b`–`150b652`，G5/分析在当前代码上复现”。

---

## 六、逐条回答审查问题（1–7 的落点）

1. **模型与数据**：一致；生成器确定；参数语义正确；窗口/边界处理到位（`instance.py:45-55,74-87`；`generator.py:46-76,185-207`；测试 `test_maintenance_model.py:36-89,139-193`）。**但测试集因子复用导致非独立样本**（S1）。训练/验证/测试种子区间数值上不重叠（lead 已知；`generator.py:146-151,250-260` 也支持）。
2. **解码器**：**声称成立**（对合法实例/排列）；证据：`metaheuristics.py:102-157` + 我的 1 026 720 次穷举/抽样 0 反例 + 不变量。没有找到“漏维护/维护越界/非法解”的反例。唯一限制是 `decode` 不校验输入是否为合法排列（内部保证）。
3. **元启发式**：GA/SA/IGA 正确（`metaheuristics.py:171-296`）；同预算、计数公平、无作弊（4.2；实测 500/500/500）；随机可复现（同 seed 同序列，测试 `:90-91`）。轻微：局部搜索注释“first-improvement”与“接受等值/循环 20 次”不完全一致。
4. **精确方法**：CP-SAT 精确、窗口必选且不重叠（`cpsat.py:91-148`）；枚举穷尽且独立（`enumeration.py:25-97`）；测试核对 `test_maintenance_algorithms.py:36-66,214-236`；我另核 G4/G5 双 OPTIMAL 对 0 违反。
5. **RL**：状态/候选/掩码/结束条件正确；候选 ≤ n+m；无梯度泄漏；共享基线分离；优势符号正确；8 轮 BC / 16×16 / 1696 步可从 summary+协议核实（1696 不是 summary 字段，见 M4）。数据泄漏：种子不重叠、g6 只用验证集；但测试集复用（M1）与非独立（S1）。**未实跑**（无 PyTorch）。
6. **实验公平性**：质量—时间曲线记录“t 之前最好解”基本正确（IGA/GA trace、CP-SAT incumbent、RL points；SA 每预算单独跑；`g9:38-60`、`g7:54-75`、`g8:57-69`）；启动开销/CPU-GPU 差异、CP-SAT trace 不含建模时间、RL 训练时间不计入，这些需在论文写清；统计：**g12 的 Holm 正确**（`g12:61-78`），**g9 没有 Holm/阈值**（M2/S2）；g10/g13 复用测试集（M1）。数字追踪示例：G4 n=100 t=1 s，RL mean gap 0.009308 vs IGA 0.028082，对应 `experiments/results/g4_summary/curves.csv` 的 `group=n100,budget=1.0,method=RL/IGA` 两行，可从 `g4_policy_curves/rows.jsonl` + `g4_search_curves(_retimed)/rows.jsonl` 逐实例复算（我复算值 0.009308 完全一致）；G5 n=100 t=1 s，RL_s0 0.018198 vs IGA 0.305770，对应 `g5_summary/curves.csv` 与 `hypotheses.csv` 的 H1 seed0 行，我用当前 `g12` 复算逐字节一致。
7. **可维护性**：模块职责清楚、注释/类型总体好；存在三套维护插入语义（`TokenDecoder`、`SequenceEnv`、`ParallelMaintenanceEnv`）和两套特征（19/20 维）的重复，靠测试交叉核对；`env` 依赖 `cpsat` 分层不干净；`g10/g13/g14` 硬编码路径、`g14` import 时读文件；`g4_comparison` 命名易混；`results/README` 有过时声明；测试缺解码器合法性/预算计数/Holm/生成器负边界/RL 冒烟（M6/M7/M8）。

---

## 七、无法判断 / 未覆盖

- **PyTorch 运行时**：本环境无 torch，`test_learned_policies.py` 的 3 项 skip；`g6/g8/g11` 未实跑，只能静态审查 + 归档哈希/参数核验。因此 RL 的**数值行为**（GPU bf16、mask 在真实 forward 中是否产生 NaN、训练曲线是否可复现）未独立验证。
- **G4 行级重跑**：未在 `858a32b`/`be01963`/`d9e53c7` 上重跑或补多窗口等价性；只核到分析复算、哈希、规则/生成器小样本。要确认 G4 数值可复现，需要多窗口 K>1 重构等价性测试。
- **G7 的 576×10 s 搜索重跑、G8 的 GPU 推理计时、G11 的热启 IGA 重跑**：成本/环境限制，未做。
- **g1–g4 单窗口归档结果**（G3A/G3B）：本次未重跑；`g4_comparison`/`g2` 只做了静态审查，未用归档输入重算。
- **枚举在 n=5/m=3/多窗口**的穷尽性压力测试：代码支持，但测试只到 n≤3、m≤2、K≤2；我的随机检查未覆盖 n=5,m=3 的大状态。
- **长期硬件/功耗波动**：所有计时结论依赖一台笔记本和当时负载；G4/G5 已披露部分，未做多机器复测。
- **`docs/models/graduation_model.md` 第 2 章草稿**（`thesis_ch2_model_zh.tex`）不在本次范围，未核对 NP 难/证明。
