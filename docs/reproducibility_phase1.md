# Phase 1 可复现性清单

## 2026-10-27 加固方案与执行记录

用户已授权依据本轮评估加固并重新评估；沿用本页记录，不新增进度 Markdown。

**目标与设计：**保留静态 FJSP 模型和已有算法含义，修复输入、结果身份和实验留痕的边界。
采用严格、深度不可变的实例与独立结果校验；不自动修复坏数据，不削弱约束。
继续扩展现有接口，比另建平行框架更容易保证动态及毕设兼容；只在调用者必须提供原始实例处收紧接口。
不扩展 AGV、奖励函数、训练器或课题范围。历史结果是旧源码快照，不覆盖。

**接口与分工：**

- `src/data/instance.py`：所有构造入口严格整数（拒绝 bool）、正加工时间、连续 ID、唯一机器选项和深度不可变；提供 `validate_instance(instance)`。
- `src/data/loader.py`：auto 仅在编号基准唯一时推断，模糊范围必须显式指定；拒绝非法 header 和选项。
- `src/scheduling/feasibility.py`：`check_feasibility(result, *, expected_instance=None)`；坏结构/类型返回违规，原有七项约束不减少。
- `src/scheduling/decoding.py`：先验证 assignment 完整、唯一、顺序与机器合法，再解码。
- `src/solvers/ortools_solver.py`：校验时限、线程和 seed，默认单线程/seed42，保留显式 auto；在结果保存实际求解配置。
- `experiments/common.py`：`run_solver_once` / `run_solver_suite` 必须传 `expected_instance`；运行前独立快照、运行后原始身份与计划双检；所有调用点迁移。
- 实验留痕采用 CSV 旁 JSON sidecar，包含每条完整调度、原始实例、配置、校验结论、输入/源码哈希和运行环境版本；提供独立读取重检，拒绝覆盖既有证据。
- 相关测试先 RED 再 GREEN；固定本次最小反例，追加小实例穷举核对、元变换、坏归档拒绝测试。

**重点审查：**直接构造绕过 factory、输入替换或突变、非整数/非有限字段、重复机器导致假不可行、编号模糊、归档篡改/缺失以及动态/毕设兼容。

- [x] 输入模型及 loader 加固与 RED/GREEN。
- [x] 检查器、解码器加固与 RED/GREEN。
- [x] CP-SAT 参数与独立小例核对。
- [x] 原始实例绑定、完整实验归档及重检，迁移入口。
- [x] 完整测试与原始实验新目录复跑；独立数值实现复核。最终代码复核由主代理完成，未获得新的独立代理审查。
- [x] 更新本页、保存新证据、重新评价；与本轮代码一并提交。

本轮数值复验和重新评价见下方验收记录；历史档案继续保留。

## 模型与边界

Phase 1 表达静态、非抢占 FJSP：所有工件在0时刻可用，每个工件按给定路线依次加工，每道工序在一台可选机器上恰好执行一次，机器容量为1，目标为 makespan。时间为整数，区间采用 `[start, end)`，相接不算重叠。

实例三层均不可变；列表输入会被复制为元组。所有构造入口检查连续编号、正加工时间和唯一机器选项，拒绝 bool、float、NaN/Inf。修改问题应创建新实例。结果本身仍是可构造的容器，必须经过检查器。

通用解析器 `load_benchmark_file` / `load_benchmark_instance` 的 auto 仅接受无歧义编号。仓库 FJSPLib 已声明1起始，因此实验使用 `load_project_benchmark_file` 适配器；该约定只适用于本仓库的指定数据目录。外部副本不能靠文件名推断来源，应明确传 `machine_index_base=1` 或0。动态协议复制原始文件时一并保留编号约定。

`check_feasibility(result, expected_instance=original)` 同时核对原问题和七项调度约束。`run_solver_once` / `run_solver_suite` 的 `expected_instance` 为必填参数；运行前保存独立快照，检测输入替换或突变，整个算法组共用原始问题身份。Python 内任意恶意代码不属于这一数据边界的隔离保证。

CP-SAT 默认单线程、seed42，显式 `num_workers=0` 才启用自动线程；时间限制、seed和线程数均校验并记录。只有 `OPTIMAL` 才能称为当前模型下求解器证明最优；`FEASIBLE` 只是限时可行参考。更大整数或模型超出 OR-Tools 支持范围时明确拒绝。单线程固定seed不能保证不同机器/库版本/负载与墙钟截止下逐位重现。

## 运行和重检

先使用专用环境，并打印实际解释器路径：

```powershell
$Python = if ($env:FJSP_CONDA_ENV) { Join-Path $env:FJSP_CONDA_ENV 'python.exe' } else { '.\.conda-env\python.exe' }
& $Python -c "import sys; print(sys.executable)"
& $Python experiments/exp_001_toy_instance.py
& $Python experiments/exp_002_solver_check.py
```

001–004默认在 `experiments/runs/` 新建独立批次，也支持 `--output-dir`。下面把矩阵结果放在同一新目录；不要复用已有输出文件名：

```powershell
$RunRoot = Join-Path 'experiments/runs' ('phase1-' + [guid]::NewGuid().ToString('N'))
& $Python experiments/exp_012_benchmark_metadata_audit.py --output "$RunRoot/metadata.csv"
& $Python experiments/exp_010_heuristic_benchmark_matrix.py --runs-output "$RunRoot/heuristic.csv" --summary-output "$RunRoot/heuristic-summary.csv"
& $Python experiments/exp_009_cpsat_benchmark_matrix.py --worker-counts 1 --repeats 1 --time-limit 3 --runs-output "$RunRoot/cpsat.csv" --summary-output "$RunRoot/cpsat-summary.csv"
& $Python -c "import sys; from experiments.artifacts import recheck_results_csv; print(recheck_results_csv(sys.argv[1], require_current_sources=True))" "$RunRoot/cpsat.csv"
& $Python -m pytest -q --cov=src --cov-report=term --cov-fail-under=80
```

CSV旁的 `.evidence.json` 保存原实例、完整计划、源文件哈希、求解参数、校验结论和实际运行环境版本。写入拒绝覆盖CSV或其sidecar。重新读取会复算可行性、makespan和诊断一致性；只有指标CSV的旧资料不能据此获得“已重检完整计划”的结论。动态/维护结果仍需对应领域检查器，此静态重检不替代它们。JSON哈希用于检测变化，不是作者身份或不可伪造的最优性证明。

记录依赖版本方便排查差异，并不等于已在另一台机器重建验证。历史档案可以只读重检；要核对本次源码必须启用 `require_current_sources=True`。源码绑定的旧科研批次不能直接在新源码上续跑；兼容性复验应生成新版本证据，保留旧档案。

本地 `scripts/run_checks.ps1` 在检查失败时立即以失败退出；CI和本地链均使用新输出目录，避免覆盖历史结果。CI配置存在不等于本轮已经在GitHub运行成功。

## 历史材料

加固前的30个算例、120条CP-SAT和420条启发式结果保留在 `experiments/results/` 原路径；它们是对应版本下的实验快照。本次新证据和重新评价在上方执行记录登记。数学模型见 `math_model_phase1.tex` / `math_model_phase1_zh.tex`，代码阅读顺序见[Phase 1 导读](code_walkthrough_phase1.md)。后续生产—维护或生产—物流约束须单独建模和验收，不能从静态makespan成绩推出。

## 2026-10-27 验收记录与重新评价

本轮修复了可复现的边界错误：重复机器选项造成求解器假不可行；bool/浮点时间与非法ID进入底层；可变输入及结果自带实例替换原问题；编号含糊时静默偏移；实验只留指标、缺少完整计划；本地检查脚本忽略失败退出码。反例在修复前先失败，修复后通过。没有改变静态调度目标或新增研究算法。

最终完整回归：**1696通过、2跳过、13条第三方警告，源码覆盖率91.16%，676.53秒，退出码0**。沿用现有Markdown记录，没有新增Markdown文件。测试和日志见[验收记录](../experiments/results/phase1_hardening_v1/validation_record.json)及[完整测试输出](../experiments/results/phase1_hardening_v1/pytest_final.log)。

最终源码下重新执行001–004、30实例元数据检查、420条启发式矩阵和30条CP-SAT矩阵。所有入口退出码0；共保存484份计划，项目检查器重检与一份不导入项目检查器/解码器/求解器的标准库实现均通过，共40913道工序、34份求解器诊断，差异0。独立穷举小例测试进一步核对CP-SAT最优值；这些证据不构成一般规模问题的独立最优性证明。

核心源码改变后，旧科研参考的源码绑定按预期拒绝续用。本轮真实重跑025/026并保存 `phase1_v2`，没有放松身份检查或改写旧档案：36份初始/最终/选中参数以及176条策略/规则轨迹与旧版相同，026选择结果相同。026整体摘要包含新的参考诊断身份，因此整体哈希不同；不能宣称所有文件逐字相同。

控制器的五步候选流程完成一次兼容性复跑，活动时间27.829秒、模型调用0，终态恢复未重复训练。共享评分候选的验证均值仍劣于原none策略，程序仍保留原策略。此轮说明基础改动未改变已有比较结论，不是新的算法性能提升。

首轮完整集成曾出现19个失败、19个设置错误，原因是旧参考绑定和一处仍假设实例可变的测试；通过新参考实跑及更新不可变实例测试修复。第一份025参考尝试有两次OSError，失败目录保留在本地 `experiments/runs/phase1-reference-attempt-1`，没有作为成功证据归档。错误原因尚未确定，随后诊断运行及原CLI运行完成；本轮不据此承诺无人值守运行永不发生环境故障。子代理完成分块实现后遇到用量上限，最后集成、代码复核和独立数值复验由主代理执行，不称为新的独立人工或代理审计。

**重新评价：**在静态、整数、非抢占FJSP的明确边界内，Phase 1 已具备可检验、可追溯的研究基础，可继续承接领域扩展。它的职责是保证问题和实验结果可核对，不能代替后续研究设计。

| 后续工作 | 当前基础能支撑什么 | 还需要什么 |
|---|---|---|
| 大创 | 静态生产调度、动态扩展接口、规则/CP参考和结果重检 | 依据计划书验证生产—物流协同模型、AGV/运输约束、对应检查器和正式对照 |
| 毕设 | 共用数据和实验基础，已有生产—维护实现经兼容性回归 | 维护/总延期领域检查、正式算法及独立测试集比较；静态makespan验证不能替代这些 |
| 更深入研究与工作流 | 原问题绑定、可复核归档、预算内候选执行和拒绝劣化候选 | 更广实例和多seed研究设计、独立复现；自动诊断、形成下一假设仍是工作流缺口 |

现有证据只验证本机环境，没有在第二台机器上重新安装复验，也没有本轮GitHub CI成功记录。覆盖率或测试数量不能证明没有剩余缺陷。当前应进入具体研究问题和对照设计；若遇到新反例，再针对性修复基础层。

完整数据见[本轮运行摘要](../experiments/results/phase1_hardening_v1/summary.json)、[独立数值重检](../experiments/results/phase1_hardening_v1/independent_replay.json)、[新旧研究参考比较](../experiments/results/phase1_hardening_v1/reference_equivalence.json)、[归档文件哈希](../experiments/results/phase1_hardening_v1/archive_manifest.json)。归档中的路径、解释器和时刻是实际运行信息；复制归档用于只读检查，不表示移动后的控制器SQLite可以原地续跑。
