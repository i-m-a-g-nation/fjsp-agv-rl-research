# FJSP-AGV-RL Research

English version: [README.md](README.md)

本项目当前处于 **Phase 2A：动态柔性作业车间调度（FJSP）最小底座**。
Phase 2A 在已经验证的 Phase 1 静态 FJSP 底座上加入动态事件和确定性
重调度；AGV、运输时间、RL训练和图神经网络仍为后续阶段，用户另行放行的毕设增量见下。

科研辅助工作流提供独立的大创、毕设要求配置和受限静态实验，默认离线；它不代表已经实现两个研究课题。运行方式、状态解释与人工审核点见 [科研辅助工作流说明](docs/research_workflow.md)。

用户已批准毕设G1数据/延期/维护检查、G2固定/联合参考求解及独立枚举。现有`--graduation-request`专用离线路线已将参考后端接入三道人审，重新核对保存的维护计划，不经过RAG/模型/代码生成。见[毕设三审使用说明](docs/graduation_workflow.md)、[G2验证](docs/graduation_g2_validation.md)。

后续已起草[G3参考对照协议](docs/graduation_g3_protocol_draft.md)及[RL方案](docs/graduation_rl_design_draft.md)。其中[R1纯Python无训练环境](docs/graduation_rl_environment_validation.md)已实现并验证动作/维护/奖励；没有Gym/PPO适配器或训练策略，G3协议仍为未冻结/未执行设计，完整任务书算法要求仍待核对。

## 当前范围

Phase 1 已覆盖：

- FJSP 实例结构：`FJSPInstance`、Job、Operation、MachineOption
- 调度结果结构：`ScheduleRecord`、`ScheduleResult`
- 半主动解码：由 `(job_id, op_id, machine_id)` 生成带时间的调度
- Feasibility Checker：检查工序覆盖、工序顺序、机器容量、机器可行性、加工时间和 makespan
- 简单启发式 baseline：FIFO、SPT、Earliest Finish Time、Random
- 严格 dispatching rule：DispatchFIFO、DispatchSPT、DispatchEFT、DispatchMWKR、DispatchMOPNR、DispatchRandom
- OR-Tools CP-SAT baseline：OptionalIntervalVar、ExactlyOne、Precedence、NoOverlap、makespan 最小化
- CP-SAT 诊断：solver status、objective bound、relative gap、solver wall time
- 官方 FJSPLib 静态子集：30 个 tracked 上游文件，覆盖 6 个来源系列
- 统一实验 CSV 记录和元数据审计
- Matplotlib Gantt 图输出
- Phase 1 数学建模 LaTeX 文档
- Phase 2A 动态 FJSP LaTeX 建模文档
- Phase 2A 动态 FJSP 中文说明文档
- pytest 单元测试
- Phase 2A 动态事件、动态状态、动态合法性检查、冻结记录快照和最小重调度 baseline

当前阶段明确不做：

- AGV 运输、路径规划、避碰
- 运输时间建模
- 强化学习、PPO、DQN、多智能体
- 图神经网络
- 多目标优化
- 复杂论文算法完整复现

## 目录结构

```text
src/
  data/          FJSP 实例结构和 benchmark loader
  scheduling/    编码、解码、合法性检查
  solvers/       baseline、dispatching rule、兼容门面和 OR-Tools CP-SAT
  dynamic/       Phase 2A 动态事件、状态和重调度 baseline
  vis/           Gantt 图绘制
tests/           pytest 测试
experiments/     实验脚本、CSV 结果和图像产物
instances/       本地 smoke 文件和真实 FJSPLib 子集
docs/            代码说明、审查状态、数学模型
notes/           开发笔记和方案讨论
papers/          文献索引
```

## 快速运行

推荐使用项目专用 Conda 环境，不要使用 `base` 环境：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_env.ps1
```

常用检查：

推荐先跑本地 CI 风格检查链：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_checks.ps1
```

也可以逐项运行：

```powershell
.\.conda-env\python.exe experiments\exp_005_benchmark_batch.py
.\.conda-env\python.exe experiments\exp_009_cpsat_benchmark_matrix.py
.\.conda-env\python.exe experiments\exp_010_heuristic_benchmark_matrix.py
.\.conda-env\python.exe experiments\exp_011_heuristic_quality_report.py
.\.conda-env\python.exe experiments\exp_012_benchmark_metadata_audit.py
.\.conda-env\python.exe -m pytest
```

如果使用自定义 `FJSP_CONDA_ENV`，把 `.\.conda-env\python.exe` 换成对应环境里的 Python。

## 当前实验状态

真实 FJSPLib 子集来自 ScheduleOpt 官方仓库，并保留 CC-BY-SA-4.0 归属说明。
当前 tracked 上游文件数为 30。

| FJSPLib 实例 | 规模 | 当前启发式最佳值 | CP-SAT 10s | FJSPLib UB |
|---|---:|---:|---:|---:|
| `fattahi1` | 2 x 2 | 66 | 66 `OPTIMAL` | 66 |
| `fattahi2` | 2 x 2 | 107 | 107 `OPTIMAL` | 107 |
| `fattahi3` | 3 x 2 | 221 | 221 `OPTIMAL` | 221 |
| `fattahi4` | 3 x 2 | 367 | 355 `OPTIMAL` | 355 |
| `fattahi5` | 3 x 2 | 119 | 119 `OPTIMAL` | 119 |
| `fattahi6` | 3 x 3 | 330 | 320 `OPTIMAL` | 320 |
| `fattahi7` | 3 x 5 | 397 | 397 `OPTIMAL` | 397 |
| `fattahi8` | 3 x 4 | 273 | 253 `OPTIMAL` | 253 |
| Chambers-Barnes `mt10c1` | 10 x 11 | 1225 | 927 `FEASIBLE` | 927 |
| Chambers-Barnes `mt10cc` | 10 x 12 | 1121 | 908 `FEASIBLE` | 908 |
| Chambers-Barnes `mt10x` | 10 x 11 | 1173 | 918 `FEASIBLE` | 918 |
| Dauzere-Peres `01a` | 10 x 5 | 3056 | 2586 `FEASIBLE` | 2505 |
| Dauzere-Peres `02a` | 10 x 5 | 2443 | 2534 `FEASIBLE` | 2228 |
| Dauzere-Peres `03a` | 10 x 5 | 2413 | 2602 `FEASIBLE` | 2228 |
| Dauzere-Peres `04a` | 10 x 5 | 3070 | 2591 `FEASIBLE` | 2503 |
| `kacem1` | 4 x 5 | 11 | 11 `OPTIMAL` | 11 |
| `kacem2` | 10 x 7 | 12 | 11 `OPTIMAL` | 11 |
| `kacem3` | 10 x 10 | 8 | 7 `OPTIMAL` | 7 |
| `kacem4` | 15 x 10 | 12 | 15 `FEASIBLE` | 11 |
| Hurink edata `ft06` | 6 x 6 | 55 | 55 `OPTIMAL` | 55 |
| Brandimarte `mk01` | 10 x 6 | 44 | 40 `OPTIMAL` | 40 |
| Brandimarte `mk02` | 10 x 6 | 30 | 28 `FEASIBLE` | 26 |
| Brandimarte `mk03` | 15 x 8 | 204 | 220 `FEASIBLE` | 204 |
| Brandimarte `mk04` | 15 x 8 | 77 | 62 `FEASIBLE` | 60 |
| Brandimarte `mk05` | 15 x 4 | 185 | 180 `FEASIBLE` | 172 |
| Brandimarte `mk06` | 10 x 15 | 67 | 74 `FEASIBLE` | 57 |
| Brandimarte `mk07` | 20 x 5 | 160 | 159 `FEASIBLE` | 139 |
| Brandimarte `mk08` | 20 x 10 | 531 | 523 `FEASIBLE` | 523 |
| Brandimarte `mk09` | 20 x 10 | 341 | 340 `FEASIBLE` | 307 |
| Brandimarte `mk10` | 20 x 15 | 243 | 302 `FEASIBLE` | 193 |

对 `FEASIBLE` 行，只能说明本地 CP-SAT 在时限内找到合法可行调度，不能说明已经证明最优。

## 最新验证

- `exp_005_benchmark_batch.py`：32 个 discovered 文件全部 feasible
- `exp_009_cpsat_benchmark_matrix.py`：120/120 个 CP-SAT 矩阵调度全部 feasible
- `exp_010_heuristic_benchmark_matrix.py`：420/420 个启发式调度全部 feasible
- `exp_011_heuristic_quality_report.py`：30 实例 UB-relative 质量报告已刷新
- `exp_012_benchmark_metadata_audit.py`：30/30 个 tracked 文件、LB/UB 行和 loader 校验通过
- `exp_013_cpsat_report.py`：生成 CP-SAT Markdown 报告，区分 `OPTIMAL` 与时限内 `FEASIBLE`；当前 15/30 个 best row 达到上游 UB，13/30 个本地证明 `OPTIMAL`，2/30 个达到 UB 但未本地证明最优
- `exp_014_dynamic_reschedule_smoke.py`：3 个 Phase 2A 动态重调度 smoke 场景全部 feasible
- `exp_015_dynamic_event_file_check.py`：3/3 个动态事件 JSON 文件可加载、非空、时间线非递减
- `exp_016_dynamic_event_file_reschedule.py`：3/3 个动态事件 JSON 文件驱动的重调度场景全部 feasible
- `exp_017_phase2a_dynamic_report.py`：汇总 exp_014/015/016，Phase 2A 动态链条总览 PASS
- `pytest`：2026-10-25 工作流加固、动态验证及EAM补齐后 364 passed
- 全部 `src` coverage：88.11%，包含科研辅助工作流与受监督子进程，CI 门槛仍为 80%
- 科研入口现在默认持久化范围、证据与结论三道人工审核；累计执行、供应商调用与输出预占预算跨恢复保留
- 文献陈述逐项绑定原文片段与位置；有可靠对应关系时显示 PDF 物理页码。缓存绑定目标论文，文字匹配仍须人工判断科学依据
- [固定 Phase 2A 实验协议](docs/phase2a_experiment_protocol.md)：243 次既有动态基线运行全部合法；27 配置对应 23 个不同场景，独立目录复跑摘要一致。[双课题验收对照](docs/research_acceptance_map.md)继续列出研究缺口
- [连续事件顺序重放](docs/phase2a_sequential_validation.md)：9 条运行、18 个时间戳批次合法，逐次冻结上一份计划中的执行历史；同一时刻事件合并后只调度一次，失败前缀不当作最终结果
- [Phase2A交付自检](docs/phase2a_acceptance.md)：补齐此前遗漏的EAM基线，001/002中toy makespan为11；EAM与EFT分开定义，既有019/020协议不变。[毕设首版模型](docs/graduation_model_draft.md)的 G1 基础及 G2 参考求解已有，G3正式比较与最终验收仍待推进

当前 30 实例质量报告中，`DispatchFIFO` 的跨实例平均 best gap 最低：

| 算法族 | 平均 best gap | 最大 best gap |
|---|---:|---:|
| DispatchFIFO | 0.151281 | 0.370370 |
| DispatchMWKR | 0.158760 | 0.364924 |
| DispatchMOPNR | 0.193880 | 0.466667 |
| EarliestFinishTime | 0.392423 | 1.384615 |
| DispatchEFT | 0.405199 | 1.384615 |

## 数学建模文档

英文版：

- [docs/math_model_phase1.tex](docs/math_model_phase1.tex)
- [docs/math_model_phase1_en.pdf](docs/math_model_phase1_en.pdf)

中文版：

- [docs/math_model_phase1_zh.tex](docs/math_model_phase1_zh.tex)
- [docs/math_model_phase1_zh.pdf](docs/math_model_phase1_zh.pdf)

代码导读和可复现性清单：

- [docs/code_walkthrough_phase1.md](docs/code_walkthrough_phase1.md)
- [docs/reproducibility_phase1.md](docs/reproducibility_phase1.md)

数学模型包含集合、参数、决策变量、机器选择约束、工序顺序约束、机器容量约束、
makespan 定义，以及 feasibility checker 与数学约束之间的对应关系。

## CI / Coverage

仓库包含最小 GitHub Actions workflow：

- [.github/workflows/ci.yml](.github/workflows/ci.yml)

CI 会安装 dev 依赖、运行 benchmark metadata audit、生成 CP-SAT report、刷新 Phase 2A 动态报告链，并执行：

```powershell
python -m pytest --cov=src --cov-report=term-missing --cov-fail-under=80
```

## 威胁有效性

| 风险 | 当前缓解方式 |
|---|---|
| CP-SAT 限时结果可能只是 feasible 而非 proved optimal | 报告保留 `FEASIBLE`、bound、gap、UB gap 和 local proof 字段 |
| benchmark 子集仍是中等规模 | 每次扩展先跑 `exp_012`，并记录来源、LB/UB |
| Random 启发式受 seed 影响 | 使用固定 seeds，并报告范围而非隐藏单次结果 |
| 上游参考界不是本地证明 | 报告区分“达到 UB”和“本地证明 `OPTIMAL`” |
| Phase 2 主题容易提前混入 | Phase 2A 只允许动态事件和重调度；AGV、RL、GNN、运输和多目标优化继续排除 |

## 维护建议

当前代码不需要推倒重构。更合适的路线是继续小批量扩展：

- 分批扩展 FJSPLib 子集，并每批运行 metadata audit、heuristic matrix、CP-SAT matrix
- 优先观察更大静态实例上的求解行为，再决定是否增加新规则
- 保持 feasibility checker 独立、严格、不可绕过
- 暂时不要引入 AGV/RL/GNN/运输时间，避免复杂度过早失控

项目优先级保持：

```text
正确性 > 可维护性 > 性能
```
