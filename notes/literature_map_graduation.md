# 毕设文献地图：平行机 + 维护 + 总延期 + 学习型派工（2026-10-30）

本页回答两个问题：毕设目前的模型和方法，在文献里处于什么位置？哪些创新点有依据、可以主张？

它是检索整理，不是精读结论。表格里的"要点"都来自摘要或检索摘要；只看到元数据的条目会明确标出。写进论文之前，必须读原文核对。

## 本项目在做什么

- **问题**：同质平行机，每个工件一道工序、0 时刻到达；每台机器在给定时间窗内必须做一次维护（闲置机器也要做）。比较两种做法：维护开始时刻预先固定（fixed），或和生产一起决定（joint）。目标是最小化总延期 ΣT_j。
- **参考解**：CP-SAT（`solver_v2`），n=8 时能证得最优。
- **学习型方法**：
  - 为每个合法动作单独算特征，用一个共享的小网络打分，网络与实例规模无关；
  - 先模仿逐实例最好的规则（EDD/MDD/ATC），再用 REINFORCE 微调，基线取贪心回放；
  - 推理时可以多次采样再挑最好。
- **已有证据**：exp_035（G3A）、exp_036/037（策略与规则）、exp_038（G3B）。

## 核实规则

- **DOI**：通过 Crossref 元数据核对了标题、作者、期刊、年份、卷期页。
- **会议论文**：通过 arXiv 或会议官方页面核对。
- **"要点"一栏**：只来自摘要或检索摘要，没有读全文。标"仅元数据"的条目连摘要都没看到。
- **检索局限**：只检索了英文文献，没有检索中文数据库（CNKI 等）。所以凡是"没找到"，都只能说"本次检索没有发现"，不能写成"不存在"。

## A. 问题本身：带维护或可用性约束的平行机调度（非学习方法）

| 编号 | 文献 | 要点 | 与本项目的关系 |
|---|---|---|---|
| A1 | Ma, Chu, Zuo (2010), *Computers & Industrial Engineering* 58(2):199–211. DOI 10.1016/j.cie.2009.04.014 | 综述：机器有不可用时段（常由预防性维护引起）的调度，覆盖单机、平行机、流水车间等的复杂度与算法 | 问题背景和分类的入口文献 |
| A2 | Lee, Chen (2000), *Naval Research Logistics* 47(2):145–165. DOI 10.1002/(SICI)1520-6750(200003)47:2<145::AID-NAV5>3.0.CO;2-3 | 平行机上同时安排工件和维护活动（仅元数据；目标函数和维护规则待读全文） | 题目和本项目"每机维护 + 生产联合安排"最接近，**优先精读** |
| A3 | Lee, Kim (2015), *Journal of the Operational Research Society* 66(9):1542–1554. DOI 10.1057/jors.2014.122 | 两台同质平行机、带机器可用性约束，最小化总延期的分支定界精确算法 | 同一目标下的精确方法，可作为精确解对照的文献依据 |
| A4 | Geurtsen, Adan, Akçay (2023 在线 / 2024), *Flexible Services and Manufacturing Journal* 36(3):1046–1079. DOI 10.1007/s10696-023-09511-z | 不相关平行机加换型时间，维护与生产集成调度；摘要称灵活维护比固定维护能改善总延期 | 和 G3A 的"固定 vs 联合"直接相关。它报告的改善幅度很小（检索摘要称总延期约 2%），本项目 n=8 证得最优的降幅是 30%–56%，**需要读全文解释差异**（机器类型、换型、维护模型、实例生成都不同） |

## B. 经典总延期派工规则

| 编号 | 文献 | 要点 | 与本项目的关系 |
|---|---|---|---|
| B1 | Vepsalainen, Morton (1987), *Management Science* 33(8):1035–1047. DOI 10.1287/mnsc.33.8.1035 | 加权延期的优先级规则，后来称为 ATC（Apparent Tardiness Cost） | `dispatch_rules.py` 中 ATC 的出处 |
| B2 | Baker, Bertrand (1982), *Journal of Operations Management* 3:37–42. DOI 10.1016/0272-6963(82)90020-1 | 面向交期的动态优先级规则（修正交期思想） | MDD 规则的出处 |
| B3 | Baker, Kanet (1983), *Journal of Operations Management* 4:11–22. DOI 10.1016/0272-6963(83)90022-0 | 用修正交期做作业车间调度 | MDD 的后续发展 |

## C. 深度强化学习做平行机调度（以延期为目标）

| 编号 | 文献 | 要点 | 与本项目的关系 |
|---|---|---|---|
| C1 | Paeng, Park, Park (2021), *IEEE Access* 9:101390–101401. DOI 10.1109/ACCESS.2021.3097254 | 带族换型的平行机，最小化延期；参数共享的网络；摘要称优于元启发式、规则和其他 RL 方法 | 最接近的 DRL 平行机延期工作之一，但没有维护。参数共享的思路和本项目"共享打分网络"相近，**必须对比并说明差异** |
| C2 | Li, Lang, Hong, Reggelin (2023 在线 / 2024), *Journal of Intelligent Manufacturing* 35(3):1107–1140. DOI 10.1007/s10845-023-02094-4 | 平行机加交期和族换型，两阶段 RNN，PPO 训练；摘要称延期低于对照方法 | 同样没有维护；PPO 是本项目没有采用的路线 |

## D. 强化学习做生产与维护集成调度

| 编号 | 文献 | 要点 | 与本项目的关系 |
|---|---|---|---|
| D1 | Wang, Zhang, Zhang, Xiang, Jin, Li (2024), *Journal of Manufacturing Systems* 77:946–961. DOI 10.1016/j.jmsy.2024.11.004 | 动态平行机加自适应维护，生成式 DRL（仅元数据：关键词含 double DQN、自模仿学习、生产成本最小化；目标和基线待核） | **目前找到的最直接竞争工作**，问题、目标和维护模型都要读全文对比 |
| D2 | Hu, Wang, Tang, Kanazawa, Gupta, Farahat (2023), *Computers & Industrial Engineering* 185:109631. DOI 10.1016/j.cie.2023.109631 | 多机生产与维护集成调度，结合知识的 RL（KERL）；按 MDP 建模 | 集成调度的 RL 路线；目标和机器模型与本项目不同，待核 |

## E. 方法谱系（本项目算法的依据）

| 编号 | 文献 | 本项目用到的部分 |
|---|---|---|
| E1 | Williams (1992), *Machine Learning* 8:229–256. DOI 10.1007/BF00992696 | REINFORCE 策略梯度 |
| E2 | Kool, van Hoof, Welling (2019), ICLR. arXiv:1803.08475 | 用贪心回放作基线（本项目的自评基线）；采样解码 |
| E3 | Kwon et al. (2020), NeurIPS. arXiv:2010.16011 | 多次回放、多条起点（POMO）；本项目"多次采样挑最好"的同类做法 |
| E4 | Zhang et al. (2020), NeurIPS（Advances in NeurIPS 33）. arXiv:2010.12367 | 与规模无关的派工策略（GNN 编码）；本项目用逐动作特征代替 GNN 实现规模无关 |

"先模仿规则、再用 RL 微调"在调度和派工领域已有先例（检索摘要提到 DAgger 式学习派工规则、先用 EDD 预训练再用 DRL 微调等），**不能把它当成本项目的方法创新**。具体条目还没核实到 DOI，所以没有列进表格。

## 空白分析

本次检索没有发现同时满足以下全部条件的工作：

1. 同质平行机，每台机器在时间窗内必须维护一次；
2. 维护时刻固定和联合决定两种方式放在同一个模型里对照；
3. 目标是总延期；
4. 用学习型派工策略求解，并且在相同回放次数下和规则组合、在给定时限下和 CP-SAT 比较。

最接近的是 D1（动态平行机加维护加 DRL，但目标和维护模型待核）、A2（平行机加维护的联合安排，非学习方法）和 C1/C2（DRL 平行机延期，没有维护）。

**D1 和 A2 的全文是确认这个空白的关键。**

## 候选创新点（按证据强弱排序）

| 编号 | 候选 | 已有证据 | 风险 / 还需要什么 |
|---|---|---|---|
| I1 | **评估方法**：在相同回放次数下和规则组合比较、在给定时限下和 CP-SAT 比较，并据此把学习型方法定位为"快速近似方法" | exp_037/038：只做一次贪心时策略和三规则组合持平，多采样后超过；CP-SAT 60 秒在 n=24 上好 6%–11% | 属于方法论上的严谨，不是新算法；需要说明为什么这种比较方式会改变结论 |
| I2 | **维护时间窗下的联合决策价值**：在 n=8 证得最优的实例上量化联合决定维护时机带来的总延期降低（30%–56%），以及它对固定策略的依赖 | exp_035 | 方向在理论上是预知的（联合是固定的松弛），价值在于量化；需要和 A4 报告的约 2% 对照并解释差异 |
| I3 | **面向维护的逐动作特征加共享打分网络**：EDD/MDD/ATC 都是这个策略类的特例，模仿规则后再用 RL 改进 | exp_036–038：优于单一规则，同等回放次数下优于规则组合 | 和 C1 的参数共享、E4 的规模无关思想相近；创新只能定位为"在维护约束问题上的设计与验证"，强度中等 |
| I4 | **动态重调度下的速度优势**（尚未做） | 无 | 需要新实验：在 Phase 2A 的动态事件下，比较策略（毫秒级）和 CP-SAT（秒到分钟级）的响应质量。这是把"快"变成实际优势的关键 |

## 建议精读顺序（由你和导师完成）

1. **D1**（Wang et al., 2024, JMS）：最直接的竞争工作，判断空白是否成立。
2. **A2**（Lee & Chen, 2000, NRL）：维护和生产联合安排的经典模型，确认目标函数和维护规则。
3. **C1**（Paeng et al., 2021, IEEE Access）：参数共享 DRL 和延期目标，和本项目方法最接近。
4. **A4**（Geurtsen et al., 2023/2024, FSMJ）：解释固定与灵活维护收益的差异。
5. **E2**（Kool et al., 2019）：自评基线和采样解码的方法依据。

精读后需要补的：本页"待核"的目标和基线、中文文献检索，以及导师对 I1–I4 的取舍。

## 参考文献（按编号）

- [A1] Ma, Y., Chu, C., Zuo, C. (2010). A survey of scheduling with deterministic machine availability constraints. *Computers & Industrial Engineering*, 58(2), 199–211. https://doi.org/10.1016/j.cie.2009.04.014
- [A2] Lee, Chen (2000). Scheduling jobs and maintenance activities on parallel machines. *Naval Research Logistics*, 47(2), 145–165. https://doi.org/10.1002/(SICI)1520-6750(200003)47:2<145::AID-NAV5>3.0.CO;2-3
- [A3] Lee, Kim (2015). A branch and bound algorithm to minimize total tardiness of jobs in a two identical-parallel-machine scheduling problem with a machine availability constraint. *Journal of the Operational Research Society*, 66(9), 1542–1554. https://doi.org/10.1057/jors.2014.122
- [A4] Geurtsen, Adan, Akçay (2024). Integrated maintenance and production scheduling for unrelated parallel machines with setup times. *Flexible Services and Manufacturing Journal*, 36(3), 1046–1079. https://doi.org/10.1007/s10696-023-09511-z
- [B1] Vepsalainen, A. P. J., Morton, T. E. (1987). Priority rules for job shops with weighted tardiness costs. *Management Science*, 33(8), 1035–1047. https://doi.org/10.1287/mnsc.33.8.1035
- [B2] Baker, Bertrand (1982). A dynamic priority rule for scheduling against due-dates. *Journal of Operations Management*, 3, 37–42. https://doi.org/10.1016/0272-6963(82)90020-1
- [B3] Baker, Kanet (1983). Job shop scheduling with modified due dates. *Journal of Operations Management*, 4, 11–22. https://doi.org/10.1016/0272-6963(83)90022-0
- [C1] Paeng, B., Park, I.-B., Park, J. (2021). Deep reinforcement learning for minimizing tardiness in parallel machine scheduling with sequence dependent family setups. *IEEE Access*, 9, 101390–101401. https://doi.org/10.1109/ACCESS.2021.3097254
- [C2] Li, Lang, Hong, Reggelin (2024). A two-stage RNN-based deep reinforcement learning approach for solving the parallel machine scheduling problem with due dates and family setups. *Journal of Intelligent Manufacturing*, 35(3), 1107–1140. https://doi.org/10.1007/s10845-023-02094-4
- [D1] Wang, et al. (2024). Generative deep reinforcement learning method for dynamic parallel machines scheduling with adaptive maintenance activities. *Journal of Manufacturing Systems*, 77, 946–961. https://doi.org/10.1016/j.jmsy.2024.11.004
- [D2] Hu, et al. (2023). Knowledge-enhanced reinforcement learning for multi-machine integrated production and maintenance scheduling. *Computers & Industrial Engineering*, 185, 109631. https://doi.org/10.1016/j.cie.2023.109631
- [E1] Williams, R. J. (1992). Simple statistical gradient-following algorithms for connectionist reinforcement learning. *Machine Learning*, 8, 229–256. https://doi.org/10.1007/BF00992696
- [E2] Kool, W., van Hoof, H., Welling, M. (2019). Attention, learn to solve routing problems! ICLR 2019. https://arxiv.org/abs/1803.08475
- [E3] Kwon, Y.-D., Choo, J., Kim, B., Yoon, I., Gwon, Y., Min, S. (2020). POMO: Policy optimization with multiple optima for reinforcement learning. NeurIPS 2020. https://arxiv.org/abs/2010.16011
- [E4] Zhang, C., Song, W., Cao, Z., Zhang, J., Tan, P. S., Xu, C. (2020). Learning to dispatch for job shop scheduling via deep reinforcement learning. NeurIPS 2020. https://arxiv.org/abs/2010.12367

只写姓的条目，是 Crossref 核对过的姓；名的首字母没有核实，所以没写。带首字母的条目来自 arXiv、会议页面或检索结果。正式引用前，请以出版方页面为准。
