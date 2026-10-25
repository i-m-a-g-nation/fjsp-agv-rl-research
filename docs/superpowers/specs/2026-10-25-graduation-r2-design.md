# 毕设 R2：规则基线与开发验证

用户在进度审计后要求继续，并明确允许多个 agent。承接已公开的下一步，完成 R2 规则和小型对照；沿用 G1/R1 首版假设。本轮不训练 PPO、不执行正式 G3 先导或主网格，不复用旧会话批准。

## 范围与选择

沿用纯 Python `ParallelMaintenanceEnv`、真实动作 mask、独立 G1 检查和总延期目标。生产优先规则容易解释、无需额外优化器；维护优先规则可能在不必要时提前阻塞生产，带搜索的维护插入则改变基线复杂度。因此 EDD/SPT 首版统一采用**有合法生产动作时先生产；否则维护**。这是实施约定，不是已证明最佳维护策略。Random 在全部合法动作中均匀选择，包含维护。

- EDD：在至少有一台合法机器的任务中，按 `(due_date, processing_time, job_id)` 选择。
- SPT：按 `(processing_time, due_date, job_id)` 选择。
- 两者给选中任务按 `(整数机器尾部时刻, machine_id)` 选合法机器。没有合法生产动作时按 machine_id 选合法维护；生产完成后仍补齐闲置机维护。
- Random：局部 `random.Random(seed)` 对按动作编号升序排列的全部合法动作执行 `choice`，每回合新建 RNG，不读取或改变全局随机状态。
- 规则名精确为 `EDD`、`SPT`、`Random`；seed 必须为非 bool 的整数，范围 0..2**32-1，所有规则均校验。

## 接口

在 R1 增加只读 `machine_tails: tuple[int, ...]`，只含真实机器、保持整数，不暴露内部列表或从归一化浮点反推时刻。既有观察、奖励、mask、转移和检查器不改。

新增 `src/graduation/rules.py`：

- frozen `RuleEpisode(rule, mode, seed, actions, total_reward, result)`，其中 actions 为 tuple[int,...]；result 为独立的可变 MaintenanceScheduleResult，frozen 外壳不声称深层不可变。
- `run_maintenance_rule_episode(data, *, mode, rule, seed=42) -> RuleEpisode`：最多恰好 n+m 次合法转移，终态由 R1 检查；异常透传，不返回部分计划。
- `solve_maintenance_rule(data, *, mode, rule, seed=42) -> MaintenanceScheduleResult`：统一算法返回值，复用回合函数，不携带求解最优性证书；solver 字段保持 None。

所有函数在固定或联合模式下使用同一输入、同一选动作规则，仅 mask/维护时机遵循 R1 模式语义。不保证 joint 规则结果一定优于 fixed 规则；可行域包含只约束最优值。

## 开发验证与产物

新增 `experiments/exp_022_graduation_rule_smoke.py`，提供 `run_experiment(output_dir: Path)` 和 CLI `--output-dir`。输出目录必须全新，拒绝覆盖。四个固定手算/边界输入：

1. 单机两任务 p=(2,2),d=(2,4),维护 q=2,窗[0,6),f=0；EDD/SPT fixed/joint 总延期4/0。
2. 双机三任务 p=(2,2,2),d=(2,2,4),各机 q=2,窗[0,6),f=0；EDD/SPT 总延期6/0。
3. 双机单任务 p=2,d=2,各机 q=2,窗[0,2),f=0；所有机器仍维护。
4. 单机单任务 p=1,d=1,q=1,窗[3,4),f=3；生产 makespan=1，维护结束=4，总延期0。

四输入 × fixed/joint × EDD/SPT/Random(seed42) 共24条。不得调用 CP-SAT、枚举、模型或网络。保存输入、动作、回报、完整生产/维护计划、独立复算延期和 G1检查结果。失败行保留、接受指标及计划留空、有有界错误，不删失败分母；CLI失败返回1。生产/维护记录先验证再序列化，畸形结果也转为失败行，不中止其余运行。

`results.json` 保存所有行；`manifest.json` 保存期望/接受数量、状态、配置、Python版本、Git HEAD、相关源码指纹及 results.json 的SHA256。使用规范JSON，拒绝NaN。确定性摘要只含输入、配置、动作、计划和结果，不含耗时/路径/Git HEAD。独立新目录重复运行摘要一致，原有结果不变。

产物明确标为 `r2_development_validation`、`research_status=not_achieved`。它既不是12配对G3先导，也不是RL训练或性能优势证据。旧 G3 JSON 继续 `execution_supported=false`。

## 验收

先测试后实现：验证 EDD/SPT 的区别、所有 tie-break、局部 seed 重放、只选 mask 内动作、n+m 步、闲置机器维护、边界与大整数、输入/全局 RNG 不变、失败拒绝和无最优证书。小样本对照只作开发证据；运行完整专用环境回归和独立审查，保留真实结果。
