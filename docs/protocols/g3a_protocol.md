# 毕设 G3A：固定/联合维护参考对照协议与执行记录（原草案 v0.1）

当前状态：**第二次尝试执行480次请求，475接受/5 ERROR，整批FAILED；用户仅确认失败事实与有效子集，研究仍未达成**。当前结果与完整边界见第13节。以下保留从原草案到材料冻结、批准和执行的历史，不用后续批准改写旧快照。用户偏好加强化学习，完整任务书要求仍未核实。

[同名JSON](g3a_protocol.json)保留原提案及其`execution_supported=false`历史字段。实际主比较通过第10—13节冻结材料及独立入口执行；旧G2/先导批准不替代本批scope/evidence，任何参考运行均不授予RL训练或课题验收权限。

## 1. 研究问题与分工

G3A先回答：在同一首版模型、相同输入和求解预算下，放开维护开始时刻如何影响总延期？使用同一个已验证CP-SAT后端，区分可行域变化与限时搜索效果。

G3B再回答：用户偏好的RL在相同模型、测试数据和推理条件下，相对规则/启发式及CP-SAT参考表现如何？见[RL建模草案](../history/graduation_rl_design_draft.md)，算法和训练预算尚未冻结。

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

主实验每调用CP-SAT1秒、单线程、solver seed42、不重复计时，共480求解秒的请求上限之和。整个新批次累计主动时间上限600秒，包含建模/检查/写盘/报告和监督开销，预算0模型调用/0token；等待人审不计主动时间。600秒符合当前BudgetLimits硬上限。旧单请求路线不支持该批量执行；后续实现的独立有界后端见第11节，不能把480次调用塞进旧已完成会话。

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

历史进度更新：用户随后推进[R1无训练环境](../history/graduation_rl_environment_validation.md)，并继续完成有界神经试训及候选比较，最新状态见[START_HERE](../../START_HERE.md)。这些开发记录本身不代表正式G3A网格执行；后续实际尝试见第13节。原JSON草案的execution_supported=false记录当时状态，保留历史字节；正式主比较材料及后端见第10/11节，下面的开发入口使用独立、固定的先导协议。

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

## 11. 主比较后端与evidence材料（2026-10-29）

本节记录第2版材料交付时的快照；随后的人审批准、启动失败及修复提审见第12节。

用户已明确批准第10节的完整scope哈希，仅进入evidence审核。`exp_030_graduation_main.py`现支持准备/只读复检evidence、查看原账本状态、有批准后执行、只读复检结果。所有动作继续使用原始`budget.sqlite`；只读归档不能替换账本，也不授权执行。scope绑定的8份源码、原模型、求解器、检查器、奖励与训练器均未修改。

执行时先保存480条完整计划行，每对fixed后joint，使用原CP-SAT配置。父进程和工作进程各自核对同一份人审批准、输入、27份来源及Python/OR-Tools运行环境。每条保存完整生产和维护计划，父进程重读G1合法性、延期与solver诊断后生成原始CSV、主比较表和敏感性表；只读复检可以重新生成这些表，不运行求解器。限时逆序、零延期分母、失败/未运行行及非独立工作负载按第6节披露。`COMPLETED`仅表示所有请求已记账，仍可能含UNKNOWN等无有效计划结果；不代表所有配对都有可用指标。

最终相关回归231项通过。受原进程监督器管理的DEVTEST另跑4次小例求解，固定/联合延期为4/0和6/0；独立标准库计算核对计划并穷举机器分配、任务顺序、维护时刻和前后切点，最优值一致。真实CLI在未获evidence批准时拒绝运行，未创建输出，也未改变scope、control、evidence或账本字节。测试中的模拟批准明确标为开发夹具，不写入真实会话。另用真实审批检查/账本执行480条模拟UNKNOWN结果，确认预算预留期间可以启动、结果保留全分母、同一evidence不能重复执行；没有正式求解。

**最终整批后端独立审查未完成**：审查代理触达账户用量限制。已有模块测试、主进程复核及反例修复，不能将其等同于整批独立审查通过。[限制记录](../experiments/results/exp_030_graduation_main_evidence_v2/review_limitations.json)随审核材料保存。远程完整回归以草稿PR对应提交的Checks为准，不用231项局部测试代替全套验收。

本次[evidence中文摘要](../experiments/results/exp_030_graduation_main_evidence_v2/materials/evidence_summary.txt)及[完整请求](../experiments/results/exp_030_graduation_main_evidence_v2/materials/evidence_review.json)绑定哈希`187881a399e7c27ba7949356a716d918b1b4243bf566d4f81d7ea2129397561b`。原600秒累计账本已计约15.828秒、余584.172秒，包含scope/evidence准备及各次保守预扣5秒的收尾；精确浮点数见[预算收据](../experiments/results/exp_030_graduation_main_evidence_v2/materials/budget_snapshot.json)。审批等待不计时。正式网格0次求解，evidence/conclusion均未批准，research_status仍为not_achieved。

日常只读入口如下（先设置项目专用环境并核对解释器）：

```powershell
$mainPython = if ($env:FJSP_CONDA_ENV) { Join-Path $env:FJSP_CONDA_ENV 'python.exe' } else { '.\.conda-env\python.exe' }
& $mainPython -c "import sys; print(sys.executable)"
& $mainPython experiments/exp_030_graduation_main.py status --review-dir experiments/runs/g3_main_review_17bc1aa7
& $mainPython experiments/exp_030_graduation_main.py recheck-evidence --evidence-dir experiments/results/exp_030_graduation_main_evidence_v2/materials
```

实际批准必须绑定原本地packet路径和完整evidence哈希；运行命令为`run --review-dir <实际控制目录> --evidence-dir <已审核原包> --output-dir <新目录>`，没有批准时拒绝。来源/输入/运行环境改变需要新evidence，不能自行补写批准或沿用旧哈希。预算耗尽、进程失败或控制状态改变均不自动重跑、续跑或加时。`exp_029 --recheck`只适用于最初冻结的双段账本；开始evidence后请用`exp_030`检查累计历史。

进程树对工作进程实施硬超时；主进程检查和I/O采用合作式截止检查，每次最终结算/写盘预付5秒且限定在该时段内。阻塞I/O或失败清理可能晚返回，但不能保留迟到成功状态；不承诺强制中断任意文件系统调用。来源哈希是内容身份，记录的主机信息与历史人工决定仍依赖真实回执来源，不能靠哈希自行证明历史事实。

第一版evidence在获批前被新版替代：真实账本集成测试发现运行预留被误判为预算耗尽，导致无法启动；修复同时收紧重复启动检查。旧包、失败日志和[替代记录](../experiments/results/exp_030_graduation_main_evidence_v2/superseded_evidence.json)保留，重新准备的主动时间仍计入同一600秒账本，没有退款或重建。请只审核本节新版哈希。

## 12. 首次批准执行失败与修复后提审（2026-10-29）

本节记录第3版材料准备时快照；其后实际批准及执行结果见第13节。

用户已明确批准第2版`187881a3…` evidence。实际执行一次后，工作进程在第一条求解前被身份检查拒绝，批次标记FAILED，全部480行NOT_RUN、0条接受结果、0次实际求解，科研结论仍不可用。[失败摘要](../experiments/results/exp_030_graduation_main_failed_v1/failure_summary.txt)及[完整记录](../experiments/results/exp_030_graduation_main_failed_v1/failure_record.json)保存实际人审回执、全部CSV/计划行、原始runmanifest和原账本收据。原控制目录`experiments/runs/g3_main_review_17bc1aa7`保持FAILED，不被重置或续跑。

根因是Windows的`platform.machine()`读取了监督器刻意移除的架构环境变量，父进程报告AMD64，精简环境中的子进程报告空串。改用`sysconfig.get_platform()`绑定解释器平台，仍严格比较Python完整版本、解释器路径、OR-Tools版本、系统与解释器平台；没有扩大监督器环境白名单或跳过身份检查。工作进程现在返回限长的阶段/错误原因，父进程保存原始`worker_receipt.json`并绑定进manifest，避免只留下“回执不完整”。

4个新增原生反例先失败后通过。真实生产入口测试使用明确标为TEST_ONLY的合成批准和已经过期的执行截止时间，经过实际子进程、审批和SQLite预算后，在首条求解前超时；480行仍NOT_RUN且没有计划文件，不执行正式算例。最终236项相关回归通过（60.63秒），同时修复验证器对pytest标准分钟时长后缀的误拒绝。原生只读诊断再次确认父/子身份相同，材料/来源/原账本检查通过；缺少新批准时真实CLI拒绝运行且所有材料字节不变。

[第二次尝试审核说明](../experiments/results/exp_030_graduation_main_evidence_v3/attempt_review.txt)是修复后的独立提案，完整evidence哈希为`5f654ce766bfbb9084dc8ea7d497972114f6a2ced2fe8afc6726e2c5951e6fec`。研究范围仍为原`17bc1aa7…`，输入、模型、顺序及每次1秒/单线程/seed42完全相同。复制原实际scope批准，未声称产生新的人审；新控制目录`experiments/runs/g3_main_review_17bc1aa7_attempt2`没有evidence批准。拟用新输出目录`experiments/runs/g3_main_formal_20261029_v2`。这是等待明确授权的额外尝试，未自动重跑。

首次失败耗时和新材料准备均保留在同一原600秒账本；目前累计约30.437秒、余569.563秒，共10个已结算片段。前次失败档案及本次[尝试上下文](../experiments/results/exp_030_graduation_main_evidence_v3/prior_attempt.json)的哈希写入受审核包绑定的validation.log；没有退款、重建账本或隐藏前次480条未运行记录。整批后端的独立代码审查仍未完成，原因是账户用量限制，测试通过不能替代该审查。完整Linux回归以本次修复提交的PR Checks为准。

只读查看新提案（先依项目规则选择专用环境、核对解释器）：

```powershell
& $mainPython experiments/exp_030_graduation_main.py status --review-dir experiments/runs/g3_main_review_17bc1aa7_attempt2
& $mainPython experiments/exp_030_graduation_main.py recheck-evidence --evidence-dir experiments/results/exp_030_graduation_main_evidence_v3/materials
```

第2版的实际批准仅用于已结束的首次尝试，源码与材料已变化，不能拿它批准第3版。只有明确批准本次新evidence才能再执行一次有界比较；执行后仍需conclusion审核。当前不认可任何维护协同效果、RL优势或课题达标。

## 13. 第二次实际执行与结论材料（2026-10-29）

用户在`call_f9b4280f95804ccba4711741e4605f5d`明确批准`5f654ce7…`新版evidence，随后仅执行一次第二次尝试。执行源码为`7b8e07c`，本轮未修改模型、求解器、检查器、预算或任何绑定源码。480次请求全部处理完，475份接受、5份ERROR，无UNKNOWN、未运行或中断行；接受结果为410 OPTIMAL、65 FEASIBLE。5份错误均为`Solver objective/bound disagrees with independent total tardiness`，因此整批保持**FAILED**，不是一次完整通过的参考比较。

| 分组 | 计划配对 | 有效完整配对 | 联合延期更低 | 相同 | 联合延期更高 | 不完整 | 两方OPTIMAL |
|---|---:|---:|---:|---:|---:|---:|---:|
| 主比较 | 160 | 155 | 88 | 63 | 4 | 5 | 124 |
| 敏感性 | 80 | 80 | 43 | 37 | 0 | 0 | 80 |

[全部480行原始指标](../experiments/results/exp_030_graduation_main_attempt2_v1/run/raw.csv)、[160对主比较](../experiments/results/exp_030_graduation_main_attempt2_v1/run/primary_pairs.csv)、[80对敏感性](../experiments/results/exp_030_graduation_main_attempt2_v1/run/sensitivity_pairs.csv)完整保留。分析另给出[48个条件分组](../experiments/results/exp_030_graduation_main_attempt2_v1/conclusion/conditions.csv)和[规模分组](../experiments/results/exp_030_graduation_main_attempt2_v1/conclusion/size_groups.csv)。主比较观察差范围[-95,157]，敏感性[0,59]；负差不截断，固定延期为0时百分比留空。5个缺失配对不被从计划分母160中删除，也不以0补齐。数据只有10组基础随机工作负载、160个物理核心，不能按240个独立样本推断显著性或普遍优势。

已有生产后端重检所有行的来源、输入、审批、预算、计划和派生CSV。另用标准库整数区间算术独立复算475份接受计划：任务恰好一次、机器分配、加工时长、生产与维护互斥、每机一次维护、完整窗口、fixed时刻、总延期、makespan及诊断一致；逐对重算观察差/界/NA，并检查同一物理核心中OPTIMAL joint目标一致。该复算不调用项目领域检查器或求解器，475份均通过；之后从复制出的完整归档再次只读重放通过，没有额外求解。独立计划算术不是整批代码独立审查，后者仍因额度限制未完成。

5份拒绝结果的原始候选和分项数值没有保存，现有记录只能确认合并校验错误，无法确定具体是目标值、下界还是独立延期不一致。不能直接放宽检查或据此断言某一种根因。它们均位于n24/m2主比较，完整case_id/mode/错误保存在[comparison.json](../experiments/results/exp_030_graduation_main_attempt2_v1/conclusion/comparison.json)的rejected_or_missing列表。下一步应设计拒绝候选诊断留档并受控定位，再决定新验证；本批不自动重跑，也不进入RL调参。已保存各接受结果的solver_wall_time和阶段累计账本，尚无逐请求完整端到端耗时，不作运行时性能排名。

同一600秒账本包含旧启动失败、两版准备、第二次求解及本次复核/结论封装；累计约136.296秒、余463.704秒，共14个已结算片段。第二次执行阶段91.313秒，另预付5秒收尾；结论复核4.546秒，另预付5秒收尾，未用不退。精确值见[结论预算收据](../experiments/results/exp_030_graduation_main_attempt2_v1/conclusion/budget_snapshot.json)。全批0模型调用，没有退款、重置、加时或失败重试。批次端到端账本不能冒充每条请求耗时。

[结论中文摘要](../experiments/results/exp_030_graduation_main_attempt2_v1/conclusion/conclusion_summary.txt)与[内容绑定请求](../experiments/results/exp_030_graduation_main_attempt2_v1/conclusion/conclusion_review.json)的哈希为`106f4ba8bcbdc9c9c955a4c7458958af4b236497235a0fe61658cf0e3e70ee6a`。材料生成时控制状态为WAITING_HUMAN_CONCLUSION，experiment_status仍为FAILED、conclusion_approved=false、research_status=not_achieved。待确认的只是本次失败事实、接受子集和未解决问题，不是完整G3通过、RL优势、大创物流协同或课题验收。

归档只读重检（先依项目规则选择专用环境并核对解释器）：

```powershell
& $mainPython experiments/results/exp_030_graduation_main_attempt2_v1/conclusion/analysis.py --recheck experiments/results/exp_030_graduation_main_attempt2_v1
```

此入口只读取保存的原始计划、材料、哈希并重算报告，不调用CP-SAT、不改变账本、不授予新运行许可。执行源码`7b8e07c`的既有验收为本地236项相关测试和Linux1991项完整测试（覆盖率90.75%）；本轮只追加结果档案和说明，结果提交的CI状态以PR Checks为准。

随后用户在`call_1780b4a49e8b421085b0b0b1141a46c7`明确回复“仅确认本次失败事实与有效子集”。[实际结论回执](../experiments/results/exp_030_graduation_main_conclusion_ack_v1/conclusion_approval.json)单独绑定同一`106f4ba8…`完整哈希，原待审材料和原始run状态未改写。当前控制状态为CONCLUSION_RECORDED_EXPERIMENT_FAILED，conclusion_approved=true仅表示事实确认；experiment_status仍FAILED、research_status仍not_achieved，不授权额外求解或RL训练。保存回执前后原账本字节一致，剩余463.704秒未被退款或重置。5条一致性错误、拒绝诊断缺口和独立代码审查缺口仍未解决。

## 14. 拒绝候选诊断（2026-10-29）

本次“继续”按上一明确下一步解释为诊断开发，未伪造内容绑定的正式scope/evidence批准。新增隔离观察器和`exp_031`入口，所有27份旧后端源码、原模型、求解器和检查器均保持字节不变。观察器记录原始响应、每个整数变量、目标表达式和API取值，然后继续返回原基线行；严格目标/下界一致性检查没有放宽。

只执行一次独立开发批次：原5条ERROR各1次、原顺序、每次1秒、单线程、seed42，整个开发入口限定30主动秒，继续使用原600秒账本。5条全部重现原拒绝；这不是480请求正式批次重跑，也不替换任何历史行。所有新候选保持`UNVALIDATED_DIAGNOSTIC_CANDIDATE`和`accepted_for_research=false`。

| 原请求序号（从0计） | 模式 | 报告目标 | 原始整数目标与独立延期 | 差值 | 下界 |
|---|---|---:|---:|---:|---:|
| 167 | joint | 88 | 86 | 2 | 0 |
| 186 | fixed | 109 | 106 | 3 | 0 |
| 222 | fixed | 159 | 141 | 18 | 0 |
| 226 | fixed | 423 | 422 | 1 | 0 |
| 229 | joint | 63 | 61 | 2 | 0 |

5份均为FEASIBLE。原始响应目标等于API目标；返回整数变量、API变量和独立计划延期彼此一致。独立标准库脚本另检任务恰好一次、单机分配、加工时长、资源互斥、每机一次维护、完整维护窗口及fixed时刻，5份均通过。原模型的24个目标系数均1、offset0、scale1，差异是整数级，不能靠增大浮点容差处理。[逐项取证报告](../experiments/results/exp_031_consistency_diagnostic_dev_v1/independent_candidate_check.json)与[独立脚本](../experiments/results/exp_031_consistency_diagnostic_dev_v1/inspect_candidates.py)随原始捕获归档。算术通过不证明搜索过程正确，也不授予科研接受资格。

这与[OR-Tools官方问题5453](https://github.com/google/or-tools/issues/5453)描述的9.15.6755问题吻合：`lin_max`预处理与后处理可能使报告目标与返回变量不一致。本模型使用延期的`AddMaxEquality`，因此是有依据的机制推断；尚未做关闭该预处理的对照，不能说已经独立证明了具体内部规则因果。查看时[修复PR5452](https://github.com/google/or-tools/pull/5452)仍是未合并草稿，没有安装或验证修复版本。只用重算延期覆盖公开目标可能掩盖搜索内部候选排名问题，当前未采用。

本次开发封装另因Windows强制锁文件被纳入哈希清单而失败：worker已经保存全部5份捕获，但批次回执为DEVELOPMENT_FAILED。原失败目录和采集时源码快照不改写。后续版本将运行锁移到结果目录外；合成反例验证修复，没有再次调用这5个问题算例。重放额外核对29份来源，旧27份必须匹配当前原始源码；两份诊断源码发生变化时，必须显式提供采集快照且哈希匹配，绝不执行快照源码。重放还检查开发状态、零正式/模型调用及研究未达成，不能把重算哈希后的材料提升为研究通过。

内部工作进程现在还核对父进程PID、有效期限、父进程持有的锁、原账本预留段和账本哈希；只有公开源码/输入哈希不能直接启动。后续代理审查发现的来源、结果标记、普通求解异常误标完整、内部入口绑定问题均补了合成反例。最终独立复审因账户用量限制未完成；本次审查提出问题不等于修复后独立审查通过，整批G3后端独立审查也仍未完成。

本次工作计账13.828秒，另预付5秒收尾；账本累计155.124秒。由于封装失败，既有保守策略又预留余下444.876秒且不结算，所以charged=600、可用=0。这不表示实际消耗600秒CPU。原账本及17段记录保存，未退款、删除预留、重建或自动续跑。后续代码修复、只读复盘和合成测试属于开发活动，不冒充仍有实验额度；相关旧回归中2次微型G2求解控制也明确与这5次诊断分开记载。

当前仅有只读复检可继续使用（先核对专用解释器）：

```powershell
& $mainPython experiments/exp_031_graduation_solver_diagnostics.py audit
& $mainPython experiments/exp_031_graduation_solver_diagnostics.py recheck --output-dir experiments/results/exp_031_consistency_diagnostic_dev_v1/run --captured-sources experiments/results/exp_031_consistency_diagnostic_dev_v1/captured_sources
& $mainPython experiments/results/exp_031_consistency_diagnostic_dev_v1/inspect_candidates.py --recheck experiments/results/exp_031_consistency_diagnostic_dev_v1
```

这些入口不调用求解器、模型或修改账本。下一步先准备新的有界验证提案，比较原配置与关闭有关预处理/等价严格建模中的一种补救，再用枚举和反例验证目标、返回变量、合法性和界。新试验需要明确的新预算与协议，不能恢复旧账本或直接重跑正式网格。确认参考底座后才推进新的G3/RL对比；大创物流与毕设算法成果均未因此达标。

## 15. 补救开发范围提案（2026-10-29）

本次用户选择开始落实有限交付补齐及下一次验证准备。`exp_032_graduation_remedy_scope.py`只生成或只读复检材料，没有运行命令，也不创建预算、人工批准或求解结果。旧600秒账本继续锁定，原正式480条和5份开发诊断不改写。

提案只改变`cp_model_presolve`一个开关：原5个ERROR的原case/mode各跑开/关两配置，共10次；再对原可枚举单机双任务，在fixed/joint及两配置下运行4次控制，总计14次。每次最多1秒、单线程、seed42，Python3.11.15/OR-Tools9.15.6755。控制例加工2/2、交期2/4、维护时长2、完整窗口[0,6)、fixed开始0；枚举与手算目标为固定4、联合0。

建议新预算60累计主动秒，仅覆盖将来获批执行的入口检查、受监督子进程、结果核验和收尾；本次材料开发准备不计入该未来预算。0模型调用，不重试、不恢复，不修改原模型/严格checker，也不升级依赖。官方[参数定义](https://github.com/google/or-tools/blob/stable/ortools/sat/sat_parameters.proto)确认该布尔开关默认true；[上游问题](https://github.com/google/or-tools/issues/5453)仅作为待验证机制依据，关闭整个预处理不能单独证明某条内部规则是原因。

本版[中文范围摘要](../experiments/results/exp_032_graduation_remedy_scope_v1/scope_summary.txt)、[全部输入](../experiments/results/exp_032_graduation_remedy_scope_v1/inputs.json)、[14条顺序](../experiments/results/exp_032_graduation_remedy_scope_v1/planned_runs.json)及[协议](../experiments/results/exp_032_graduation_remedy_scope_v1/protocol.json)绑定范围哈希`6f9f88f81315bbfdda2da1c7a7c0c29577ab5e0a0fec9039e5b442282918d83e`。范围、新预算和原生执行均未批准；有界执行入口尚待实现，不能把本提案当作已经完成补救验证。

计划保留14条完整分母和所有拒绝/未完成行，逐项记录报告目标、原始整数目标、独立延期、界、状态、参数和完整候选。控制例须OPTIMAL且与枚举4/0一致；5问题例若原配置不再复现，则明确写“反事实证据不足”，不自动重试。仅在这5个请求上减少异常不能推出通用正确性、性能优势、完整G3通过或课题达标。

```powershell
& $mainPython experiments/exp_032_graduation_remedy_scope.py recheck --output-dir experiments/results/exp_032_graduation_remedy_scope_v1
```

上面仅只读核对内容、来源和固定计划，不运行求解器、不改账本。旧未发布草稿因复检闭包缺陷修复而被替换，原草稿移至本机忽略的开发记录，未有人工批准；本节仅以当前完整哈希为待审范围。正式批次的既有scope/evidence/conclusion批准均不自动授权新试验。

## 16. 一次实际预处理对照及停止（2026-10-29）

用户在`call_abf95b525fbb402ab0a44191fe83cfdf`明确批准第15节完整`6f9f88f8…`范围和全新60主动秒，条件为入口实现、测试、复核后仅执行一次14请求，不授权正式G3网格或RL。实际人审回执[单独保存](../experiments/results/exp_033_graduation_remedy_dev_v1/run/authorization/approval.json)，原提案准备时false标记未改。原600秒账本未解锁、退款或重建。

新增`remedy_validation.py`配置观察器与`exp_033`有界入口，只切换`cp_model_presolve`，原模型、checker及29份批准来源不变。新执行器另绑定自身与锁实现，共32份来源；记录实际Solve前的参数。原始候选、API/响应目标、整数变量和目标表达式完整保存，基线ERROR仍保留原样。实际批准、来源、测试/审查、4aa655a成功CI、运行环境及新账本在派发前核对，工作进程再验证父PID、持有锁、单次尝试标记、完整文件集合和原预留段。没有自由配置、批准或恢复命令。

40项合成/零求解专项通过。独立复核先发现工作进程准入、重放来源绑定、失败可重检、状态提升和锁实现来源遗漏，另发现损坏验证记录的收尾问题；修复并补反例后复核未报剩余重要问题。最终两项损坏记录反例先失败后通过。完整本地回归在最后小收尾修复前为2089通过、2跳过；实际执行前专用validate命令重新运行当前40项并绑定32份源码及2份测试。前置`4aa655a`CI为2053通过、覆盖率90.85%；这不冒充新执行器提交的CI，最终远程验收以对应提交Checks为准。此审查范围是新增执行器，不补齐此前整批G3后端独立审查缺口。

执行源码为`5fb4344`。一次14/14全部捕获、原始计划14份均有效，原基线返回12ACCEPTED/2ERROR，程序状态DEVELOPMENT_CAPTURED；预先约定的研究判断却是**INCONCLUSIVE_ORIGINAL_NOT_REPRODUCED**，因为原5个ERROR本次仅复现2个。没有删除另外3个观察、重复尝试或延长单次时限。

| 原请求序号 | 模式 | 原配置报告目标 | 原配置候选重算延期 | 原配置行状态 | 关闭预处理延期 |
|---|---|---:|---:|---|---:|
| 167 | joint | 119 | 114 | ERROR | 1711 |
| 186 | fixed | 121 | 121 | ACCEPTED | 1542 |
| 222 | fixed | 159 | 141 | ERROR | 1371 |
| 226 | fixed | 472 | 472 | ACCEPTED | 541 |
| 229 | joint | 98 | 98 | ACCEPTED | 2176 |

10份大例均FEASIBLE、下界均0；关闭预处理5份均通过严格一致性检查，但原始候选延期全部更大。表中两份ERROR的候选只作诊断，不能提升成原正式研究接受结果，也不据此作一般性能排名。4个小例控制均OPTIMAL，两配置固定/联合分别4/0、界相同，与枚举一致。单线程固定seed与墙钟1秒不能保证每次保留同一候选；本次未复现不抹去旧5/5诊断记录。

新60秒账本工作21.672秒，另预付5秒收尾，累计26.672秒，余33.328秒、无预留。单次attempt1已消费，剩余时间不授权额外求解，入口拒绝恢复或重试。程序内核对和收尾计入这份预算；随后独立标准库开发复盘及复制重放只读、0新增求解，不修改账本，不是第二次试验。独立复算全部14份区间/目标、并枚举小例开工/维护时刻，均通过。旧账本字节相同，原正式475接受/5错误/整批FAILED及研究not_achieved保持不变。

阅读[中文结果](../experiments/results/exp_033_graduation_remedy_dev_v1/findings.txt)、[程序收据](../experiments/results/exp_033_graduation_remedy_dev_v1/run/summary.txt)、[独立算术](../experiments/results/exp_033_graduation_remedy_dev_v1/independent_candidate_check.json)和[新预算](../experiments/results/exp_033_graduation_remedy_dev_v1/run/budget_snapshot.json)。只读复检如下（先核对专用解释器）：

```powershell
& $mainPython experiments/exp_033_graduation_remedy.py recheck --output-dir experiments/results/exp_033_graduation_remedy_dev_v1/run
& $mainPython experiments/results/exp_033_graduation_remedy_dev_v1/inspect_candidates.py --recheck experiments/results/exp_033_graduation_remedy_dev_v1
```

当前1秒样例下，全关预处理的质量代价明显，暂不直接用于正式参考配置。下一步先设计保持每个可行解数学等价的局部延期表达，或核实已修复的上游版本，再准备有界验证。第15节批准已用于这一次尝试，不授权这些新试验、正式网格或训练。

## 17. solver_v2：目标上界验收规则（2026-10-30）

原求解器要求"报告目标 = 返回排程的精确延期"。探针显式写出 `t_j ≥ C_j − d_j` 后，求解器返回带松弛的 `t_j`，报告目标与原模型相同（88/109/159/423/63），排程精确延期仍为 86/106/141/422/61。这说明 FEASIBLE 的报告目标只是排程精确延期的上界，原规则把合法排程误判成了错误。

新增 [`src/graduation/solver_v2.py`](../../src/fjsp_lab/maintenance/cpsat.py)：模型与原求解器相同，验收改为：

- 排程必须通过 G1 检查器（不放宽）；
- 延期 T 从排程独立重算，并作为报告指标；
- 要求 `0 ≤ 下界 ≤ T ≤ 报告目标`，目标和下界必须为整数；
- OPTIMAL 仍要求 `下界 = T = 目标`；
- gap 按 `(T − 下界) / max(1, T)` 计算；
- 可选 `max_deterministic_time`，让单线程运行可重复。

`solver.py` 与 `graduation_backend.py` 保持字节不变：改动它们会使 exp_025/026 参考档案及 exp_030/031/033 复检的源码哈希失配（实测 27 项测试失败）。

[`exp_034`](../experiments/exp_034_graduation_solver_v2_check.py) 在 `b505144` 上运行，状态 PASSED：原 5 个出错请求 5/5 复现、v2 全部接受；确定性上限两次排程逐字节相同；24 个极小对照全部 OPTIMAL 且与穷举一致。见[中文结果](../../experiments/archive/exp_034_graduation_solver_v2_v1/findings.md)。

注意：确定性预算 0.3 时有 2 例明显变差（472 对 422、93 对 61），正式实验若采用确定性上限，需先标定预算。

下一步是用 v2 重跑 G3A 全部 480 次请求，作为新的正式批次单独归档。原 exp_030 的结果和"整批 FAILED"记录不改写。

## 18. 用 solver_v2 重跑正式网格（2026-10-30）

用户批准后，[`exp_035`](../experiments/exp_035_graduation_main_v2.py) 在 `a6e0e1e` 上按原协议的输入、顺序和设置（1 秒墙钟、单线程、seed 42）重跑全部 240 对 / 480 次请求，只把验收换成 `solver_v2`。结果单独归档，原 exp_030 记录不改写。

- **批次 COMPLETED**：480/480 接受，0 错误，0 配对完整性错误。
- **与 exp_030 一致**：双方都接受的 475 行中 472 行延期相同、3 行 v2 更低（n24-m4 墙钟波动）、0 行更高；原 5 个错误全部被接受。
- **n=8 有最优性证明**：全部 OPTIMAL。固定延期大于 0 时，联合在 m2 的 24/24 对、m4 的 39/39 对中严格更低，最优总延期平均降低 51.4% 和 55.6%。
- **n=24 只是限时观察**：68/70 个 FEASIBLE 下界为 0，没有一对能证明最优差为正；观察到的相对降低中位数为 51.3%（m2）和 43.1%（m4），另有 4 对联合更高，属于搜索造成的现象。
- **固定策略影响收益**（n8-m2，全部 OPTIMAL）：相对固定在窗口最早 / 中点 / 最晚，平均降低 44.6% / 51.4% / 30.5%。

边界：联合是固定的松弛，所以方向是预知的，实验价值在于降幅；只有 10 组基础工作负载，配对不是独立样本；n=24 需要更长时限或更强下界才能量化。详见[中文结果](../../experiments/archive/exp_035_graduation_main_v2_v1/findings.md)。G3A 参考对照至此完成；G3B（RL 与规则、CP-SAT 的对比）尚未开始。

## 19. G3B：策略、规则与 CP-SAT 正式对比（2026-10-30）

[`exp_038`](../experiments/exp_038_g3b_comparison.py) 在 `7623a87` 上评估 G3A 全部 480 个实例。最终模型按 exp_036 的验证集事先选定为 `policy_s0`；n=24 主网格另补 CP-SAT 60 秒、4 线程的参考解。

- **对规则**：1 次回放比 MDD 低 8.0%，3 次回放比三规则取最好低 5.9%（p 均 < 1e-10）；9 次回放对 9 规则组合低 1.4%，不显著。n24-m4 优势最大，n24-m2 各档都和规则持平。
- **对 CP-SAT**：n=8 时 1 秒的 CP-SAT 已证得最优，策略差 6%–12%；n=24 时策略比 1 秒 CP-SAT 好 17%–29%，但比 60 秒 CP-SAT 差 5.7%（m2）和 10.9%（m4），62 个困难实例上只有 1 次胜过它。
- **算力**：策略 9 次回放约 82 毫秒（单线程），CP-SAT 困难实例跑满 60 秒 × 4 线程。

结论：在 n ≤ 24 的范围内，策略是比经典规则更好的毫秒级方法，但解的质量明显不如给足时间的 CP-SAT。论文应把它定位为快速响应、可用于动态重调度的近似方法。详见[中文结果](../../experiments/archive/exp_038_g3b_comparison_v1/findings.md)。
