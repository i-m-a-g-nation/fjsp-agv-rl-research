# Phase 1 可复现性清单

## 2026-10-29 有限交付补齐计划

用户在DS只读评审后选择开始执行有限收尾，研究主线仍为毕设参考异常验证和大创领域模型。沿用当前隔离工作树，不新增人维护的Markdown。设计取舍：只为既有绘图行为补测试、保存已发生CI的精简长期证据、准备下一次独立开发验证范围；不重构结果容器、绘图库或CI平台，也不把重型矩阵作为每次提交必跑项。

- [x] 绘图专项：手工可核对的合法双机计划，检查输出PNG、机器行/任务区间/标签，以及显示和保存失败时的图资源释放。仅有可复现缺陷才修改绘图实现；不改调度语义或checker。
- [x] CI证据：保存`3bb926d`对应run40821350521的GitHub元数据、默认实验回执/必要产物、精简测试结尾和文件哈希；明确2040通过/90.84%及heavy skipped，不把旧1708测试计数当最新结果。旧档案不改写。
- [x] 下一次开发验证提案：5个历史ERROR请求各比较原配置/关闭预处理（10次），另用可枚举双任务固定/联合在两配置下验证（4次）。提议全新60主动秒、每次1秒/单线程/seed42、0模型调用，仅一次尝试；旧600秒账本保持锁定。准备不创建新执行预算或批准记录，也不调用求解器。
- [ ] 运行专项及相关回归、现有001/002和完整pytest；检查原来源/旧档案、索引和密钥，再提交已授权公开分支并验证CI。实际重型远程实验和新补救求解均不在本轮执行。

实施顺序：先绘图测试和真实缺陷修复，再CI资料和补救提案；最后统一验证/提交。无需给既有人类说明文本写实现镜像测试，提案只读生成器则核对固定分母、禁止执行和来源身份。所有范围外缺口继续保留，不追求评分上升。

执行结果：绘图反例先复现显示路径和保存失败路径两处figure泄漏，再以`try/finally`只关闭本函数创建的图；3项绘图测试通过，001/002重新执行、14份计划合法，生成图已查看。调度算法、checker和27份毕设基线源码未改。旧CI ZIP的SHA256与GitHub发布digest一致，28份ZIP成员与下载结果一致；43份保存计划静态层重检、756项历史源码身份核对通过，9份长期资料见[CI归档](../../experiments/archive/phase1_ci_3bb926d_v1/summary.txt)。动态语义、一般最优性和研究创新不由这些静态层检查认证。

本地完整回归2049通过、2跳过、13条第三方警告，776.72秒；独立审查随后发现归档换行保护遗漏和嵌套manifest排除过宽，均已修复。嵌套反例先失败，修复后绘图/提案/动态批处理共28项通过；独立复核2项反例及字节/来源/提案身份通过，未报告剩余重要问题。新的完整远程验收以本次提交PR Checks为准，不把上一提交3bb926d的CI当作新修复的CI。最终本地材料和测试记录见[交付验证](../../experiments/archive/phase1_delivery_followup_v1/validation_record.json)。本轮没有新的补救求解、正式网格、训练或模型调用；常规测试和001/002包含既有微型求解器验证。

## 2026-10-27 首次远程CI与检出身份修复

在用户明确授权公开当前分支后建立[草稿PR #1](https://github.com/i-m-a-g-nation/fjsp-agv-rl-research/pull/1)，不合并main。[首次Linux运行](https://github.com/i-m-a-g-nation/fjsp-agv-rl-research/actions/runs/40474551395)的依赖安装与共享实验入口通过，完整测试为1669通过、18失败、19设置错误。源码绑定使检出换行差异暴露出来：当前025/026的`phase1_v2`参考将三个核心文件绑定为CRLF字节，而Git中为LF，Linux默认检出后哈希不符。

`.gitattributes`现将Python源码默认固定为LF，并将`src/data/instance.py`、`src/scheduling/encoding.py`、`src/scheduling/feasibility.py`明确固定为CRLF，以保留已有参考绑定。历史实验档案继续使用`-text`，不改写其哈希、不忽略来源检查。新增测试真实执行Git暂存与重新检出，分别覆盖`core.autocrlf=false/true`；修复前两个测试均失败，修复后连同Phase 1证据、穷举和入口回归共41项通过。修复后的远程结果以PR对应提交的Checks为准；下文各轮本地验收数字是历史记录。

## 2026-10-27 评审后收口计划

用户在评审答复后要求继续，采用已说明的有限收口方案；当前基线为 `fd89472`，在现有工作树内执行。沿用本文记录，不新增计划Markdown。范围不包含新研究算法或Phase 2A公开库适配。

- [x] EAM证据：在003/004/005/010注册既有EAM规则；先用手算反例和真实CLI证明遗漏，再补注册。011按输入自动汇总，增加端到端测试保证EAM进入报告。完整矩阵保留其他算法与seed，输出新目录。
- [x] 检查入口：本地和CI共用显式的轻量验收脚本，覆盖001–004和既有动态链；重型模式另外运行005/009/010/011。先验证缺少入口和错误传播，再实现；拒绝复用非空输出目录，不执行模型API。
- [x] 固定环境：保存核心、dev及research依赖的传递版本约束，新建本机专用Conda前缀验证安装及静态复跑；不改现有科研环境。不把同机新环境称为跨机器复现。
- [x] 文档和验收：补EAM的顺序/平局语义，同步当前审查摘要和结果索引，保留历史数字；运行完整回归、归档哈希和独立复核，最终本地提交。

接口依赖：实验注册表→矩阵→011质量报告→验收脚本；新约束文件→新环境安装→同一验收入口。原025/026科研源码绑定不涉及这些静态实验入口，保持原参考身份检查。审查重点是EAM被误接成EFT、输入/报告路径混用、失败后仍继续、旧结果覆盖、环境重建与原环境混淆。

执行记录：5项EAM注册/报告反例先失败，补齐后相关28项通过。统一入口初次集成暴露子目录使实例ID与BKS不一致；决定固定使用仓库FJSPLib根目录并允许数量抽样，避免在验收入口扩展自定义数据与参考表协议。抽样模式在运行前由声明的文件清单生成参考表，011仍检查该表的完整覆盖，不能按成功行缩小分母。自定义实验继续使用已有独立脚本显式提供匹配参考表。统一入口及失败传播测试4项通过。

独立代码审查未发现阻断问题。依据审查补齐新环境中的research依赖，防止默认前缀只能跑静态实验而不能运行研究测试。另一项边界保留：`input_scope.json`是运行前输入快照，不是对并发文件修改的持续监视；验收期间保持源码和数据固定。每个实验sidecar独立保存实际问题，不能将快照描述为隔离锁。

### 本轮实际验收

- 原研究环境通过完整本地检查链：**1704通过、2跳过、13条第三方警告，覆盖率91.16%，1048.27秒，退出码0**。这包含共用实验入口及全量pytest。
- 同机新Conda前缀安装了清单要求的核心、dev与research依赖，76项版本全部吻合，`pip check`通过；新环境的定向静态/入口回归**421项通过，27.59秒**。本轮没有在新环境再次执行完整研究测试，也没有跨机器或远程CI成功记录。
- 两环境均执行14个入口，各保存763份计划（757静态计划、6份动态结果的静态层），每批65371道工序、34条CP诊断；项目重检和不导入项目检查器的独立实现均为零差异。动态事件、冻结历史及release约束仍由对应入口的领域检查器负责。
- 两环境的729份非CP计划完全相同；34条限时CP结果有4条状态或目标值不同。这符合墙钟限时求解的已知复现边界，不能把版本固定解释为CP结果逐位一致，也不据此比较环境性能。
- EAM新增30条基准结果，完整启发式矩阵由420增为450条。EAM平均`(makespan-UB)/UB = 0.461360`，只表示相对公开上界的质量，不能解释为证明最优的gap。新中英文模型PDF已编译并逐页检查，历史数值保留并明确标注。
- 本轮未更改核心求解器、检查器或025/026科研参考绑定源文件；现有参考身份仍有效。没有新增人工维护的Markdown，生成的实验报告随证据归档。

[本轮验收记录](../../experiments/archive/phase1_closeout_v1/validation_record.json)、[环境对比及CP差异](../../experiments/archive/phase1_closeout_v1/environment_comparison.json)、[原环境独立重检](../../experiments/archive/phase1_closeout_v1/native/independent_replay.json)、[新环境独立重检](../../experiments/archive/phase1_closeout_v1/rebuilt/independent_replay.json)。

这次关闭了EAM对照证据、现有文档同步、检查入口一致性和本机环境重建缺口。仍保留的边界是跨机器/远程CI验证、输入快照不监视并发修改，以及未作为本轮范围扩展的Gantt专测、Phase 2A公开库/公开动态基线。下一阶段回到具体研究假设和实验闭环，遇到新反例再针对性加固。

### 本地与CI共用入口

```powershell
$Python = if ($env:FJSP_CONDA_ENV) { Join-Path $env:FJSP_CONDA_ENV 'python.exe' } else { '.\.conda-env\python.exe' }
& $Python -c "import sys; print(sys.executable)"
& $Python scripts/check_experiments.py
& $Python scripts/check_experiments.py --heavy
```

默认执行001–004、012、014–017。`--heavy`再执行005（启发式批量）、009（单线程/seed42/每例3秒/一次）、010（含EAM、全部原有算法和seed）、011、013；报告读取本批新结果。`--heavy --max-files 1`可验收明确的小子集，其结果不能充当完整30实例矩阵。输出默认新建在`experiments/runs/`，也可用`--output-dir`指定尚不存在的路径；保留`checks.json`及每个入口的日志，任一子进程失败即停止。

`scripts/run_checks.ps1`调用同一实验入口再运行完整pytest；加`-Heavy`启用完整矩阵。CI常规任务运行轻量入口和完整测试，手动`full_benchmarks`可增加重型任务，并保存实验产物。配置已更新，不代表本轮实际获得了远程CI成功记录。

### 固定版本环境

在仓库根目录为新环境执行；若默认前缀已经存在，选择另一个空前缀：

```powershell
$ReproEnv = Join-Path (Get-Location) '.conda-env'
conda env create --prefix $ReproEnv --file environment-phase1-repro.yml
$env:FJSP_CONDA_ENV = $ReproEnv
$Python = Join-Path $ReproEnv 'python.exe'
& $Python -c "import sys; print(sys.executable)"
& $Python -m pip check
& $Python scripts/check_experiments.py --heavy
```

该清单固定Python 3.11.15，并通过`requirements/phase1-py311.constraints.txt`约束核心、dev和research的76项传递依赖版本，包括OR-Tools 9.15.6755。原`environment.yml`仍是滚动开发安装方式。此处约束是Windows x64下核对的发行版本，不包含所有Conda构建号、轮子哈希或跨平台解析锁；不能保证不同系统的底层二进制相同。环境文件本身也不包含API密钥。

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

最终完整回归：**1696通过、2跳过、13条第三方警告，源码覆盖率91.16%，676.53秒，退出码0**。沿用现有Markdown记录，没有新增Markdown文件。测试和日志见[验收记录](../../experiments/archive/phase1_hardening_v1/validation_record.json)及[完整测试输出](../../experiments/archive/phase1_hardening_v1/pytest_final.log)。

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

完整数据见[本轮运行摘要](../../experiments/archive/phase1_hardening_v1/summary.json)、[独立数值重检](../../experiments/archive/phase1_hardening_v1/independent_replay.json)、[新旧研究参考比较](../../experiments/archive/phase1_hardening_v1/reference_equivalence.json)、[归档文件哈希](../../experiments/archive/phase1_hardening_v1/archive_manifest.json)。归档中的路径、解释器和时刻是实际运行信息；复制归档用于只读检查，不表示移动后的控制器SQLite可以原地续跑。
