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

## 下一步建议
- 加入 `notes/paper_matrix.md`：是
- 是否需要精读：不需要按论文精读，但需要研究实例格式
- 是否需要找代码：是，后续实现 loader 时使用
- 是否需要复现：否
