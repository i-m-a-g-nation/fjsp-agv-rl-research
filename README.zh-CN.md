# FJSP-AGV-RL Research

English version: [README.md](README.md)

本项目当前处于 **Phase 1：静态柔性作业车间调度（FJSP）基础实验底座**。

当前目标不是直接做 AGV、强化学习或图神经网络，而是先把静态 FJSP 的数据结构、调度解码、合法性校验、基准算法、CP-SAT 求解器和实验记录做稳。后续 AGV 协同调度和强化学习应该建立在这个稳定底座上。

## 当前范围

Phase 1 已覆盖：

- FJSP 实例结构：`FJSPInstance`、Job、Operation、MachineOption
- 调度结果结构：`ScheduleRecord`、`ScheduleResult`
- 半主动解码：从 `(job_id, op_id, machine_id)` 编码生成带时间的调度表
- Feasibility Checker：检查工序覆盖、工序顺序、机器容量、机器可行性、加工时间和 makespan 一致性
- 简单启发式 baseline：FIFO、SPT、Earliest Finish Time、Random
- 严格 dispatching rule：DispatchFIFO、DispatchSPT、DispatchEFT、DispatchMWKR、DispatchMOPNR、DispatchRandom
- OR-Tools CP-SAT baseline：可选区间变量、ExactlyOne、Precedence、NoOverlap、最小化 makespan
- CP-SAT 求解诊断：solver status、objective bound、relative gap、solver wall time
- CP-SAT 时限 sweep：对 tracked `mk03` 使用固定单 worker 进行对比
- CP-SAT worker 数量 sweep：对 tracked `mk03` 使用固定 10 秒时限进行对比
- CP-SAT worker 重复实验聚合：同时保留逐次记录和汇总 CSV
- tracked 静态 FJSPLib 子集上的受控 CP-SAT 重复实验矩阵
- 包含确定性规则和可复现随机 seed 的启发式 benchmark 矩阵
- 基于结构化上游参考值的启发式 BKS 相对质量指标
- 将 tracked FJSPLib 文件、BKS 记录和 loader 校验关联起来的元数据审计
- Benchmark smoke loader：支持小型 0-based / 1-based FJSP 格式文件
- 有来源说明的 FJSPLib 子集：覆盖六个上游来源系列
- Matplotlib Gantt 图输出
- 统一实验 CSV 记录
- 统一实验 runner：负责计时、feasibility 校验、失败记录和 solver metadata 提取
- 递归 benchmark 批量实验入口：稳定排序，并记录可审计的 loader 失败信息
- Phase 1 数学建模 LaTeX 文档

Phase 1 明确不做：

- AGV 运输、路径规划、避碰
- 动态事件、实时重调度
- 强化学习、PPO、DQN、多智能体
- 图神经网络
- 复杂论文算法完整复现

## 目录结构

```text
src/
  data/          FJSP 实例结构和 benchmark loader
  scheduling/    编码、解码、合法性检查
  solvers/       baseline、dispatching rule、兼容门面和 OR-Tools CP-SAT
  vis/           Gantt 图绘制
tests/           pytest 测试
experiments/     实验脚本、CSV 结果和图像产物
instances/       本地 smoke 文件和真实 FJSPLib 子集
docs/            代码说明、审查状态、数学模型
notes/           开发笔记和方案讨论
papers/          文献索引
```

## 快速运行

推荐使用项目专用 Conda 环境，不要用 `base` 环境：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_env.ps1
```

常用检查：

```powershell
.\.conda-env\python.exe experiments\exp_001_toy_instance.py
.\.conda-env\python.exe experiments\exp_002_solver_check.py
.\.conda-env\python.exe experiments\exp_003_dispatching_rules.py
.\.conda-env\python.exe experiments\exp_004_benchmark_smoke.py
.\.conda-env\python.exe experiments\exp_005_benchmark_batch.py
.\.conda-env\python.exe experiments\exp_006_cpsat_time_limit_sweep.py
.\.conda-env\python.exe experiments\exp_007_cpsat_worker_sweep.py
.\.conda-env\python.exe experiments\exp_008_cpsat_worker_repeats.py
.\.conda-env\python.exe experiments\exp_009_cpsat_benchmark_matrix.py
.\.conda-env\python.exe experiments\exp_010_heuristic_benchmark_matrix.py
.\.conda-env\python.exe experiments\exp_011_heuristic_quality_report.py
.\.conda-env\python.exe experiments\exp_012_benchmark_metadata_audit.py
.\.conda-env\python.exe -m pytest
```

如果使用自定义 `FJSP_CONDA_ENV`，把上面的 `.\.conda-env\python.exe` 换成对应环境里的 Python。

## 当前实验结果

Toy 3x3 实例上的主要结果：

| 算法 | Makespan | Feasible |
|---|---:|---|
| FIFO | 14 | PASS |
| SPT | 13 | PASS |
| EarliestFinishTime | 13 | PASS |
| DispatchFIFO | 11 | PASS |
| DispatchSPT | 13 | PASS |
| DispatchEFT | 13 | PASS |
| DispatchMWKR | 12 | PASS |
| DispatchMOPNR | 12 | PASS |
| DispatchRandom(42) | 14 | PASS |
| CP-SAT | 11 | PASS / OPTIMAL |

实验 CSV 结果位于：

- `experiments/results/exp_001_toy_instance.csv`
- `experiments/results/exp_002_solver_check.csv`
- `experiments/results/exp_003_dispatching_rules.csv`
- `experiments/results/exp_004_benchmark_smoke.csv`
- `experiments/results/exp_005_benchmark_batch.csv`
- `experiments/results/exp_006_cpsat_time_limit_sweep.csv`
- `experiments/results/exp_007_cpsat_worker_sweep.csv`
- `experiments/results/exp_008_cpsat_worker_repeats_runs.csv`
- `experiments/results/exp_008_cpsat_worker_repeats_summary.csv`
- `experiments/results/exp_009_cpsat_benchmark_matrix_runs.csv`
- `experiments/results/exp_009_cpsat_benchmark_matrix_summary.csv`
- `experiments/results/exp_010_heuristic_benchmark_matrix_runs.csv`
- `experiments/results/exp_010_heuristic_benchmark_matrix_summary.csv`
- `experiments/results/exp_011_heuristic_quality_rows.csv`
- `experiments/results/exp_011_heuristic_quality_families.csv`
- `experiments/results/exp_012_benchmark_metadata_audit.csv`

CSV 中会记录算法、实例、makespan、feasibility 状态、运行时间和说明。对 CP-SAT 结果，还会额外记录 objective bound、relative gap 和 solver wall time。

`experiments/exp_005_benchmark_batch.py` 是可扩展的批量入口。它会递归扫描
`instances/` 下的 `*.fjs` 文件，稳定排序并记录 loader 失败。对更大的静态
benchmark 集合，可使用 `--max-files`、`--skip-cp-sat` 和
`--cp-sat-time-limit` 控制实验规模。

真实子集的来源说明位于 [instances/README.md](instances/README.md)。十三份上游
文件来自 ScheduleOpt 官方 FJSPLib 仓库，并保留 CC-BY-SA-4.0 归属说明。

| FJSPLib 实例 | 规模 | 当前启发式最佳值 | CP-SAT | FJSPLib BKS |
|---|---:|---:|---:|---:|
| `fattahi1` | 2 x 2 | 66 | 66 `OPTIMAL` | 66 |
| `fattahi2` | 2 x 2 | 107 | 107 `OPTIMAL` | 107 |
| `fattahi3` | 3 x 2 | 221 | 221 `OPTIMAL` | 221 |
| Chambers-Barnes `mt10c1` | 10 x 11 | 1225 | 927 `FEASIBLE` | 927 |
| Dauzere-Peres `01a` | 10 x 5 | 3056 | 2565 `FEASIBLE` | 2505 |
| `kacem1` | 4 x 5 | 11 | 11 `OPTIMAL` | 11 |
| `kacem2` | 10 x 7 | 12 | 11 `OPTIMAL` | 11 |
| `kacem3` | 10 x 10 | 8 | 7 `OPTIMAL` | 7 |
| Hurink edata `ft06` | 6 x 6 | 55 | 55 `OPTIMAL` | 55 |
| Brandimarte `mk01` | 10 x 6 | 44 | 40 `OPTIMAL` | 40 |
| Brandimarte `mk02` | 10 x 6 | 30 | 28 `FEASIBLE` | 26 |
| Brandimarte `mk03` | 15 x 8 | 204 | 204 `FEASIBLE` | 204 |
| Brandimarte `mk04` | 15 x 8 | 77 | 60 `FEASIBLE` | 60 |

对于 `mk02`、`mk03`、`mk04`、`mt10c1` 和 `01a`，本地 CP-SAT 结果是 10 秒时限内得到的可行调度，
求解器没有证明最优性。因此这里只将其报告为限时可行参考调度。

### 实验 006：CP-SAT 时限 sweep

对 tracked Brandimarte `mk03` 使用固定单 worker，减少并行搜索噪声：

| 时限 | Makespan | 状态 | Bound | 相对 gap |
|---:|---:|---|---:|---:|
| 1s | 417 | `FEASIBLE` | 20 | 0.952038 |
| 3s | 285 | `FEASIBLE` | 20 | 0.929825 |
| 10s | 220 | `FEASIBLE` | 20 | 0.909091 |

固定 worker 的 sweep 与默认批量实验分开记录。默认批量实验允许 CP-SAT 使用
默认 worker 配置。求解器配置属于实验结果的一部分，比较时必须明确区分。

### 实验 007：CP-SAT worker 数量 sweep

对 tracked Brandimarte `mk03` 使用固定 10 秒时限，只改变 CP-SAT worker 配置：

| Workers | Makespan | 状态 | Bound | 相对 gap |
|---:|---:|---|---:|---:|
| 1 | 220 | `FEASIBLE` | 20 | 0.909091 |
| 2 | 207 | `FEASIBLE` | 20 | 0.903382 |
| 4 | 207 | `FEASIBLE` | 20 | 0.903382 |
| auto | 209 | `FEASIBLE` | 75 | 0.641148 |

每一行均通过独立 feasibility checker。这只是一次限时运行的观测结果，不是
稳定的 worker 性能排名：并行 CP-SAT 搜索可能在不同运行之间产生变化。本次
观测中，auto 配置给出了更强的 bound，而 2 和 4 workers 给出了略好的
incumbent。

### 实验 008：CP-SAT worker 重复观测

对 tracked Brandimarte `mk03` 保持相同的 10 秒时限，每种 worker 配置重复运行
3 次。逐次结果和聚合统计分别记录。

| Workers | 可行运行数 | 最佳 makespan | 平均 makespan | 标准差 | 最佳 bound | 最佳 gap |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3 / 3 | 220 | 220.000000 | 0.000000 | 20 | 0.909091 |
| 2 | 3 / 3 | 204 | 204.000000 | 0.000000 | 20 | 0.901961 |
| 4 | 3 / 3 | 204 | 204.000000 | 0.000000 | 21 | 0.897059 |
| auto | 3 / 3 | 204 | 204.000000 | 0.000000 | 88 | 0.568627 |

全部 12 个调度均通过独立 feasibility checker。在本次三次重复观测中，
2、4 和 auto workers 都稳定达到上游 BKS `204`。但是 CP-SAT 状态仍然是
`FEASIBLE`，所以这些结果仍然只是限时可行参考解，不是本地已证明最优解。

### 实验 009：CP-SAT benchmark 重复矩阵

递归扫描 tracked 静态 FJSPLib 子集。每个实例在相同的 3 秒时限下，使用单
worker 重复 2 次，再使用 auto worker 配置重复 2 次。

| 实例 | Workers | 可行运行数 | 最佳 makespan | 平均 makespan | 状态 | 最佳 bound |
|---|---:|---:|---:|---:|---|---:|
| `mk01` | 1 | 2 / 2 | 40 | 40.000000 | `OPTIMAL` | 40 |
| `mk01` | auto | 2 / 2 | 40 | 40.000000 | `OPTIMAL` | 40 |
| `mk02` | 1 | 2 / 2 | 30 | 30.000000 | `FEASIBLE` | 3 |
| `mk02` | auto | 2 / 2 | 28 | 28.000000 | `FEASIBLE` | 22 |
| `mk03` | 1 | 2 / 2 | 272 | 274.000000 | `FEASIBLE` | 20 |
| `mk03` | auto | 2 / 2 | 215 | 218.000000 | `FEASIBLE` | 84 |
| `mk04` | 1 | 2 / 2 | 68 | 68.000000 | `FEASIBLE` | 14 |
| `mk04` | auto | 2 / 2 | 61 | 62.000000 | `FEASIBLE` | 43 |
| `mt10c1` | 1 | 2 / 2 | 933 | 940.500000 | `FEASIBLE` | 759 |
| `mt10c1` | auto | 2 / 2 | 927 | 927.000000 | `FEASIBLE` | 876 |
| `01a` | 1 | 2 / 2 | 2697 | 2697.000000 | `FEASIBLE` | 1395 |
| `01a` | auto | 2 / 2 | 2621 | 2625.500000 | `FEASIBLE` | 2505 |
| `fattahi1` | 1 / auto | 4 / 4 | 66 | 66.000000 | `OPTIMAL` | 66 |
| `fattahi2` | 1 / auto | 4 / 4 | 107 | 107.000000 | `OPTIMAL` | 107 |
| `fattahi3` | 1 / auto | 4 / 4 | 221 | 221.000000 | `OPTIMAL` | 221 |
| edata `ft06` | 1 / auto | 4 / 4 | 55 | 55.000000 | `OPTIMAL` | 55 |
| `kacem1` | 1 / auto | 4 / 4 | 11 | 11.000000 | `OPTIMAL` | 11 |
| `kacem2` | 1 / auto | 4 / 4 | 11 | 11.000000 | `OPTIMAL` | 11 |
| `kacem3` | 1 / auto | 4 / 4 | 7 | 7.000000 | `OPTIMAL` | 7 |

全部 52 个调度均通过独立 feasibility checker。除 `mk02` 外，较小的 tracked
实例在时限内证明了最优性。对于 `mk02`、`mk03`、`mk04`、`mt10c1` 和 `01a`，auto workers 改善了本次
观测中的 incumbent 和 bound，但两种配置都没有在 3 秒内证明最优性。

### 实验 010：启发式 benchmark 矩阵

在每个 tracked FJSPLib 实例上运行一次确定性 baseline 和严格 dispatching
rule。`Random` 与 `DispatchRandom` 使用固定 seed `42`、`123` 和 `999`
进行聚合。

| 实例 | 最佳确定性规则 | Makespan | Random 范围 | DispatchRandom 范围 |
|---|---|---:|---:|---:|
| `mk01` | DispatchMWKR | 44 | 148-165 | 92-125 |
| `mk02` | DispatchMWKR | 30 | 134-169 | 86-113 |
| `mk03` | DispatchFIFO / DispatchMWKR | 204 | 1086-1206 | 488-563 |
| `mk04` | DispatchFIFO | 77 | 279-292 | 143-177 |
| `mt10c1` | DispatchMOPNR | 1225 | 3348-3394 | 1446-1728 |
| `01a` | DispatchFIFO | 3056 | 10212-10398 | 4132-4525 |
| `fattahi1` | DispatchMWKR | 66 | 86-135 | 86-135 |
| `fattahi2` | DispatchFIFO / DispatchMWKR | 107 | 107-192 | 107-149 |
| `fattahi3` | DispatchFIFO / DispatchMOPNR | 221 | 298-442 | 221-361 |
| edata `ft06` | DispatchFIFO | 55 | 146-152 | 71-112 |
| `kacem1` | DispatchFIFO | 11 | 27-82 | 26-44 |
| `kacem2` | DispatchMWKR | 12 | 62-102 | 50-88 |
| `kacem3` | DispatchFIFO / DispatchMWKR / DispatchMOPNR | 8 | 42-77 | 50-72 |

全部 182 个调度均通过独立 feasibility checker。没有一个 dispatching rule
在所有实例上占优：MWKR 在 `mk01`、`mk02`、`fattahi1` 和 `kacem2` 上最好，
FIFO 在 `mk04`、`ft06` 和 `kacem1` 上最好，在 `mk03` 和 `fattahi2` 上与
MWKR 并列，并在 `fattahi3` 上与 MOPNR 并列。MOPNR 在 `mt10c1` 上最好；
FIFO 在 `01a` 上最好；FIFO、MWKR 和 MOPNR 在 `kacem3` 上并列。
ready-operation 随机 dispatching 在当前 tracked 子集上持续优于简单
job-order 随机 baseline，但仍然受 seed 影响。

### 实验 011：基于 BKS 的启发式质量报告

读取 `instances/fjsplib_bks.csv` 中的结构化上游参考值，并为实验 010 中每个
算法族和实例计算：

```text
gap_BKS = (makespan - BKS) / BKS
```

上游 BKS 用于比较，不等于本地求解器已经证明最优性。

| 算法族 | 平均最佳 gap | 最大最佳 gap |
|---|---:|---:|
| FIFO | 5.046584 | 21.285714 |
| SPT | 1.870830 | 3.366667 |
| EarliestFinishTime | 0.459417 | 1.384615 |
| DispatchFIFO | 0.145799 | 0.331176 |
| DispatchSPT | 1.109732 | 2.259082 |
| DispatchEFT | 0.461686 | 1.384615 |
| DispatchMWKR | 0.140666 | 0.350593 |
| DispatchMOPNR | 0.202347 | 0.466667 |
| Random | 2.608660 | 5.000000 |
| DispatchRandom | 1.479880 | 6.142857 |

在当前十三实例子集上，DispatchMWKR 的跨实例平均最佳 gap 最小。当前样本仍然
较小，下一步应优先扩展 benchmark 覆盖，再决定是否增加新规则。

### 实验 012：Benchmark 元数据审计

递归发现 tracked FJSPLib 文件，将文件与 `instances/fjsplib_bks.csv` 逐项匹配，
并验证每个 tracked 文件仍可被 loader 加载。当前十三行全部通过文件、BKS 和
loader 检查。若缺少文件、元数据记录或可加载实例，脚本会返回失败退出码。

## 数学建模文档

英文版：

- [docs/math_model_phase1.tex](docs/math_model_phase1.tex)
- [docs/math_model_phase1_en.pdf](docs/math_model_phase1_en.pdf)

中文版：

- [docs/math_model_phase1_zh.tex](docs/math_model_phase1_zh.tex)
- [docs/math_model_phase1_zh.pdf](docs/math_model_phase1_zh.pdf)

数学模型包含集合、参数、决策变量、机器选择约束、工序顺序约束、机器容量约束、makespan 定义，以及 feasibility checker 与数学约束之间的对应关系。

## 维护建议

当前代码还不需要推倒重构。后续应继续小步开发：

- 分批扩展 FJSPLib 子集，并比较更大静态实例上的求解行为
- 再测试更大静态 FJSP 实例上的 OR-Tools 行为
- 再加入少量 Phase 1 范围内的启发式算法
- 暂时不要引入 AGV/RL/GNN，避免复杂度过早失控

项目优先级保持：

```text
正确性 > 可维护性 > 性能
```
