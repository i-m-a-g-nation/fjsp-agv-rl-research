# FJSP-AGV-RL Research

English version: [README.md](README.md)

**先看 [START_HERE.md](START_HERE.md)：项目当前状态、最近证据与下一步统一在这一页维护。** 找代码看[项目结构导航](docs/project_structure.md)，选实验看[实验使用说明](experiments/README.md)。本页只保留环境、入口和稳定约定。

本项目研究柔性作业车间调度（FJSP），以 Phase 1 静态平台和 Phase 2A 动态事件、冻结执行历史及重调度为基础。阶段边界与用户放行的扩展以 [AGENTS.md](AGENTS.md) 和上述状态入口为准。

## 环境与检查

创建项目专用 Conda 环境，不使用 `base`：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_env.ps1
```

默认创建到项目内 `.conda-env`；使用自定义位置时，先设置 `FJSP_CONDA_ENV`。本机环境路径不要写进版本化文件。

需要复现已核对的版本时，用[`environment-phase1-repro.yml`](environment-phase1-repro.yml)在新前缀创建环境，其中包含核心、dev与research依赖。具体命令和已验证边界见[Phase 1复现清单](docs/reproducibility_phase1.md)。它是版本约束，不是跨平台二进制锁文件。

运行本地检查链：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_checks.ps1
```

本地与CI均通过`scripts/check_experiments.py`运行001–004和动态检查链，再执行完整测试。给PowerShell入口加`-Heavy`可运行完整基准矩阵及新结果报告；CI也提供显式的`full_benchmarks`手动选项。每批结果写入新目录。

逐项运行时，先核对 Python 路径：

```powershell
.\.conda-env\python.exe -c "import sys; print(sys.executable)"
.\.conda-env\python.exe experiments\exp_001_toy_instance.py
.\.conda-env\python.exe experiments\exp_002_solver_check.py
.\.conda-env\python.exe -m pytest
```

输出必须指向专用环境。使用 `FJSP_CONDA_ENV` 时，将 `.\.conda-env\python.exe` 换成对应环境的 Python。较大的 benchmark、动态、毕设与控制器实验见[实验使用说明](experiments/README.md)。

离线实验无需模型配置。调用模型时，在**当前工作树根目录 `.env`** 填写密钥，模板为 [`.env.example`](.env.example)，操作见[模型接口说明](docs/model_interface.md)。本机 `.env` 被 Git 忽略，不随分支合并复制到其他检出目录。

## 代码与数据

| 位置 | 职责 |
|---|---|
| [`src/data/`](src/data/)、[`src/scheduling/`](src/scheduling/)、[`src/solvers/`](src/solvers/) | FJSP 实例、编解码、统一结果、合法性检查、规则与 CP-SAT |
| [`src/dynamic/`](src/dynamic/) | 动态事件、状态、冻结历史与重调度 |
| [`src/graduation/`](src/graduation/) | 毕设维护/延期模型、参考求解及策略工具 |
| [`src/ai_workflow/`](src/ai_workflow/) | 科研要求、文献依据、预算、会话及审核/控制器路线 |
| [`src/vis/`](src/vis/) | 甘特图 |
| [`instances/`](instances/README.md) | smoke 算例、FJSPLib 子集、来源与参考界 |
| [`experiments/`](experiments/README.md) | 可执行实验、协议与保存证据 |
| [`tests/`](tests/)、[`scripts/`](scripts/) | 测试、环境与检查脚本 |

更细的任务到文件映射见[项目结构导航](docs/project_structure.md)。理解静态底座可看 [Phase 1 代码导读](docs/code_walkthrough_phase1.md)与[复现清单](docs/reproducibility_phase1.md)。

## 调度与证据约定

实例采用 `jobs[job_id][op_id] = [(machine_id, processing_time), ...]`。所有调度算法返回包含 `ScheduleRecord` 的统一 `ScheduleResult`，结果通过对应合法性检查后才能记为有效。

检查器核对工序恰好一次、先后约束、机器无重叠、可选机器、加工时间和 makespan。CP-SAT 使用可选工序-机器 interval、ExactlyOne、precedence 与 `NoOverlap`，并设置时限。只有 `OPTIMAL` 能证明本地最优，`FEASIBLE` 只能作为限时可行参考；达到上游 UB 不等于本地最优证明。

| 要查的证据 | 入口 |
|---|---|
| 静态 benchmark 来源与结果文件 | [算例说明](instances/README.md)、[保存结果](experiments/results/README.md) |
| 动态协议与连续事件重放 | [Phase 2A 协议](docs/phase2a_experiment_protocol.md)、[顺序验证](docs/phase2a_sequential_validation.md) |
| 毕设与科研执行 | [毕设工作流](docs/graduation_workflow.md)、[通用工作流](docs/research_workflow.md)、[控制器说明](docs/research_controller_validation.md) |
| 工程验证与课题验收的区别 | [Phase 2A 自检](docs/phase2a_acceptance.md)、[研究验收对照](docs/research_acceptance_map.md) |

**验证报告、带日期文档和保存的结果表都是对应源码、输入及配置下的历史快照。** 当前状态统一看 [START_HERE.md](START_HERE.md)；声称重新验证通过前，应实际重跑对应检查。[`docs/superpowers/`](docs/superpowers/) 保存开发规格、计划和过程历史，日常使用无需逐份阅读。

## 模型与 CI

- Phase 1 模型：[英文源码](docs/math_model_phase1.tex) / [PDF](docs/math_model_phase1_en.pdf)；[中文源码](docs/math_model_phase1_zh.tex) / [PDF](docs/math_model_phase1_zh.pdf)。
- Phase 2A 模型：[源码](docs/math_model_phase2a.tex) / [PDF](docs/math_model_phase2a.pdf)，另有[中文阅读说明](docs/phase2a_dynamic_model_zh.md)。
- [CI 配置](.github/workflows/ci.yml)：metadata audit、报告生成、动态 smoke 和 pytest coverage；最低覆盖率为 80%。最近本地验证只在 [START_HERE.md](START_HERE.md) 维护。

Random 实验记录种子，求解器对照记录时限和 worker 设置。保留旧结果，结合 manifest 和原始证据阅读报告。优先保证正确性与可复现性。
