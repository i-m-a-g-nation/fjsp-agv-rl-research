# 第一批核心文献种子清单

更新时间：2026-05-18

## 1. Phase 1 直接相关

- P001：The flexible job shop scheduling problem: A review
- P002：FJSPLib benchmark library
- P003：Brandimarte 1993 tabu search
- P004：Fattahi et al. 2007 modeling and heuristics

用途：确定静态 FJSP 定义、实例格式、benchmark 来源、makespan 对照和基础建模方式。

## 2. 后续运输/AGV 方向

- P005：Flexible job-shop scheduling with transportation resources
- P008：Dynamic scheduling for flexible job shop with insufficient transportation resources via GNN and DRL

用途：作为 Phase 2 及以后生产-物流协同调度背景。当前 Phase 1 不实现这些内容。

## 3. 后续 DRL/GNN 方向

- P006：Learning to Dispatch for JSSP via DRL
- P007：FJSP via Dual Attention Network Based RL
- P009：FJSP via MHGNN + DRL

用途：作为后续强化学习和图神经网络路线背景。当前 Phase 1 不引入 RL/GNN 代码或依赖。

## 下一步阅读顺序

1. 精读 P001，提取 FJSP 问题分类、约束、目标、求解方法 taxonomy。
2. 阅读 P002，确认 FJSPLib 数据格式和 BKS 记录方式。
3. 只读 P003/P004 的问题定义和实例来源。
4. Phase 1 通过测试后，再筛 P005/P006/P007/P008/P009。
