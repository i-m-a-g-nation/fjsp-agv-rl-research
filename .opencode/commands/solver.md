---
description: Add or fix OR-Tools CP-SAT baseline for static FJSP
---

请先阅读 AGENTS.md。

当前任务：添加或修复 OR-Tools CP-SAT 静态 FJSP 求解器基线。

禁止实现：
- AGV
- 强化学习
- GNN
- 动态事件
- 多目标优化

要求：

1. 使用 OR-Tools CP-SAT。
2. operation-machine 组合使用 optional interval。
3. 每道工序 exactly one machine。
4. 同一工件相邻工序满足 precedence。
5. 同一机器上任务满足 NoOverlap。
6. 目标 minimize makespan。
7. 支持 time limit。
8. 输出转换为已有 ScheduleResult / ScheduleRecord。
9. 求解器输出必须经过 feasibility checker。
10. 只有 status 为 OPTIMAL 时才能说最优。
11. 如果 status 为 FEASIBLE，只能说限时可行参考解。

需要文件：

- src/solver/ortools_fjsp.py
- experiments/exp_002_solver_check.py
- tests/test_ortools_solver.py
- requirements.txt
- README.md

运行前检查：

python -c "import sys; print(sys.executable)"

输出路径必须是专用环境路径（项目内 `.conda-env` 或 `FJSP_CONDA_ENV` 指向的路径），不允许使用 base。

完成后运行：

python experiments/exp_002_solver_check.py
pytest

最后报告：

- 修改文件列表
- CP-SAT 模型说明
- solver status 处理方式
- 实验表格
- 测试结果
- 剩余限制
