# 当前毕设参考会话：人审摘要

本地会话：`experiments/ai_memory/graduation/g2-reference-v1`。2026-10-25用户分别明确批准scope、evidence和conclusion，真实决定均已记录；会话现为COMPLETED/GRADUATION_REFERENCE，研究状态仍为not_achieved，模型调用0。本页解释已审材料与结果，不替代原始哈希和记录；见[最终报告](../experiments/ai_memory/graduation/g2-reference-v1/report.md)、[最终结构化记录](../experiments/ai_memory/graduation/g2-reference-v1/report.json)。

## 已审核的实际结果

| 模式 | 实际生产计划 | 实际维护 | 总延期 | 生产makespan | 状态/下界/gap |
|---|---|---|---:|---:|---|
| 固定 | J1:2–4；J0:4–6 | 0–2 | 4 | 6 | OPTIMAL / 4 / 0 |
| 联合 | J0:0–2；J1:2–4 | 4–6 | 0 | 4 | OPTIMAL / 0 / 0 |

固定方案中J1按期完成，J0延期6−2=4；联合方案两任务均按期完成。每任务一次、每机一次必需维护、完整窗口、互斥、时长及总延期重算均通过；原始目标与独立延期一致。固定方案与此前另一任务顺序的手算计划不同，但最优总延期相同。

[本地原始报告](../experiments/ai_memory/graduation/g2-reference-v1/graduation_run/report.md)、[固定计划](../experiments/ai_memory/graduation/g2-reference-v1/graduation_run/fixed.json)、[联合计划](../experiments/ai_memory/graduation/g2-reference-v1/graduation_run/joint.json)已保存，manifest及四份登记产物的字节哈希、保存计划的领域/元数据检查在结论恢复前后重新核对。最终累计主动执行约10.984秒，原预算120秒；模型/供应商调用0。

已批准conclusion哈希为`9b3a96b2645e397a528ccc4e5df2e955590477265fb5c9a2b641625ef56474b7`，manifest哈希为`a3426e17a5b868c3c9a299a4146ff82b395fb244b4787b4853d2cc8cea0fc42e`。用户明确选择“批准 conclusion，仅确认本次参考运行”，不把一例4对0外推为普遍性能优势、创新性或毕设/大创验收完成；研究状态仍为not_achieved。

真实审核顺序为scope→evidence→conclusion，三份决定的reviewer均为human_user_via_chat，依据本会话逐项明确确认记录。最终CLI返回2，含义是本次参考运行完成但课题尚未达成，不是执行失败。已完成会话不能重放旧批准；遗留review-request.json/decision-template.json是最后一轮材料，是否待审应以status.json和真实检查点为准。

## 本次审核范围

| 项目 | 本次具体内容 |
|---|---|
| 目的 | 让同一个极小算例通过固定/联合参考求解、领域检查和报告链；研究状态仍未达成 |
| 任务 | J0加工2、交期2；J1加工2、交期4；均在0时刻可加工，每任务一道不可抢占工序 |
| 机器 | 一台同质机器，无运输、换型、共享维修班组或随机故障 |
| 必需维护 | 时长2，整个维护区间在[0,6)内，每机恰好一次，不能省略 |
| 固定方案 | 维护必须从0开始；生产顺序由求解器决定 |
| 联合方案 | 相同任务/交期/维护时长/窗口，只放开维护开始时刻，可选范围0..4 |
| 目标 | 最小化总延期sum(max(0,C_j-d_j))；提前完成不能抵消其他任务延期 |
| 执行 | 已验证G2 CP-SAT后端，两种模式各至多10秒、单线程、seed42；原累计主动执行预算120秒，提供者调用/token预算均0 |
| 结果核对 | 生产约束、每机维护、完整窗口、生产维护互斥、独立总延期及求解目标/下界/gap；保存后在结论审核时再次重建核对 |

预先手算期望为固定4、联合0，本会话实际结果已达到相同目标值，详见上表。正式G3比较、任务书最终算法、大创物流/RL和学术成果均不据此完成。

## 已批准evidence的范围记录

用户批准后已仅运行上述两次参考求解，保存计划和诊断，并停在conclusion审核。FEASIBLE仍为限时可行，失败不计有效指标；没有自动批准结论、扩大模型、抓取论文、调用AI或训练RL。

已批准evidence材料哈希为`ff6ff76f3f863a53ab87213892b9d9f05c16627c6de824097236e4af97ea61c5`；原始请求哈希为`e36db3c822e37f2605105dcf3211014972dc9765543e5ed2b8ac37cdc07d2814`。材料若改变，旧决定不能继续使用。
