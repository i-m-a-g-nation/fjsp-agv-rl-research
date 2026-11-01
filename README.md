# fjsp-lab：调度研究实验平台

> A small, test-covered research platform for scheduling: static flexible job
> shop (FJSP), dynamic rescheduling, and identical parallel machines with
> mandatory maintenance windows (total tardiness). Every algorithm returns a
> plan only after an independent feasibility checker accepts it.

三条研究线共用一个 Python 包 `fjsp_lab`：

| 子包 | 内容 | 阶段 |
|---|---|---|
| `fjsp_lab.fjsp` | 静态 FJSP：不可变实例、FJSPLib 读取、统一调度结果、解码、**合法性检查器**、7 条派工规则、CP-SAT、甘特图 | Phase 1 |
| `fjsp_lab.dynamic` | 机器故障/维修、新工件到达、加工时间变化；冻结已开工工序；基线重调度；动态检查器 | Phase 2A |
| `fjsp_lab.maintenance` | 毕设模型：同质平行机 + 周期性必需维护（每台机器一个或多个时间窗，每窗内完整维护一次），最小化总延期；检查器、算例生成、CP-SAT/枚举、构造式 MDP、EDD/MDD/ATC、GA/SA/改进 GA、注意力 RL 策略（主方法）与 NumPy 打分策略（早期对照） | 毕设 |
| `fjsp_lab.logistics` | 大创 L1：柔性作业车间 + AGV 运输（显式空驶、L/U 站）+ 有限/无限输入缓冲 + 加工后阻塞；FJSPT 算例读取、协同检查器、事件仿真器、联合/解耦规则、小规模 CP-SAT | 大创 |

依赖方向单一：`fjsp ← dynamic`，`fjsp ← maintenance`，`fjsp ← logistics`（维护模型和物流模型的生产部分都直接用静态检查器校验）。

## 目录

```
src/fjsp_lab/        库代码（见上表）
tests/               pytest：fjsp/、maintenance/、logistics/、test_dynamic.py
experiments/         实验脚本（p1_*、p2_*、g*_*）、inputs/、results/（新结果）、archive/（旧结果）
instances/           FJSPLib 子集（30 个）与 BKS 表；external/（第三方无许可证数据，只在本地，git 忽略）
docs/                models/ 数学模型；protocols/ 实验协议；plans/ 路线与论文大纲；history/ 历史验收快照
notes/               文献笔记与毕设文献地图
scripts/             setup_env.ps1（建环境）、run_checks.ps1（测试 + Phase 1/2A 实验）
```

## 快速开始

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_env.ps1   # 建项目专用 Conda 环境 .conda-env
powershell -ExecutionPolicy Bypass -File .\scripts\run_checks.ps1  # pytest + Phase 1/2A 实验
```

不安装也能运行：测试通过 `pyproject.toml` 的 `pythonpath = ["src"]`，实验脚本由 `experiments/_common.py` 加入 `src/`。

```python
from fjsp_lab.fjsp import create_toy_instance, solve_rule, check_feasibility
result = solve_rule(create_toy_instance(), "EFT")
assert check_feasibility(result)[0]

from fjsp_lab.maintenance.generator import build_instance
from fjsp_lab.maintenance.metaheuristics import solve_metaheuristic
data = build_instance(24, 4, alpha=30, beta=75, tau=75, seed=101)
plan = solve_metaheuristic(data, mode="joint", algorithm="IGA", evaluations=10000).result
print(plan.total_tardiness)
```

## 正确性约定

- 输入数据不可变；所有时间和编号必须是 Python `int`（拒绝 `bool`、浮点）。
- 每个算法在返回前调用对应检查器，失败就抛异常，不返回非法调度。
- 静态检查器覆盖：每道工序恰好一次、工艺顺序、机器不重叠、可选机器、`end - start = processing_time`、加工时间与实例一致、makespan 一致。
- 维护检查器在此之上再查：每个维护窗口恰好一次维护、时长正确、整段落在窗口内、固定模式下起点等于给定值、与生产不重叠、总延期与独立重算一致。
- CP-SAT 只有 `OPTIMAL` 才称最优；`FEASIBLE` 是限时可行解。

## 当前进度

见 [START_HERE.md](START_HERE.md)；开发规则见 [AGENTS.md](AGENTS.md)；实验索引见 [experiments/README.md](experiments/README.md)。
