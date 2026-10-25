# 毕设参考求解接入受监督工作流

用户“继续”承接已说明的下一步：将G1检查器、G2固定/联合求解接入现有LangGraph持久会话。复用既有scope/evidence/conclusion三道人审、代码/依赖身份、累计预算和进程树监督；原静态生成路线、动态协议路线及冻结课题契约不扩大权限。

选择新增专用离线路线，而非让通用模型生成维护代码。后者扩大不受控执行面；直接运行021又缺少会话审核。新路线只调用已验证G2后端，无RAG、网络、模型、fallback或代码生成，无AGV/RL/G3正式协议。

## 输入及输出

`--track graduation --graduation-request FILE`。JSON为自包含请求：schema_version=1、request_id、tasks、num_machines、maintenance、solver(time_limit,num_workers,seed)。严格拒绝未知/重复字段、NaN/Infinity、bool整数和不支持的模型项，固定与联合均执行。任务<=50、机器<=10、每次求解时间(0,30]秒、线程1..4、seed0..2^31-1，请求<=1MiB；数值上界沿用G2。默认提供者调用和token预算为0，主动执行预算仍由现有监督控制。

输入原始字节哈希、首版假设、全部任务/维护/配置参与scope和evidence审核。会话创建/恢复及执行前核对原文件哈希；原JSON改变、代码改变、错误track或混合论文/协议/在线选项均拒绝。初始scope只准备审核材料，不求解，不生成真实批准。

输出保存在会话内graduation_run/：原始request.json、fixed.json、joint.json、report.md、manifest.json。计划包含真实生产、维护、原始目标、下界、按延期计算的gap和状态。域合法性与求解元数据再次验证；非法结果无接受指标，失败诊断保留。FEASIBLE保持FEASIBLE，不自动升级最优；只有双方OPTIMAL时检查joint<=fixed。失败不重试，不把一条成功记录当作完整成功。

conclusion审核前及恢复时重新核对manifest哈希、严格产物清单与各文件字节哈希，再从原始输入重建两模式结果，复查G1合法性和元数据。研究状态始终not_achieved；可以记录当前输入的技术检查，但正式对照、最终算法、完整任务书及大创要求不自动认证。

## 验收

测试覆盖严格请求、真求解器4/0、FEASIBLE/非法/失败结果、篡改产物/原输入、三审暂停与拒绝、跨进程恢复与预算、无RAG/模型、错误track及CLI混合输入提前拒绝。真实CLI只创建scope待审会话；测试中模拟决定明确标注synthetic，不生成任何真实人审批准。全量测试、基础001/002、一次最终独立审查和文档交付后保留当前分支。
