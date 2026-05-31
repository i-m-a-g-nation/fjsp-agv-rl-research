# 文献/数据源快速筛选结果

## 基本信息
- 编号：P002
- 名称：FJSPLib: The flexible jobshop scheduling problem benchmark library
- 年份：未知
- 类型：FJSP benchmark library / GitHub Pages
- 链接：https://scheduleopt.github.io/benchmarks/fjsplib
- 是否有代码：是
- 是否有数据：是

## 问题分类
- 类型：FJSP benchmark
- 是否考虑机器选择：是
- 是否考虑 AGV：否
- 是否考虑动态事件：否
- 是否 RL/GNN：否

## 对当前项目的价值
- 适合作为：Phase 1 基准实例来源 / best known solution 对照
- 值得精读程度：高
- 主要理由：页面说明该库整理了来自 1993-2012 文献的 FJSP 实例，并提供 upper bound / lower bound 与 best known solutions。

## 当前落地情况
- 已接入官方 ScheduleOpt 仓库中的旧格式文本文件。
- 已跟踪 `fattahi1`、Hurink edata `ft06` 和 Brandimarte `mk01`。
- 文件来源、许可证和 BKS 对照记录在 `instances/README.md`。
- `experiments/exp_005_benchmark_batch.py` 已对这些实例执行启发式和 CP-SAT 对比。

## 下一步建议
- 加入 `notes/paper_matrix.md`：是
- 是否需要精读：不需要按论文精读，但需要研究实例格式
- 是否需要找代码：已完成，loader 和批量实验已使用官方数据格式
- 是否需要复现：否
