# 毕设 G3A：固定/联合维护参考对照协议草案 v0.1

状态：**正式协议仍为草案，主网格未冻结、未执行；先导开发验证已实现并运行**，见文末2026-10-28记录。用户“继续”承接G3协议设计；随后说明“暂不清楚，但最好加强化学习”。因此把RL列为优先研究方向，完整任务书要求仍未核实。本页正式网格、生成规则与预算仍是设计建议，不是已生成的人审批准。

机器可读提案见[同名JSON](graduation_g3_protocol_draft.json)，它不是现有018/019的可执行协议，`execution_supported=false`，不能直接投入工作流。原已完成三审会话的批准不授予本协议运行或RL训练权限。

## 1. 研究问题与分工

G3A先回答：在同一首版模型、相同输入和求解预算下，放开维护开始时刻如何影响总延期？使用同一个已验证CP-SAT后端，区分可行域变化与限时搜索效果。

G3B再回答：用户偏好的RL在相同模型、测试数据和推理条件下，相对规则/启发式及CP-SAT参考表现如何？见[RL建模草案](graduation_rl_design_draft.md)，算法和训练预算尚未冻结。

比较方案有两条：先做参考模型对照，或直接进行多算法排名。选择前者作为当前设计，因为已有G2后端，而RL环境、最终算法及独立测试协议尚未建立。CP-SAT参考不能自动替代最终算法要求，也不能用“RL联合方案对CP固定方案”同时改变模型与算法后声称算法优势。

## 2. 保留的模型

同质平行机、单工序不可抢占、release0、每机一次必需维护含闲置机、整个维护区间在窗口内、无共享维修班组。唯一目标为总延期T=Σmax(0,C_j-d_j)；makespan仅作生产完工诊断。输入、约束及已有G1/G2检查器不改。

固定与联合的一对请求逐字节使用相同任务、交期、机器、维护时长、窗口和预设fixed_start；只通过mode改变是否强制维护开始等于fixed_start。两模式均优化生产分配和顺序，同预算、线程和solver seed。

## 3. 主网格与敏感性

| 因素 | 主网格 |
|---|---|
| 任务数n | 8、24 |
| 机器数m | 2、4 |
| 维护强度α | 10%、30% |
| 窗口可调宽度β | 25%、75% |
| 交期系数τ | 75%、125% |
| instance seed | 101、202、303、404、505 |
| 主固定策略 | 窗口内可行开始区间的中点 |

32条件格×5种子=160个主配对请求，每对fixed/joint各一次，共320次求解。此“格数”是配置数，不是独立样本数。

预先选择n=8,m=2的全部40个主算例，另加窗口最早、最晚两种固定策略；每策略仍重新执行fixed/joint两模式，新增80配对/160求解。合计240配对请求、480次求解。敏感性子集依输入规模指定，不看结果选择。它用于检查结论对固定安排的依赖，不把最差策略挑出来作为主基线。

跨不同固定策略时fixed_start当然不同，每对内部保持相同完整输入。joint模型忽略fixed_start约束，重复joint不是新的独立质量样本；保存真实运行状态，不假定限时排程必然逐字相同。

## 4. 可复现生成规则

时间采用抽象整数单位，不解释为真实工厂分钟。按任务ID和机器ID升序生成。

三条独立RNG流分别为`processing`、`due`、`maintenance_start`。每条种子为UTF-8字符串`graduation-g3a-v1|n={n}|seed={instance_seed}|field={field}`的SHA256前8字节，按big-endian无符号整数转换，传入Python`random.Random`。锁定Python版本，使用`randint`闭区间采样。α、β、τ、m不进入种子键，以便相同n/seed共享加工时间、分位数及机器分位数前缀。

每个n/seed先生成n个p、n个u和4个v；m=2取v前两项，workload_hash始终包含完整4项v及生成配置，避免把同一基础随机流的不同机器前缀误计为独立工作负载。先导也使用同样的四项v规则，只取前两项。

1. p_j在[1,20]均匀整数采样，due分位数u_j在[50,150]采样，机器开始分位数v_i在[0,25]采样。
2. W=ceil(Σp_j/m)，仅作输入尺度，不是优化目标或已知最优makespan。
3. q_i=max(1,ceil(α_percent×W/100))，s_i=ceil(β_percent×W/100)。同一条件下各机q/s相同，但窗口起点可不同。
4. L_i=floor(v_i×W/100)，U_i=L_i+q_i+s_i。
5. d_j=ceil(τ_percent×W×u_j/10000)。较小τ使对应交期不晚，但不据此预断每例的延期量。
6. 主策略f_i=L_i+floor(s_i/2)；最早f_i=L_i，最晚f_i=L_i+s_i。均有f_i+q_i≤U_i，不依赖求解输出。

ceil/floor使用整数运算，不用浮点近似；先完整生成并保存输入，再求解，不能看结果调整交期/窗口。维护不得通过省略或延长窗口来改善指标。

主网格只有n×seed=10组独立基础随机流；同一组在m、α、β、τ条件间重复使用。每格5种子也是小样本。保存`workload_hash`(n/seed/p/u/v)、`core_model_hash`(p/d/m/q/L/U，不含f)、`request_hash`(完整f与配置)。量化可能令不同条件产生相同物理实例；报告唯一哈希数和别名，保留标签但不冒充独立样本、不重采样美化结果。

## 5. 先导、资源与停止规则

先导使用n=3,m=2、p∈[1,4]、相同α/β、τ=100%、seed11/22/33及中点策略：12配对、24求解。每条还由既有独立枚举核对，要求双方OPTIMAL并与枚举一致、G1检查通过。W≤6、每机可行维护开始数≤6，最多36个维护组合；既有全局排列/分配/cut枚举每组合264状态，至多9504，低于200000预算。先导预算90秒，失败不自动加时；须修复或改版后再冻结主实验。

主实验每调用CP-SAT1秒、单线程、solver seed42、不重复计时，共480求解秒的请求上限之和。整个新批次累计主动时间上限600秒，包含建模/检查/写盘/报告和监督开销，预算0模型调用/0token；等待人审不计主动时间。600秒符合当前BudgetLimits硬上限，但**当前单请求路线尚不支持该批量执行**，必须先实现有界批次后端，不能把480次调用塞进旧已完成会话。

先导与主批次使用两个新的持久会话，各自三审和预算（90/600秒），计划总主动上限690秒。先导通过不自动批准或启动主批次；预算不互相退款或借用。这里给的是设计上限，当前没有执行或批准这两个新批次。

每对按fixed后joint顺序运行；先遍历JSON主网格中n/m/α/β/τ/seed各数组的声明顺序，再遍历敏感性子集及earliest/latest顺序，不按字符串case_id重新排序。单线程同机不并发，不用计时排名；不能为了获得更好值调整顺序或重试。主网格先于额外策略，预算耗尽时后部缺失须完整披露，不能只报主网格成功或将剩余行删掉。

上限不保证机器实际能完成全部配置。逐次原子保存已检查的计划和状态；总超时终止进程树，批次标BUDGET_EXHAUSTED，未完成行NOT_RUN/中断诊断，无有效指标。保留全部规划行；不自动续跑、挑选成功前缀或提高预算。修改网格、预算或失败重跑策略须新版本、新会话与独立记录。

## 6. 指标与限时求解解释

保存每次原始status、T、原始目标、下界LB、按T计算的gap、solver_wall_time、含检查的端到端时间、生产makespan、计划、G1违规及错误。只有合法OPTIMAL/FEASIBLE有接受指标；UNKNOWN/失败/非法不以0填补。FEASIBLE始终称限时可行参考，不能升格最优。

配对主指标D_obs=T_fixed−T_joint，可为负，不能截成0。两方都OPTIMAL时联合T不得大于固定T，否则是完整性异常，保留证据并使比较失败。限时逆序不等于维护可调有害，也不删样本。

对双方合法且各有有效LB/UB的配对，模型最优差Δ*有界：

`max(0, LB_fixed − T_joint) ≤ Δ* ≤ T_fixed − LB_joint`。

非负下界来自固定可行域包含于联合可行域。若右界为负或小于左界，记录完整性异常，不静默修补求解器界。区间仅为当前输入的界分析，不改变任何FEASIBLE状态；下界严格大于0才支持有界证据的严格改善。缺失有效计划/界时区间留空。

百分比只在T_fixed>0时为D_obs/T_fixed；T_fixed=0记NA并单列零延期/平局/限时逆序，不能加epsilon隐藏分母问题。按条件分别报告完整配对数、失败/未运行数、两方OPTIMAL数、原始D及范围和各类状态。全局描述须说明同一基础随机流被重复使用；不把480次调用或240配对当独立样本，不据5种子宣称统计显著或普遍优势。

## 7. 产物与审核

实现后须保存精确协议、完整输入、所有规划行(含失败)、两模式生产/维护计划、原始CSV、状态分组汇总、比较区间与异常、manifest的源代码/依赖/硬件/输入/输出哈希及报告。原生/工作流入口均不得覆盖旧目录。主网格和敏感性分表，不挑最佳种子或替换固定策略；图若需要，预先指定seed101、中点、n8/m2代表例，数值以原始记录为准。

新工作流仍为范围→协议/输入证据→实际批次→结论三审，不继承G2小例批准。范围审核须明确600秒上限及残缺处理；证据审核须看到先导核对、全部输入及生成版本；结论审核核对界/状态、失败和依赖条件。协议草案或批次COMPLETED均不自动使课题达标。

## 8. 与RL及后续实现的连接

G3A只做可行域/参考比较。它的数据与结果可用于开发理解，因此不能冒称未来RL的未见测试集。RL环境先做独立G1/G2正确性验证；训练、验证、最终测试须隔离实例生成种子，算法/超参数冻结后再冻结独立测试协议。

后续实施顺序：G3A生成器与去重/预算测试→先导独立枚举验收→有界批次/完整产物和三审→主参考对照；另线R1无训练环境→R2掩码规则基线→R3短训练试验→R4独立算法比较。最终算法以用户RL偏好推进设计，同时继续核对完整任务书，不把偏好写成原题强制要求。

历史进度更新：用户随后推进[R1无训练环境](graduation_rl_environment_validation.md)，并继续完成有界神经试训及候选比较，最新状态见[START_HERE](../START_HERE.md)。这些不代表正式G3A网格已经执行。原JSON草案的execution_supported=false仍有效；下面的开发入口使用独立、固定的先导协议。

## 9. 先导开发验证（2026-10-28）

新增`exp_028_graduation_reference_pilot.py`，只执行本草案12对先导配置。生成器以独立RNG流保存p/u/四个v、完整实例及三层身份；所有输入与24条计划行先落盘，再按fixed→joint执行。原G1、CP-SAT及独立枚举保持。每条均须OPTIMAL、领域合法并与枚举目标一致；主进程还会重读计划并重新枚举核对。失败保留完整分母，不覆盖或续跑已有目录。

原生两次新目录复跑分别3.375秒和3.625秒，24/24通过，输入和最优目标一致。共有3组基础随机工作负载、12个不同物理模型；10对联合维护总延期更低，2对相同。独立标准库脚本重算两次运行共96份生产/维护计划，工序唯一性、资源互斥、完整窗口、固定开始、总延期及最优诊断均一致。该结果不证明RL优势、普遍性能或课题达标；这些实例已暴露为开发数据。

运行及只读复检（先按项目规则选择专用环境、核对解释器）：

```powershell
$pilotPython = if ($env:FJSP_CONDA_ENV) { Join-Path $env:FJSP_CONDA_ENV 'python.exe' } else { '.\.conda-env\python.exe' }
& $pilotPython -c "import sys; print(sys.executable)"
& $pilotPython experiments/exp_028_graduation_reference_pilot.py --output-dir experiments/runs/my-g3a-pilot
& $pilotPython experiments/exp_028_graduation_reference_pilot.py --recheck experiments/runs/my-g3a-pilot
```

预算最多90秒，覆盖输入准备、工作进程执行及主进程验收。CP-SAT/枚举工作进程受进程树硬超时管理；主进程在重放、文件操作及最终收据前后检查真实截止时间。阻塞文件I/O或失败收尾可能在期限后返回，但迟到结果不能保留COMPLETED。复检核对预算、分母、协议与来源记录结构；默认读取历史证据而不要求源码字节等于当前检出。API的`require_current_sources=True`才同时检查当前源码；记录的主机身份本身不是哈希能证明的事实。

这是开发者根据原草案选定的先导实现，`formal_approval=false`、`research_status=not_achieved`。没有生成三审批准，没有启动480次主网格或接入新RL训练。正式会话仍须遵守原范围、证据和结论审核。[两次运行及独立核对归档](../experiments/results/exp_028_graduation_reference_pilot_v1/)

## 10. 主比较范围材料（2026-10-29）

`exp_029_graduation_main_scope.py`已实现范围材料准备及只读复检。按上述声明顺序生成160对主比较，再对n8/m2的40个主算例逐一追加earliest/latest，共80对敏感性分析。每对的fixed/joint引用同一完整输入；480条计划行均为NOT_RUN。用两份JSON集合保存全部输入与求解顺序，保留相同物理模型的所有条件标签。

实际材料包含10组基础工作负载、160个不同物理核心：120个核心只有中点策略，40个核心有中点/最早/最晚三种固定策略。独立标准库脚本逐项核对全部240对输入、480条顺序、RNG/整数公式及三层身份，未调用项目生成器或求解器。相关53项测试通过，独立审查最终31项专项通过，原预算/账本/只读反例均复检后拒绝。

原生材料的scope哈希为`17bc1aa7d715f2090468718c8f3a14327d979178ef48b7980c5964b99fa0c0a3`。[中文审核摘要](../experiments/results/exp_029_graduation_main_scope_v1/materials/scope_summary.txt)、[全部输入](../experiments/results/exp_029_graduation_main_scope_v1/materials/inputs.json)、[求解顺序](../experiments/results/exp_029_graduation_main_scope_v1/materials/planned_runs.json)、[审核请求](../experiments/results/exp_029_graduation_main_scope_v1/materials/scope_review.json)、[独立矩阵复检](../experiments/results/exp_029_graduation_main_scope_v1/independent_matrix_check.json)。这些归档是准备时快照，批准记录须独立绑定该scope哈希，不能把快照的false字段自行改成批准。

总预算仍为600累计主动秒。输入生成、来源哈希、审核材料构建和完整静态重构从函数入口计时；最后账本结算/回执刷新保守预扣5秒，且该阶段本身限定5秒，未用不退。当前已计账5.172秒、剩余594.828秒；等待人审不计时。账本缺失、篡改或未结算均拒绝；复检使用immutable只读连接并拒绝WAL，避免创建旁路文件。迟到或失败收尾可能晚于期限返回，但不能留下可审核就绪状态。

```powershell
$scopePython = if ($env:FJSP_CONDA_ENV) { Join-Path $env:FJSP_CONDA_ENV 'python.exe' } else { '.\.conda-env\python.exe' }
& $scopePython -c "import sys; print(sys.executable)"
& $scopePython experiments/exp_029_graduation_main_scope.py --output-dir experiments/runs/my-g3a-main-scope
& $scopePython experiments/exp_029_graduation_main_scope.py --recheck experiments/runs/my-g3a-main-scope
```

本入口只生成scope材料，不运行CP-SAT、模型API、RL或最终测试，不提供主实验执行后端。实际会话保留在原本地新目录，归档用于只读审阅。根据本协议“范围→协议/输入证据→实际批次→结论三审”，scope批准只允许进入evidence；旧G2小例及先导的批准均不能代替这一批材料的审核。
