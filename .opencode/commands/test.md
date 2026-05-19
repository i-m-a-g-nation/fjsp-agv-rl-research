---
description: Run Phase 1 checks in the dedicated Conda environment
---

请先阅读 AGENTS.md。

本轮只运行检查，除非用户明确要求，否则不要修改文件。

先运行：

python -c "import sys; print(sys.executable)"

输出路径必须是专用环境路径（项目内 `.conda-env` 或 `FJSP_CONDA_ENV` 指向的路径），不允许使用 base。

然后运行：

python experiments/exp_001_toy_instance.py
pytest

如果存在 CP-SAT 基线，也运行：

python experiments/exp_002_solver_check.py

输出：

- Python 路径
- 运行命令
- 通过/失败状态
- 失败摘要
- 不要隐藏错误
