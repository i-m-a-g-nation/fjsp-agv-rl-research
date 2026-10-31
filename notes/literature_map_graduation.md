# 毕设文献地图：平行机 + 维护 + 总延期 + 学习型派工（2026-10-30）

本页回答两个问题：毕设目前的模型和方法，在文献里处于什么位置？哪些创新点有依据、可以主张？

**阅读状态**：A1、A2、A3、B1、B2、D1、D2 七篇已通读全文（用户经学校图书馆获取，PDF 存放在被 git 忽略的 `papers/auto_fetched/`，不进仓库）。其余条目仍只来自摘要或检索摘要，表中标"摘要"。写进论文之前，摘要条目必须读原文核对。

## 本项目在做什么

- **问题**：同质平行机，每个工件一道工序、0 时刻到达；每台机器在给定时间窗内必须做一次维护（闲置机器也要做）。比较两种做法：维护开始时刻预先固定（fixed），或和生产一起决定（joint）。目标是最小化总延期 ΣT_j。
- **参考解**：CP-SAT（`solver_v2`），n=8 时能证得最优。
- **学习型方法**：
  - 为每个合法动作单独算特征，用一个共享的小网络打分，网络与实例规模无关；
  - 先模仿逐实例最好的规则（EDD/MDD/ATC），再用 REINFORCE 微调，基线取贪心回放；
  - 推理时可以多次采样再挑最好。
- **已有证据**：exp_035（G3A）、exp_036/037（策略与规则）、exp_038（G3B）。

## 核实规则

- **DOI**：通过 Crossref 元数据核对了标题、作者、期刊、年份、卷期页；已读全文的七篇又按 PDF 首页核对了作者全名。
- **会议论文**：通过 arXiv 或会议官方页面核对。
- **"要点"一栏**：标"全文"的来自通读原文；标"摘要"的只来自摘要或检索摘要。
- **检索局限**：只检索了英文文献，没有检索中文数据库（CNKI 等）。所以凡是"没找到"，都只能说"本次检索没有发现"，不能写成"不存在"。

## A. 问题本身：带维护或可用性约束的平行机调度（非学习方法）

| 编号 | 文献 | 要点 | 与本项目的关系 |
|---|---|---|---|
| A1 | Ma, Chu, Zuo (2010), *C&IE* 58(2):199–211 | **全文**。确定性机器不可用时段调度的综述，按单机、平行机、流水车间等分类；区分可恢复、不可恢复、半可恢复三种中断方式；指出已有结果几乎都是离线问题，在线版本研究很少 | 背景和分类用。按它的术语，本项目是"不可恢复（nonresumable）、离线"的情形 |
| A2 | Lee, Chen (2000), *Naval Research Logistics* 47(2):145–165 | **全文**。m 台同质平行机，每台机器在 [0, T] 内必须维护**恰好一次**，维护时长固定，工件不可恢复；目标是总加权完工时间 ΣwC。分两种情形：维护可同时进行（independent）和同一时刻只能维护一台（dependent）。证明即使等权 ΣC 两种情形也都是 NP 难；用列生成加分支定界求精确解，n ≤ 40、m ∈ {2,4,6,8}。动机来自半导体厂：机器空等维修人员、而工件在排队 | **本项目模型的直接来源**。本项目的 A3（每机恰一次必需维护）、A5（不同机器可同时维护）就是它的 independent 情形。差别：它只有截止时刻 T（窗口为 [0, T]），本项目是一般窗口 [L, U)；目标是 ΣwC 而不是 ΣT；它没有"固定 vs 联合"的对照 |
| A3 | Lee, Kim (2015), *JORS* 66(9):1542–1554 | **全文**。两台同质平行机，每台机器加工完固定数目 w 个工件后必须维护，目标 ΣT，分支定界精确算法。实验：n ∈ {16,20,24,28}，共 720 个实例，单实例时限 3600 秒；n=24 平均 75 秒，n=28 平均 939 秒，有 5 个实例 3600 秒内没解出；初始上界启发式 KPM-PI 耗时 < 0.01 秒，平均偏离最优 7%–11% | 同一目标（ΣT）的精确方法，说明 **n≈24–28 就是这类问题精确求解的边界**，和本项目 CP-SAT 在 n=24 上 60 秒仍证不出最优的现象一致。维护触发方式不同（按工件数，不是时间窗）。它也给出了 P‖ΣT 的 NP 难性依据（引 Du & Leung 1990） |
| A4 | Geurtsen, Adan, Akçay (2023 在线 / 2024), *Flexible Services and Manufacturing Journal* 36(3):1046–1079 | **摘要**。不相关平行机加换型时间，维护与生产集成调度；摘要称灵活维护比固定维护能改善总延期 | 和 G3A 的"固定 vs 联合"直接相关。它报告的改善幅度很小（检索摘要称总延期约 2%），本项目 n=8 证得最优的降幅是 30%–56%，**需要读全文解释差异**（开放获取，我可以自己读） |

## B. 经典总延期派工规则

| 编号 | 文献 | 要点 | 与本项目的关系 |
|---|---|---|---|
| B1 | Vepsalainen, Morton (1987), *Management Science* 33(8):1035–1047 | **全文（扫描件，按页面图像读）**。ATC 单阶段公式（原文式 7）：优先级 = (v_i/p_i)·exp(−[d_i − p_i − t]⁺ / (k·p̄))，取最大者。p̄ 是**排队工件**的平均加工时间，脚注 5 允许用长期平均或标准加工时间代替。推荐 k：静态流水车间 k=2，动态作业车间 k=3，一般在 1.5–4.5 之间。脚注 3：等权时，其成对交换条件退化为 MDD | `dispatch_rules.py` 的 ATC 与式 7（v=1）一致；p̄ 用全部任务的平均加工时间，属于脚注 5 允许的做法，论文中要写明。**但默认 k=1 不在推荐区间内**，见下文"核对发现" |
| B2 | Baker, Bertrand (1982), *Journal of Operations Management* 3:37–42 | **全文**。修正交期 d'_j(t) = max(d_j, t + p_j)，选最小者（原文式 4）；交期宽松时等同 EDD，全部注定延期时等同 SPT。实验是动态单机仿真，目标为平均延期 | `dispatch_rules.py` 的 MDD 与式 4 一致。把 t 取为该机器的空闲时刻、推广到平行机，是本项目的做法，论文中要说明 |
| B3 | Baker, Kanet (1983), *Journal of Operations Management* 4:11–22 | **仅元数据**。用修正交期做作业车间调度 | MDD 的后续发展，只引用不必读 |

## C. 深度强化学习做平行机调度（以延期为目标）

| 编号 | 文献 | 要点 | 与本项目的关系 |
|---|---|---|---|
| C1 | Paeng, Park, Park (2021), *IEEE Access* 9:101390–101401 | **摘要**。带族换型的平行机，最小化延期；参数共享的网络；摘要称优于元启发式、规则和其他 RL 方法 | 最接近的 DRL 平行机延期工作之一，但没有维护。参数共享的思路和本项目"共享打分网络"相近，**必须对比并说明差异**（开放获取） |
| C2 | Li, Lang, Hong, Reggelin (2023 在线 / 2024), *Journal of Intelligent Manufacturing* 35(3):1107–1140 | **摘要**。平行机加交期和族换型，两阶段 RNN，PPO 训练；摘要称延期低于对照方法 | 同样没有维护；PPO 是本项目没有采用的路线（开放获取） |

## D. 强化学习做生产与维护集成调度

| 编号 | 文献 | 要点 | 与本项目的关系 |
|---|---|---|---|
| D1 | Wang, Zhang, Zhang, Xiang, Jin, Li (2024), *Journal of Manufacturing Systems* 77:946–961 | **全文**。流程工业的动态平行机：订单按指数间隔到达、有多种规格，订单内任务间有准备时间、换规格有切换时间；机器可靠性按 Weibull 退化，低于阈值 0.9 会故障。维护是**可选的自适应动作**，次数不限、没有时间窗。**双目标**：最大化平均可靠性、最小化总成本（准备 + 切换 + 维修 + 维护），合成一个奖励。方法：带动作掩码的 Double DQN，动作 = n 个订单 + 1 个维护；另用 Actor-Critic 加自模仿学习自动选状态特征。实验：m ∈ {5,10,20}、订单 50–150，共 9 个实例，每个实例一个数值；对照为消融、周期/灵活维护策略、EDD/SPT/FIFO/ATC、DDPG、SAC。**没有精确解或下界对照，没有报告重复次数和显著性检验**；模型描述里没有交期，也不以延期为目标 | **最直接的竞争工作，但问题和本项目不同**：目标不是总延期，维护不是"窗口内必需一次"，没有"固定 vs 联合"的对照。共同点是平行机 + 维护 + DRL + 动作掩码 + 拿派工规则做对照 |
| D2 | Hu, Wang, Tang, Kanazawa, Gupta, Farahat (2023), *C&IE* 185:109631 | **全文**。多台机器组成的车队（例：矿用卡车）按时间段分配生产时长并决定预防性维护；机器退化影响生产成本，退化到一定程度会故障；目标是有限时域内的总业务收益（产出收入减生产和维护成本），约束是每个时间段的产量需求。方法：集中式多智能体 Actor-Critic，用需求约束的先验知识确定生产决策（KERL）；确定性和随机两个案例，对照三种基线（含 A2C） | 也是生产 + 维护集成的 RL，但**没有工件排序和交期**，是按时间段分配产能的问题。只作背景引用 |

## E. 方法谱系（本项目算法的依据）

| 编号 | 文献 | 本项目用到的部分 |
|---|---|---|
| E1 | Williams (1992), *Machine Learning* 8:229–256 | REINFORCE 策略梯度 |
| E2 | Kool, van Hoof, Welling (2019), ICLR. arXiv:1803.08475 | 用贪心回放作基线（本项目的自评基线）；采样解码 |
| E3 | Kwon et al. (2020), NeurIPS. arXiv:2010.16011 | 多次回放、多条起点（POMO）；本项目"多次采样挑最好"的同类做法 |
| E4 | Zhang et al. (2020), NeurIPS（Advances in NeurIPS 33）. arXiv:2010.12367 | 与规模无关的派工策略（GNN 编码）；本项目用逐动作特征代替 GNN 实现规模无关 |

"先模仿规则、再用 RL 微调"在调度和派工领域已有先例（检索摘要提到 DAgger 式学习派工规则、先用 EDD 预训练再用 DRL 微调等），**不能把它当成本项目的方法创新**。具体条目还没核实到 DOI，所以没有列进表格。

## 核对发现（读全文后对项目的影响）

1. **研究空白在英文文献范围内成立。** D1 的目标是可靠性加成本、维护是不限次数的可选动作；A2 是同样的"每机窗口内维护一次"结构，但目标是 ΣwC、方法是精确算法；A3 目标是 ΣT，但维护按工件数触发、只有两台机器。本次检索仍没有发现"窗口内必需维护 + 总延期 + 固定/联合对照 + 学习型派工"同时出现的工作。
2. **模型有经典出处，可以直接引用。** 每机恰一次、时长固定、可同时维护、工件不可恢复，这几条都和 A2 的 independent 情形一致；本项目把截止时刻推广成一般窗口 [L, U)、目标换成 ΣT。
3. **NP 难性可以论证，但要自己写一段。** A3 引 Du & Leung (1990) 说明 P2‖ΣT 已是 NP 难。把每台机器的维护窗口放到所有加工之后（例如 L_i = Σp_j，U_i = L_i + q_i），维护就不影响生产，本问题即退化为 Pm‖ΣT，所以本问题也是 NP 难。这段归约需要写进论文并由导师确认，A3 和 Du & Leung 都要引用。
4. **CP-SAT 在 n=24 证不出最优是正常现象。** A3 的专用分支定界在两台机器、n=28 时平均也要 939 秒，还有实例 1 小时没解出。这可以作为本项目只在 n=8 主张"证得最优"、在 n=24 只报告限时参考解的文献依据。
5. **派工规则的定义核对：**
   - MDD 与 B2 式 4 完全一致；推广到平行机时 t 取该机器空闲时刻，属本项目的做法，需写明。
   - ATC 与 B1 式 7 一致（等权），p̄ 用全部任务的平均加工时间，原文脚注 5 允许。
   - 默认 ATC_K = 1.0 不在 B1 推荐的 1.5–4.5 区间内（静态问题推荐 k = 2）。**已用 exp_039 复核**：在 exp_037 测试集和 G3A 网格上，ATC k=2 比 k=1 平均差 14.1% 和 16.3%，k=3 更差；三规则取最好换成 k=2 也变差。所以 exp_036–038 的对照比文献默认设置更严格，已有结论成立。论文正文继续用 k=1，并引用 exp_039 说明理由；k=1 是事先定的默认值，不能说成调过的最优值。
6. **评估严谨性是可以主张的差异。** D1 每个规模只报告一个数值，没有精确解或下界、没有重复和显著性检验。本项目有 n=8 的证得最优参考、等回放次数对照和配对 Wilcoxon 检验，这一点在候选创新 I1 中可以有依据地写。

## 空白分析

本次检索没有发现同时满足以下全部条件的工作：

1. 同质平行机，每台机器在时间窗内必须维护一次；
2. 维护时刻固定和联合决定两种方式放在同一个模型里对照；
3. 目标是总延期；
4. 用学习型派工策略求解，并且在相同回放次数下和规则组合、在给定时限下和 CP-SAT 比较。

逐项对照已读全文的最接近工作：

| 条件 | A2 | A3 | D1 | 本项目 |
|---|---|---|---|---|
| 平行机，每机必需维护一次 | 有（[0, T] 内） | 按工件数周期维护 | 没有（维护可选、不限次） | 有（[L, U) 内） |
| 固定 vs 联合维护对照 | 没有 | 没有 | 和周期/灵活维护策略对照 | 有 |
| 目标总延期 | ΣwC | ΣT | 可靠性 + 成本 | ΣT |
| 学习型方法 | 没有 | 没有 | Double DQN | 共享打分网络 + REINFORCE |
| 精确解或下界对照 | 本身是精确算法 | 本身是精确算法 | 没有 | CP-SAT（n=8 证得最优） |

C1、C2（DRL 平行机延期，没有维护）和 A4（灵活 vs 固定维护，非学习方法）仍只读了摘要，读全文后再补进上表。

## 候选创新点（按证据强弱排序）

| 编号 | 候选 | 已有证据 | 风险 / 还需要什么 |
|---|---|---|---|
| I1 | **评估方法**：在相同回放次数下和规则组合比较、在给定时限下和 CP-SAT 比较，并据此把学习型方法定位为"快速近似方法" | exp_037/038：只做一次贪心时策略和三规则组合持平，多采样后超过；CP-SAT 60 秒在 n=24 上好 6%–11%。D1 这类最接近的 DRL 工作没有精确参考和显著性检验 | 属于方法论上的严谨，不是新算法；需要说明为什么这种比较方式会改变结论。ATC 的 k 值已由 exp_039 复核（核对发现 5） |
| I2 | **维护时间窗下的联合决策价值**：在 n=8 证得最优的实例上量化联合决定维护时机带来的总延期降低（30%–56%），以及它对固定策略的依赖 | exp_035；A2 从实际生产角度说明了联合安排的动机 | 方向在理论上是预知的（联合是固定的松弛），价值在于量化；需要和 A4 报告的约 2% 对照并解释差异 |
| I3 | **面向维护的逐动作特征加共享打分网络**：EDD/MDD/ATC 都是这个策略类的特例，模仿规则后再用 RL 改进 | exp_036–038：优于单一规则，同等回放次数下优于规则组合 | 和 C1 的参数共享、E4 的规模无关思想相近；创新只能定位为"在维护约束问题上的设计与验证"，强度中等 |
| I4 | **动态重调度下的速度优势**（尚未做） | 无。A3 的启发式（< 0.01 秒、偏离最优 7%–11%）说明"毫秒级近似 + 慢速精确"是这个领域常见的定位 | 需要新实验：在 Phase 2A 的动态事件下，比较策略（毫秒级）和 CP-SAT（秒到分钟级）的响应质量。这是把"快"变成实际优势的关键 |

## 还要读的（建议顺序）

1. **C1**（Paeng et al., 2021）：参数共享 DRL 和延期目标，和本项目方法最接近。开放获取，我可以读。
2. **A4**（Geurtsen et al., 2023/2024）：解释固定与灵活维护收益的差异。开放获取，我可以读。
3. **C2**（Li et al., 2023/2024）：PPO 路线的对照。开放获取。
4. **中文文献**：CNKI 检索"平行机 维护 延期""生产 维护 协同 调度 强化学习"，需要你用校园网检索，或把检索结果导出给我。

之后需要导师确认的：核对发现 3（NP 难归约）、I1–I4 的取舍。

## 参考文献（按编号）

- [A1] Ma, Y., Chu, C., Zuo, C. (2010). A survey of scheduling with deterministic machine availability constraints. *Computers & Industrial Engineering*, 58(2), 199–211. https://doi.org/10.1016/j.cie.2009.04.014
- [A2] Lee, C.-Y., Chen, Z.-L. (2000). Scheduling jobs and maintenance activities on parallel machines. *Naval Research Logistics*, 47(2), 145–165. https://doi.org/10.1002/(SICI)1520-6750(200003)47:2<145::AID-NAV5>3.0.CO;2-3
- [A3] Lee, J.-Y., Kim, Y.-D. (2015). A branch and bound algorithm to minimize total tardiness of jobs in a two identical-parallel-machine scheduling problem with a machine availability constraint. *Journal of the Operational Research Society*, 66(9), 1542–1554. https://doi.org/10.1057/jors.2014.122
- [A4] Geurtsen, Adan, Akçay (2024). Integrated maintenance and production scheduling for unrelated parallel machines with setup times. *Flexible Services and Manufacturing Journal*, 36(3), 1046–1079. https://doi.org/10.1007/s10696-023-09511-z
- [B1] Vepsalainen, A. P. J., Morton, T. E. (1987). Priority rules for job shops with weighted tardiness costs. *Management Science*, 33(8), 1035–1047. https://doi.org/10.1287/mnsc.33.8.1035
- [B2] Baker, K. R., Bertrand, J. W. M. (1982). A dynamic priority rule for scheduling against due-dates. *Journal of Operations Management*, 3(1), 37–42. https://doi.org/10.1016/0272-6963(82)90020-1
- [B3] Baker, Kanet (1983). Job shop scheduling with modified due dates. *Journal of Operations Management*, 4, 11–22. https://doi.org/10.1016/0272-6963(83)90022-0
- [C1] Paeng, B., Park, I.-B., Park, J. (2021). Deep reinforcement learning for minimizing tardiness in parallel machine scheduling with sequence dependent family setups. *IEEE Access*, 9, 101390–101401. https://doi.org/10.1109/ACCESS.2021.3097254
- [C2] Li, Lang, Hong, Reggelin (2024). A two-stage RNN-based deep reinforcement learning approach for solving the parallel machine scheduling problem with due dates and family setups. *Journal of Intelligent Manufacturing*, 35(3), 1107–1140. https://doi.org/10.1007/s10845-023-02094-4
- [D1] Wang, M., Zhang, J., Zhang, P., Xiang, W., Jin, M., Li, H. (2024). Generative deep reinforcement learning method for dynamic parallel machines scheduling with adaptive maintenance activities. *Journal of Manufacturing Systems*, 77, 946–961. https://doi.org/10.1016/j.jmsy.2024.11.004
- [D2] Hu, J., Wang, H., Tang, H.-K., Kanazawa, T., Gupta, C., Farahat, A. (2023). Knowledge-enhanced reinforcement learning for multi-machine integrated production and maintenance scheduling. *Computers & Industrial Engineering*, 185, 109631. https://doi.org/10.1016/j.cie.2023.109631
- [E1] Williams, R. J. (1992). Simple statistical gradient-following algorithms for connectionist reinforcement learning. *Machine Learning*, 8, 229–256. https://doi.org/10.1007/BF00992696
- [E2] Kool, W., van Hoof, H., Welling, M. (2019). Attention, learn to solve routing problems! ICLR 2019. https://arxiv.org/abs/1803.08475
- [E3] Kwon, Y.-D., Choo, J., Kim, B., Yoon, I., Gwon, Y., Min, S. (2020). POMO: Policy optimization with multiple optima for reinforcement learning. NeurIPS 2020. https://arxiv.org/abs/2010.16011
- [E4] Zhang, C., Song, W., Cao, Z., Zhang, J., Tan, P. S., Xu, C. (2020). Learning to dispatch for job shop scheduling via deep reinforcement learning. NeurIPS 2020. https://arxiv.org/abs/2010.12367

A1–A3、B1、B2、D1、D2 的作者名按 PDF 首页核对。其余只写姓的条目是 Crossref 核对过的姓，首字母没有核实。正式引用前，请以出版方页面为准。
