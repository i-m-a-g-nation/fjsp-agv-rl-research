# 毕设 R2 规则与开发验证

R2 在 R1 有限构造环境上增加 EDD、SPT、Random 三个规则，不进行训练或搜索。输入、动作 mask、整数转移、奖励和终态 G1 检查沿用 R1。只读 `machine_tails` 返回真实机器整数尾部的 tuple 快照，不反推归一化浮点特征。

EDD 在有合法机器的任务中按 `(due_date, processing_time, job_id)` 排序，SPT 按 `(processing_time, due_date, job_id)`；选中任务的机器按 `(machine_tail, machine_id)` 排序。维护按 `(start, machine_id)` 排序：fixed 的 start 为预设时刻，joint 为 `max(machine_tail, window_start)`。最早维护严格早于候选生产开始才先维护；同刻生产优先；没有合法生产时做最早维护。每步重新选择，生产完成后仍完成闲置机维护。这是首版约定，不是最佳维护策略结论；不承诺 joint 规则结果恒优于 fixed。

Random 每回合新建 `random.Random(seed)`，在按编号升序排列的全部合法动作中执行 `choice`，包含维护。所有规则均只接受 0..2**32-1 的非 bool 整数 seed。`RuleEpisode` 的外壳冻结，动作是 tuple，内部 result 是独立且可变的 `MaintenanceScheduleResult`；统一求解包装函数不携带最优性证书，所有 solver 字段保持 None。构造异常透传，不返回部分计划。

`experiments/exp_022_graduation_rule_smoke.py --output-dir <全新目录>` 执行四输入 × fixed/joint × 三规则（seed42），固定 24 行。输入为单机两任务、双机三任务、闲置机器和晚于生产结束的维护边界例。EDD/SPT 手算延期分别为单机 fixed/joint 4/0、双机 6/0。晚维护例生产 makespan=1，维护结束=4，总延期=0。

`results.json` 包含输入、配置和全部结果行。每行保存动作、回报、生产/维护记录、报告及独立复算延期和 G1 检查；只有先通过生产与维护检查并可编码为严格 JSON 的计划才接受。失败行保留在 24 的分母中，接受指标和计划为 null，错误文本有界，其余行继续。CLI 有失败返回 1；目录已存在时拒绝覆盖。

`manifest.json` 保存 expected_runs、accepted_runs、状态、配置、Python 版本、Git HEAD、相关源码 SHA256、results.json SHA256 和 outcome_digest。JSON 按 key 排序并使用紧凑编码，拒绝 NaN。确定性摘要只绑定输入、配置与结果（含动作和计划），不绑定错误文本、运行时、路径或 Git HEAD；在两个新目录运行应得到相同摘要。源码指纹和 Git HEAD 便于识别当前工作树与提交的区别。

两份产物均明确标注 `purpose=r2_development_validation`、`research_status=not_achieved`。这些固定小例仅用于开发正确性验证，不是 G3 的 12 配对先导，不是 RL 训练或性能优势证据；既有 G3 草案仍禁止执行。脚本不调用 CP-SAT、枚举、模型或网络。

## 本轮聚焦证据

在专用 Conda 环境中，每组 Python 命令先打印并确认 `sys.executable`。实现前观察规则入口/只读尾部缺失的 56 项 RED；规格修订维护时刻规则后，58 项规则测试仍 RED。开发验证入口缺失的 8 项测试也先观察 RED。

第一次规则 GREEN 尝试为 54 passed、4 failed：三个测试仍用了旧的 joint 维护 ID 顺序，另一个手填 Random42 初始动作有误；按修订规格和排序后的初始选择列表纠正字面期望，未修改环境或检查器。之后规则、R1 和 G1 聚焦组为 **173 passed**；开发验证脚本组为 **8 passed**。最终合并规则、开发验证、R1 和 G1 聚焦组为 **181 passed in 3.16s**。主代理完整回归/独立审查结论在收尾后补充。

## 完整回归与独立审查

由主代理运行专用环境完整回归和两次原生烟雾命令，独立核验保存计划并记录在本节。此处不以聚焦通过代替完整回归，也不预写成功结果。
