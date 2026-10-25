# 毕设参考求解：三审工作流使用说明

本路线把已验证G1维护检查及G2固定/联合CP-SAT接入LangGraph持久会话。只执行明确输入的离线参考模型，不调用文献/RAG、模型服务、网络或代码生成，不改变原始课题契约和其他路线。用户本次“继续”授权这项接入，未授权自动代替人审核。

## 输入与首次运行

示例：[graduation_reference_v1.json](../experiments/requests/graduation_reference_v1.json)。两任务加工时间2、交期2/4，一台机器必需维护2、完整窗口[0,6)、固定开始0；G2手算参考最优延期为固定4、联合0。

请求必须包含schema_version=1、request_id、tasks、num_machines、maintenance、solver；没有可执行代码或自由模型指令。未知/重复字段、非有限数、bool整数、缺失固定开始、不支持的资源/运输等参数均拒绝。首版同质机、单工序、release0、每机必需维护一次且无共享班组；所有维护完整落在窗口内。支持最多50任务/10机器，每次求解时间(0,30]秒、1..4线程，整数seed0..2^31-1；还有G2保守数值上界，请求文件最多1MiB。

在专用环境中执行：

```powershell
$workflowPython = if ($env:FJSP_CONDA_ENV) { Join-Path $env:FJSP_CONDA_ENV 'python.exe' } else { '.\.conda-env\python.exe' }
& $workflowPython -c "import sys; print(sys.executable)"
& $workflowPython experiments/exp_018_ai_rag_workflow.py --track graduation --graduation-request experiments/requests/graduation_reference_v1.json --session-dir experiments/ai_memory/graduation/g2-reference-v1
```

首次返回3，状态WAITING_HUMAN/scope，尚未求解。默认提供者调用和token预算均0，主动执行时间预算仍为120秒，由原进程监督及累计预算控制。请求不能与其他track、动态协议、论文、在线模式、网络、fallback或RAG导出组合；这些组合在读取凭据前拒绝。

## 三道审核各看什么

| 阶段 | 人应阅读 | 本阶段批准允许什么 |
|---|---|---|
| scope | contract原课题要求、graduation_request中全部任务/维护/配置、模型假设和预算 | 进入模型输入证据审核，尚不求解 |
| evidence | 同一输入的字节哈希、固定维护来源、完整窗口、目标和两模式公平性 | 在预算内运行固定/联合已验证参考求解器 |
| conclusion | 原始生产/维护计划、合法性、求解状态、实际总延期、原目标/下界/gap/耗时、失败项及科研缺口 | 完成本次运行的审核记录，研究状态保持not_achieved |

文件均在会话目录：`review-request.json`给出本轮内容及artifact_hash，`decision-template.json`是空白模板。审核人阅读后另存决定文件，填写真实reviewer、approve或reject及说明，保留stage和artifact_hash。不要把测试中的synthetic决定或AI填写文件当作真实人审。

恢复时继续使用相同会话目录，传入你填写的决定文件，例如：

```powershell
& $workflowPython experiments/exp_018_ai_rag_workflow.py --track graduation --session-dir experiments/ai_memory/graduation/g2-reference-v1 --decision-file .\decision-scope.json
```

每次只恢复一道审核；下次须使用新模板和新哈希。reject立即终止，不继续求解。输入原始字节、代码、依赖、工作区或预算发生变化时，应新建会话；不能继承旧批准。更换成内容相同但路径不同的请求也不能作为显式恢复覆盖。

## 结果与失败如何判读

`graduation_run/request.json`保存原始输入，fixed.json/joint.json保存两份真实生产与维护计划，manifest.json绑定严格产物清单及哈希，report.md汇总目标/状态。会话最终report.md另附课题与验收范围。结论审核前会从快照重建计划，重新检查G1约束、独立总延期、原始求解目标及元数据，不能只相信报告中的“PASS”。

非法或无解状态没有接受指标；诊断保留且不重试。合法FEASIBLE保留为限时可行参考，不宣称最优；只有两方均OPTIMAL时才检查联合最优不大于固定最优。生产makespan与总延期单独保存，不把维护结束算入生产makespan。

完成三审后，合法参考运行可显示COMPLETED/GRADUATION_REFERENCE，但毕设研究状态仍为not_achieved，CLI返回2。正式固定/联合比较、最终算法与完整任务书确认仍待完成；大创物流/RL要求也不据此满足。失败返回1，待人审返回3，只读status返回0。

当前输入上已检查的技术项与正式科研验收分开保存；冻结contract和原始静态选择器的验收逻辑未重写。该路线不承诺跨平台实机监督均已验证，Linux真实进程路径仍依赖Linux CI。

## 验证记录

本轮backend、graph/session、CLI测试及完整回归、独立审查见`review_status.md`和`superpowers/plans/2026-10-25-graduation-workflow-progress.md`。真实会话首次停scope；后续用户分别明确批准scope、evidence，现已完成两份参考求解并停在conclusion，尚未批准结论、供应商调用0。临时synthetic测试决定不构成真实会话放行。

接入阶段完整回归525项通过、覆盖率88.71%；随后补强13项边界反例，最新完整回归538项通过、覆盖率88.82%（门槛80%）。运行代码未改，基础001/002的前轮通过记录和既有证据保留。

已用已测源码`516f067`创建本地演示会话`experiments/ai_memory/graduation/g2-reference-v1`，退出码3，WAITING_HUMAN/scope，供应商调用0，尚未求解且决定模板为空。原始请求哈希、会话code_hash及scope中的session_spec_hash均核对一致。阅读[本地scope待审材料](../experiments/ai_memory/graduation/g2-reference-v1/review-request.json)；该目录为本地忽略产物，其他机器应按上文新建会话，不能假定随Git克隆存在。

上述为首次创建记录；当前待审阶段已是conclusion。实际固定/联合总延期4/0，均OPTIMAL、下界4/0、gap0，保存计划已重检；详见[当前人审摘要](graduation_reference_review.md)。本地review-request.json始终表示最新待审阶段，不是旧scope材料的固定文件名。

独立审查未发现Critical/Important问题。此前低优先级回归保护建议已在用户要求继续后补入13项反例：超限输入、缺失/额外文件、重算临时测试哈希后的非法维护/目标元数据/延期；后端30项专项及上述538项完整回归已通过，运行代码未变。
