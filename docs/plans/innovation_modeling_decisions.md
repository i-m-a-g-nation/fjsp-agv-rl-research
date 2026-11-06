# 大创建模决策建议：依据主流与较新文献（2026-11-01）

本文回答大创最小范围草案中的 5 个建模问题（草案（已于 2026-11-06 整理时删除，可在标签 `pre-cleanup-2026-11-06` 中查看）），并评估创新性。
**决定权在用户**：下面每条都是"推荐默认值 + 依据 + 可选项"，用户确认后才进入实现；
实现大创的 RL 部分仍需按 AGENTS 单独批准（PPO、多智能体 RL 目前禁止）。

文献核实程度如实标注：**[全文]** 表示读过正文中的建模假设；**[摘要]** 表示只读到摘要、
目录或检索片段，正式写论文前必须再读全文核对。

## 0. 结论速览

| 问题 | 推荐默认值 | 主要依据 |
|---|---|---|
| 1 运输时间 | 空驶显式建模；装卸时间并入行驶时间；首工序从 L/U 取料、末工序送回 L/U；同机连续工序不需要运输 | Bilge & Ulusoy 1995；Link 2026；Zhuang 2025；Moinuddin 2026 |
| 2 缓冲区 | 缓冲容量作参数：∞（与主流可比）和有限容量（本项目贡献）；机器前设输入缓冲，不设输出缓冲，加工完的工件留在机器上阻塞到被取走；派车时预留目的缓冲位，开工时释放 | DRL 文献普遍为无限缓冲；MILP 文献有有限/无缓冲与阻塞 |
| 3 AGV | 同质、单载荷、运输不可中断、初始在 L/U；不考虑路径冲突和充电 | Bilge & Ulusoy 1995；Ham 2020；Zhuang 2025；Link 2026 |
| 4 决策与动态 | 事件驱动决策；一次决策选定"工序—机器—AGV"，派车即锁定；同刻事件固定顺序；策略看不到未到达的插单 | Luo 2020；Link 2026；本项目 Phase 2A |
| 5 指标 | 静态：makespan（完工 = 送达 L/U）；动态插单：总延期；运输等待、阻塞时间等只作报告指标 | Bilge & Ulusoy 1995；Berterottière 2024；Luo 2020 |

## 1. 空驶、装卸、首末运输、同机连续工序

**推荐**：
- **空驶显式建模**：AGV 卸完货后从当前位置空驶到下一个取货点，空驶时间取决于前后任务（序列相关）。
  这是 Bilge & Ulusoy (1995) 以来该问题的核心难点 [摘要]，最新的 DRL 模型（Link 2026 的 "travel time to start"）[全文]
  和 MILP 模型（Zhuang 2025 单独定义空驶任务）[全文] 都显式包含它。
- **装卸时间并入行驶时间矩阵**：Bilge & Ulusoy 的标准假设是"加工、装、卸时间都计入时间参数"（Moinuddin 2026 转述）[全文]。
  代码里保留一个默认为 0 的单独装卸时间参数，以备场景需要。
- **首工序必须从 L/U 站运到第一台机器**：各文献一致 [全文：Moinuddin 2026、Link 2026、Zhuang 2025]。
- **末工序后送回 L/U 站，完工时刻 = 送达时刻**：文献有两种口径。
  Link 2026 和 Zhuang 2025 把送到卸货站算进完工 [全文]；Moinuddin 2026 则规定成品不回仓库 [全文]。
  推荐计入，原因是有缓冲和阻塞时，成品不运走就一直占着机器，不计入会让阻塞语义不完整。
  做成开关，关掉后就能与"不回仓库"口径的基准算例对比。
- **同机连续工序不需要运输**：行驶时间矩阵对角线为 0，工件留在机器上，不占 AGV。
  （Moinuddin 2026 把它建成一个零时长的空运输任务 [全文]，效果等价。）

## 2. 缓冲区

**文献现状**：
- DRL 论文普遍假设机器缓冲无限：Link 2026 的输入、输出缓冲都是无限 [全文]；
  HA-DQN (2025) 和一篇 QMIX (2025) 也写明缓冲容量无限 [摘要]。
- 有限缓冲和阻塞只在 MILP/元启发式文献里出现：Caumond 等 (2009) 单 AGV、有限机器缓冲 [摘要]；
  Heger & Voss (2017) 带阻塞的可重入柔性作业车间 [摘要]；阻塞作业车间加 AGV（BJS-AGV）[摘要]；
  Zhuang 等 (2025) 加工区不设缓冲，工件被取走前后一个工件不能送入 [全文]。
  Zhuang 2025 也明确指出，已有模型常做"忽略运输时间、机器缓冲无限"等理想化假设 [全文]。

**推荐**：
- **缓冲容量是参数**：实验同时跑 B = ∞（与主流 DRL 可比）和 B ∈ {0, 1, 2}（本项目的贡献所在）。
- **只设输入缓冲，不设输出缓冲**：加工完的工件留在机器上，直到 AGV 取走，期间机器阻塞，不能开始下一道工序。
  这与 BJS-AGV、Zhuang 2025 的阻塞语义一致；"加工结束"和"机器释放"是两个不同时刻。
- **容量不含机器本身**：B 是机器前等待位的数量，正在加工或阻塞的工件不占 B。
- **派车时预留，开工时释放**：AGV 被派去送货时就预留目的缓冲位，避免到了才发现满了；
  工件从缓冲进入机器开工时释放该位。L/U 站容量无限。
- **死锁**：有阻塞加有限缓冲时，可能出现循环等待
  （A 机阻塞等 B 的缓冲位，B 机阻塞等 A 的缓冲位）。处理方式：
  - 动作掩码只允许已预留到目的位的运输；
  - 仿真器检测死锁，检测到就判这一回合失败并如实记录；
  - 统计死锁频率，作为一个实验结果报告。

## 3. AGV

**推荐**（与主流一致）：
- 同质 AGV，数量是参数（默认 2；Bilge & Ulusoy 算例常用 2 台，此点据记忆，未在本次检索核对），全部能到达所有站点；
- 单载荷（unit-load），运输一旦开始不可中断；
- 初始停在 L/U 站，空闲时停在原地；
- 沿预定最短路径行驶，行驶时间已知，**不考虑路径冲突、拥堵和电量**。

依据：
- Bilge & Ulusoy 的假设"单载荷、走预定最短路径、不计拥堵"（Moinuddin 2026 转述）[全文]；
- Ham (2020) 使用同质机器人（Moinuddin 2026 转述）[二手转述]；
- Zhuang 2025 明确假设无交通冲突、碰撞和死锁 [全文]；
- Link 2026 为单载荷、运输不可中断 [全文]。

**不纳入首版、写进展望**：
- 无冲突路径（Sun 等 2023 Sensors；Moinuddin 2026 的分区与交接）；
- 充电（Abderrahim 等 2020 Energies；Boccia 等，见 Zhuang 2025 综述）。

这些方向都已有专门研究，作为大创首版的扩展点既不新颖，也会显著增加工作量。

## 4. 决策时机、机器分配锁定、同刻事件、未来信息

**推荐**：
- **事件驱动**：机器或 AGV 空闲、工件到达、机器故障或修复时产生决策点。
  这是动态 FJSP 强化学习的常规做法（Luo 2020，新工件插入、每次工序完成或新工件到达时决策）[摘要]。
- **一次决策选定"工序—机器—AGV"三元组**：
  - Link 2026 先选工序、再在该工序条件下选 AGV [全文]；
  - FJSP 的 DRL 主流（如 Song 等 2023, IEEE TII 的异构图网络，未在本次检索核对）选"工序—机器"对。
  本项目合并为单智能体的联合动作，不用多智能体 RL（AGENTS 禁止）。
  派车时机器分配即锁定；已派出的运输和已开工的加工在重调度时冻结，沿用 Phase 2A 的冻结规则。
- **同一时刻多个事件的处理顺序**（文献很少写明，属本项目的设计选择）：
  1. 加工完成、AGV 到达；
  2. 故障、修复；
  3. 新工件到达；
  4. 最后做决策。

  同类事件按编号排序，保证结果可复现。
- **不读取未来**：新工件按泊松过程到达（Luo 2020 采用类似设定，到达分布的细节据记忆，需读全文核对），策略只能看到已到达的工件；
  机器故障沿用 Phase 2A 的事件类型。
- **建议分两步**：先做静态版本，用于对齐基准算例和 CP-SAT；再加插单和故障。

## 5. 完工与评价指标

**推荐**：
- **静态版本以 makespan 为目标**，是 FJSPT 文献的标准目标：
  Bilge & Ulusoy 1995 [摘要]、Ham 2020、Berterottière 2024 [摘要]、Link 2026 [全文]。
  完工 = 末工序送达 L/U（可切换为末工序加工结束）。
- **动态插单版本以总延期为目标**：交期 = 到达时刻 + 紧迫系数 × 工件总加工时间（Luo 2020 以总延期为目标 [摘要]；交期公式据记忆，需核对）。
  这也能和毕设的总延期目标衔接。
- **只报告、不进入目标的指标**：
  - 运输等待时间、机器阻塞时间、缓冲满载次数；
  - AGV 利用率与空驶比例、死锁次数；
  - 重调度时改变的分配数（稳定性）。

  不做多目标优化，也不做能耗（AGENTS 禁止）。

**对照算例**：
- Deroussi & Norre (2010) 的 FJSPT 小规模算例，由 Bilge & Ulusoy 的布局扩展而来；
- Ham (2020) 基于 Hurink 的中等规模算例。

两套算例的数据能否公开获得需要核实。小规模用 CP-SAT 作精确参考：Ham 2020 已用 CP 求解这些算例，本项目也有 CP-SAT 经验。

## 6. 创新性评估

**结论：有组合式创新，但不是新范式；能否成立取决于一次系统的查新。**

> 第一轮查新（英文与中文网络）已完成，见[查新报告](../literature/innovation_novelty_search.md)。主要修正：
> "DRL + 有限缓冲的 FJSP"已有 Zhang 等 2026（无运输），"DRL + 有限资源 + 死锁的 FMS"已有 Hu 等 2020（Petri 网）。
> 所以下面的创新点 1 必须收窄为"在 FJSPT 框架下（AGV 显式行驶、含空驶）引入有限输入缓冲、加工后阻塞和死锁处理"。
> 第二轮知网检索（75 条）后：主创新点仍未发现重合，但空档更窄。"FJSP+AGV+有限缓冲"已有遗传算法的硕士论文，
> "DRL+运输+阻塞"已有流水车间类的期刊论文；贡献表述见查新报告第 5 节。

已经很拥挤、**单独不构成创新**的方向（2023–2026 有大量论文）：
- FJSP + AGV + 深度强化学习：
  - HA-DQN (2025, Complex & Intelligent Systems)；
  - 树形网络 DRL (2025, Swarm and Evolutionary Computation)；
  - 多智能体 DRL (2025 会议章节)；
  - Link 等 (2026, IEEE CASE)。
- 动态 FJSP + AGV + DRL：
  - Wang 等 (2024, Processes)；
  - GNN + D3QN (Future Generation Computer Systems)；
  - Dueling DDQN 等。
- 节能、充电、无冲突路径：都已有专门研究。

**可以主张的创新点**（按可信度排序）：
1. **问题层面**：在 **FJSPT 框架**（AGV 显式行驶，含空驶）的 DRL 调度中引入**有限输入缓冲 + 加工后阻塞 + 死锁**。
   - FJSPT 一线的 DRL 论文假设缓冲无限；
   - 有限缓冲的 DRL 论文（Zhang 2026）没有运输；
   - Petri 网一线（Hu 2020）处理了有限资源与死锁，但运输的建模方式不同。

   这三者之间有空档，但"首次用 DRL 处理有限缓冲"这类宽泛说法不能用。
2. **分析层面**：研究缓冲紧张时"联合决策"与"解耦决策"（先排机器、再派车）的差距如何变化。
   Link 2026 在缓冲无限的作业车间中提出了"协调差距"并研究了资源紧张度的影响 [全文]，
   本项目把它推广到有限缓冲的柔性作业车间，定位清楚，也容易写成论文。
   1990 年代 FMS 研究做过缓冲容量的灵敏度分析，但用的是规则和束搜索，也没有做联合与解耦的对比（见查新报告）。
3. **方法层面**：考虑缓冲预留与死锁的动作掩码；先模仿 CP-SAT 或元启发式教师、再做策略梯度微调。
   后者迁移自毕设已验证的流程。这一点更多是工程贡献，单独的创新性弱。
4. **可信度层面**：独立检查器核对工件和资源守恒，小规模用 CP-SAT 提供精确参考。
   这能提高结论的可信度，可以写进论文，但通常不算创新点。

**风险**：
- **查新风险**：第一轮查新已做（约 25 次检索，6 篇读到正文），没有发现与主创新点完全重合的论文，
  第二轮知网检索也没有发现完全重合的论文，但相邻工作很多（见[查新报告](../literature/innovation_novelty_search.md)第 5 节）。
  仍未覆盖 WoS/Scopus 的数据库内检索，投稿前建议再做一次引文追溯。
- **结果风险**：不能预先断定 RL 一定优于规则或元启发式；论文要如实报告。
- **时间风险**：距 2027 年 3 月约 4 个月。仿真器、检查器和静态版本约 3–4 周，动态与 RL 约 4–6 周，
  论文只能做到投稿，录用时间不可控。现实的投稿目标是 EI 会议（如 IEEE CASE、CCC）或中文核心期刊。

## 7. 待用户确认

1. 逐条确认或修改第 0 节表格中的 5 个推荐默认值。
2. 是否接受"有限缓冲 + 阻塞 + 联合/解耦对比"作为大创主创新点。
3. 是否先做系统查新再开始编码（建议先查新，约 1–2 天，知网部分需要用户参与）。
4. 批准大创的第一阶段：`fjsp_lab.logistics` 只依赖 `fjsp`，范围为数据结构、事件仿真器、检查器、规则基线和静态 CP-SAT；不含 RL。

## 参考文献（本文用到的）

- Bilge Ü., Ulusoy G. A time window approach to simultaneous scheduling of machines and material handling system in an FMS. *Operations Research*, 1995, 43(6): 1058–1070. [摘要]
- Deroussi L., Norre S. Simultaneous scheduling of machines and vehicles for the flexible job shop problem. 2010（会议论文）. [二手转述]
- Ham A. Transfer-robot task scheduling in flexible job shop. *Journal of Intelligent Manufacturing*, 2020. [二手转述]
- Homayouni S. M., Fontes D. B. M. M. Production and transport scheduling in flexible job shop manufacturing systems. *Journal of Global Optimization*, 2021, 79(2): 463–502. [摘要]
- Berterottière L., Dauzère-Pérès S., Yugma C. Flexible job-shop scheduling with transportation resources. *European Journal of Operational Research*, 2024, 312(3): 890–909. [摘要]
- Zhuang C. 等. Comprehensive MILP formulation and solution for simultaneous scheduling of machines and AGVs in a partitioned flexible manufacturing system. *Machines*, 2025, 13: 519. [全文]
- Link M., Hoss J., Klarmann N. An analysis of the coordination gap between joint and modular learning for job shop scheduling with transportation resources. arXiv:2604.24117, IEEE CASE 2026. [全文]
- Moinuddin A., Er Raqabi E. M., Van Hentenryck P. Scheduling and routing in the flexible job shop with heterogeneous transbots and zoning: a constraint programming approach. arXiv:2604.24483, 2026. [全文]
- Luo S. Dynamic scheduling for flexible job shop with new job insertions by deep reinforcement learning. *Applied Soft Computing*, 2020. [摘要]
- Wang J. 等. Dynamic integrated scheduling of production equipment and automated guided vehicles in a flexible job shop based on deep reinforcement learning. *Processes*, 2024, 12(11): 2423. [摘要]
- A heuristic-assisted deep reinforcement learning algorithm for flexible job shop scheduling with transport constraints. *Complex & Intelligent Systems*, 2025, doi:10.1007/s40747-025-01828-6. [摘要]
- Caumond A. 等 (2009)；Heger J., Voss T. (2017)；Sun 等 (2023, *Sensors*)；Abderrahim M. 等 (2020, *Energies*)：均为 [摘要/综述转述]。
