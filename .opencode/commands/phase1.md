---
description: Continue Phase 1 static FJSP platform implementation
---

请先阅读 AGENTS.md。

当前只做 Phase 1：静态 FJSP 基础实验平台。

禁止实现：
- AGV
- 运输时间
- 强化学习
- DQN
- PPO
- GNN
- 动态事件
- 多目标优化

任务：

1. 创建或继续实现静态 FJSP 项目结构。
2. 实现 FJSPInstance。
3. 实现 ScheduleRecord / ScheduleResult。
4. 实现 makespan 与基础指标。
5. 实现 feasibility checker。
6. 实现 FIFO、SPT、Earliest Available Machine、Random baseline。
7. 实现甘特图输出。
8. 创建 experiments/exp_001_toy_instance.py。
9. 创建 tests/test_feasibility.py 和 tests/test_rules.py。

硬性要求：

- 必须使用专用 Conda 环境：
  项目内 `.conda-env`，或环境变量 `FJSP_CONDA_ENV` 指定的路径。

- 运行 Python 前必须执行：
  python -c "import sys; print(sys.executable)"

- 输出路径必须是专用环境路径，不允许使用 base。

完成后运行：

python experiments/exp_001_toy_instance.py
pytest

最后报告：

- 修改文件列表
- 运行命令
- 测试结果
- 是否存在失败
- 是否可以进入 CP-SAT 求解器阶段
