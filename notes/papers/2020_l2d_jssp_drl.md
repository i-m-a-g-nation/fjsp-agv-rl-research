# 论文快速筛选结果

## 基本信息
- 编号：P006
- 题目：Learning to Dispatch for Job Shop Scheduling via Deep Reinforcement Learning
- 年份：2020
- 期刊/会议：NeurIPS 2020
- 作者：Cong Zhang, Wen Song, Zhiguang Cao, Jie Zhang, Puay Siew Tan, Xu Chi
- 官方页面：https://proceedings.neurips.cc/paper/2020/hash/11958dfee29b6709f48a9ba0387a2431-Abstract.html
- arXiv：https://arxiv.org/abs/2010.12367
- 是否有代码：是
- 是否有数据：是，JSSP benchmark

## 问题分类
- 类型：JSP，不是 FJSP
- 是否考虑机器选择：否
- 是否考虑 AGV：否
- 是否考虑动态事件：否
- 是否 RL/GNN：是，GNN + DRL 学习 dispatching rule

## 对当前项目的价值
- 适合作为：DRL/GNN 调度入门参照 / 后续方法背景
- 值得精读程度：中-高
- 主要理由：经典 NeurIPS 工作，但对象是 JSP，不应直接混入 Phase 1 FJSP 代码。

## 下一步建议
- 加入 `notes/paper_matrix.md`：是
- 是否需要精读：后续 RL 阶段再精读
- 是否需要找代码：是，先只记录不运行
- 是否需要复现：Phase 1 不复现
