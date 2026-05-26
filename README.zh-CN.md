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
- 严格 dispatching rule：DispatchFIFO、DispatchSPT、DispatchEFT、DispatchMWKR、DispatchRandom
- OR-Tools CP-SAT baseline：可选区间变量、ExactlyOne、Precedence、NoOverlap、最小化 makespan
- Benchmark smoke loader：支持小型 0-based / 1-based FJSP 格式文件
- Matplotlib Gantt 图输出
- 统一实验 CSV 记录
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
  solvers/       启发式算法和 OR-Tools CP-SAT
  vis/           Gantt 图绘制
tests/           pytest 测试
experiments/     实验脚本、CSV 结果和图像产物
instances/       小型 benchmark/smoke 实例
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
| DispatchRandom(42) | 14 | PASS |
| CP-SAT | 11 | PASS / OPTIMAL |

实验 CSV 结果位于：

- `experiments/results/exp_001_toy_instance.csv`
- `experiments/results/exp_002_solver_check.csv`
- `experiments/results/exp_003_dispatching_rules.csv`
- `experiments/results/exp_004_benchmark_smoke.csv`

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

- 先完善真实 benchmark 批量加载
- 再补 CP-SAT gap / bound / wall time 记录
- 再加入少量 Phase 1 范围内的启发式算法
- 暂时不要引入 AGV/RL/GNN，避免复杂度过早失控

项目优先级保持：

```text
正确性 > 可维护性 > 性能
```
