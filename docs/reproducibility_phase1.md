# Phase 1 可复现性清单

本文记录 Phase 1 静态 FJSP 实验底座的推荐复现流程。目标是让后续检查时能明确知道：数据来自哪里、实验按什么顺序跑、哪些结果能称为最优、哪些只能称为限时可行。

## 环境

```powershell
.\.conda-env\python.exe -m pytest -q
```

如果使用外部 Conda 环境，将命令中的 `.\.conda-env\python.exe` 替换为对应 Python。当前开发环境使用：

```powershell
D:\2-Dev\Environments\Conda\fjsp-agv-rl\python.exe
```

## 数据完整性

每次新增或移动 benchmark 文件后，先运行：

```powershell
.\.conda-env\python.exe experiments\exp_012_benchmark_metadata_audit.py
```

该审计必须通过三件事：

1. `instances/fjsplib/` 下 tracked 文件存在。
2. `instances/fjsplib_bks.csv` 中有一一对应的 LB/UB 记录。
3. `src/data/loader.py` 能加载每个文件。

不要在审计失败时继续解释实验结果。

## 推荐复现实验顺序

```powershell
.\.conda-env\python.exe experiments\exp_005_benchmark_batch.py
.\.conda-env\python.exe experiments\exp_009_cpsat_benchmark_matrix.py
.\.conda-env\python.exe experiments\exp_010_heuristic_benchmark_matrix.py
.\.conda-env\python.exe experiments\exp_011_heuristic_quality_report.py
.\.conda-env\python.exe experiments\exp_013_cpsat_report.py
.\.conda-env\python.exe -m pytest -q
```

当前默认规模：

| 项目 | 当前值 |
|---|---:|
| tracked FJSPLib 实例 | 30 |
| `exp_005` discovered 文件 | 32 |
| `exp_009` CP-SAT schedules | 120 |
| `exp_010` heuristic schedules | 420 |
| pytest | 159 passed |
| core coverage | 89.72% |

核心 coverage 检查：

```powershell
.\.conda-env\python.exe -m pytest --cov=src --cov-report=term-missing --cov-fail-under=80
```

## CP-SAT 结果解释

CP-SAT 输出有两个层次：

| 状态 | 可以声称 |
|---|---|
| `OPTIMAL` | 本地求解器在当前模型和参数下证明最优 |
| `FEASIBLE` | 本地求解器在时限内找到合法可行调度 |

即使 `FEASIBLE` 的 makespan 达到 FJSPLib UB，也只能写作“达到上游参考 UB 的可行解”，不能写作“本地证明最优”。

`experiments/results/exp_013_cpsat_report.md` 会显式列出：

- FJSPLib LB
- FJSPLib UB
- UB gap
- 是否达到 UB
- 是否本地证明最优
- CP-SAT bound 和 gap

当前报告中，15/30 个 best row 达到上游 UB，其中 13/30 个本地证明 `OPTIMAL`，2/30 个达到 UB 但仍只是限时 `FEASIBLE`。

## 文档与 PDF

数学建模文档源文件：

```text
docs/math_model_phase1.tex
docs/math_model_phase1_zh.tex
```

编译后应刷新：

```text
docs/math_model_phase1.pdf
docs/math_model_phase1_en.pdf
docs/math_model_phase1_zh.pdf
```

编译后至少检查 PDF 文本中包含当前关键数字：`30`、`120`、`420`、`mk10`、`exp_013`。

## CI

GitHub Actions workflow 位于：

```text
.github/workflows/ci.yml
```

CI 会安装 dev 依赖，运行 metadata audit，生成 CP-SAT report，并执行核心 coverage 检查。当前 coverage 门槛为 80%。

## 提交前检查

```powershell
.\.conda-env\python.exe experiments\exp_012_benchmark_metadata_audit.py
.\.conda-env\python.exe experiments\exp_013_cpsat_report.py
.\.conda-env\python.exe -m pytest --cov=src --cov-report=term-missing --cov-fail-under=80
git diff --check
```

Windows 下可能出现 `.pytest_cache` 权限警告；只要测试通过，该警告不影响结果。
