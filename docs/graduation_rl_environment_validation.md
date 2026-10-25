# R1：无训练生产—维护构造环境

用户在已写明R1设计后继续推进。本轮实现`src.graduation.ParallelMaintenanceEnv`，保留G1同质机、单工序、release0、每机一次必需维护和完整窗口设定。没有Gym/PPO适配器、神经网络、训练、RL效果比较或G3正式批量实验，也没有新增依赖。

## 接口和有效结果

`ParallelMaintenanceEnv(data,mode='fixed'|'joint')`在不可变的G1输入上构造计划，固定模式要求fixed_start。最多24任务/4机器，超出或超数值域明确拒绝。相同实例的`reset()`清空回合；换实例或模式构造新环境，不在回合中修改配置。

| 接口 | 返回及语义 |
|---|---|
| `observe()`、`reset()` | frozen ConstructionObservation，包含mode/status/steps/scale、24行任务特征、4行机器特征、对象presence及100动作mask |
| `action_masks()` | 100个布尔值的不可变tuple，True表示当前动作合法；非活动状态全False |
| `step(action:int)` | frozen ConstructionStep：观察、奖励、terminated、truncated、独立结果副本或None |
| `truncate()` | 结束当前未完成回合，truncated=True，result=None，无额外奖励 |
| `get_result()` | 仅合法TERMINATED时返回脱离内部状态的MaintenanceScheduleResult副本；其他状态抛异常 |

生产动作`job_id*4+machine_id`，维护动作`96+machine_id`。padding、重复、越界、bool/浮点等非法动作在修改状态前拒绝；不会默默换动作。每个合法动作消耗一个未安排对象，完整回合恰好n+m步，全部生产完成也必须补齐闲置机器维护才能终止。

机器整数尾部a_i决定追加加工起点。维护未做时，fixed生产结束不得超过f_i，joint不得超过U_i−q_i；维护动作fixed从f_i开始，joint从max(a_i,L_i)开始，完整区间必须可行。归一化观察不参与合法性计算，所有构造时间保留严格整数。

任务特征为(p/W,d/W,scheduled)，机器为(tail/W,q/W,L/W,U/W,f/W,maintenance_done,f_present)，W=ceil(sumP/m)固定于回合。joint未给f时用-1且f_present=0；padding行0且presence=False，不与真实但未完成对象混淆。观察不可修改；返回的调度/instance允许沿用原可变API，但修改副本不会影响环境或后续结果。

## 奖励、终止与失败

生产奖励为`-max(0,C_j-d_j)/100`，维护奖励0，不叠加终端奖励。理论完整回报=-T/100，浮点累计按数值容差核对；实际T始终从完整整数计划独立重算。未来训练需要gamma=1，R1没有训练器，也不自行设置训练超参数。

只有所有任务/维护齐备、原生产检查及G1维护checker通过后才是TERMINATED。结果没有OPTIMAL/FEASIBLE求解证书，solver字段维持None，不将合法构造计划当成最优求解。

ACTIVE、TERMINATED、TRUNCATED和FAILED分别处理。预算截断没有接受计划；终端metric/checker失败抛EpisodeInvariantError并保持FAILED，直到reset。失败、终止或截断后不能继续step。非终态全mask空属于实现错误，停止而不是放行非法动作。

## 已核对的轨迹

| 输入 | 模式 | 动作序列 | 总延期 | 回报 |
|---|---|---|---:|---:|
| 两任务单机p2/2,d2/4,q2,窗口0..6,f0 | fixed | 96,0,4 | 4 | -0.04 |
| 同上 | joint | 0,4,96 | 0 | 0 |
| 三任务双机p2/2/2,d2/2/4,每机q2/窗口0..6/f0 | fixed | 96,97,0,5,8 | 6 | -0.06 |
| 同上 | joint | 0,5,8,96,97 | 0 | 0 |

这四条是指定动作的验证轨迹，未由训练策略生成。动作树测试还完整穷举这些小例和6个固定种子的极小实例：每个终态都过G1检查、其可达最小T与独立枚举一致。该验证覆盖有限样例，不代替设计中的一般左移论证或算法性能实验。

另外验证6条24任务/4机器的合法动作采样轨迹，均28步终止、回报与独立T一致且reset后可复现。这是测试中的合法动作采样，不代表R2研究基线已实现。

复现：专用`.conda-env`或`FJSP_CONDA_ENV`，先确认`python -c "import sys; print(sys.executable)"`，再运行`python -m pytest tests/test_graduation_rl_environment.py tests/test_graduation_rl_reachability.py -q`。专项40项通过；完整回归578项通过、覆盖率89.07%（门槛80%），13条上游弃用警告。源码在完整回归期间未改动。

原生001/002复跑通过，toy CP-SAT11OPTIMAL，原CSV和甘特图逐字节恢复。另直接运行上表四条有界R1动作轨迹，G1检查全部通过，T及回报分别4/−0.04、0/0、6/−0.06、0/0；这是环境验证，不是策略训练结果。完整记录见`review_status.md`及本轮执行ledger。

独立只读代码/数学审查未发现Critical/Important问题；留有一项低优先级测试补强：分别注入末步指标异常、错误T和checker自身异常，验证FAILED/reset各分支。现有统一异常处理和整数累计核对已覆盖拒绝逻辑，审查未发现实际非法结果泄漏。

后续[R2规则及开发验证](graduation_r2_validation.md)已实现，增加只读整数machine_tails快照，其余R1观察/转移/掩码/奖励不变。下一步才接Gym/MaskablePPO及有界试训。G3A协议仍为未冻结草案，现有工作流仍只运行G2参考后端，不会自动调用R1/R2或训练RL。旧G2已完成人审记录保留为历史，不能用其批准启动新阶段。
