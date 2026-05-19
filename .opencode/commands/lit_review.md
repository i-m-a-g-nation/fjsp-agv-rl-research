---
description: 根据已有论文笔记生成文献综述草稿
agent: plan
---

请根据 notes/papers/ 和 notes/paper_matrix.md 生成或更新 notes/literature_review/outline.md。

要求：
1. 不要写成论文最终稿。
2. 先生成结构化综述草稿。
3. 每个方向都要写：
   - 研究对象
   - 代表方法
   - 代表论文
   - 已解决问题
   - 未解决问题
   - 与本课题关系
4. 不要编造引用。
5. 如果缺少某一方向的论文，明确提示“文献不足，需要补充”。

综述结构：

# 文献综述草稿

## 1. FJSP 基础研究
## 2. Integrated FJSP 研究
## 3. FJSP with transportation / AGV
## 4. Dynamic FJSP
## 5. DRL for scheduling
## 6. GNN for scheduling
## 7. 现有研究不足
## 8. 本课题切入点
## 9. 后续需要补充的论文清单

输出：
- 更新后的综述路径
- 当前文献覆盖是否足够
- 下一批建议阅读论文方向
