# 从这里开始

当前进度与下一步只在本页维护。代码结构见 [README](README.md)，开发规则见 [AGENTS.md](AGENTS.md)，实验索引见 [experiments/README.md](experiments/README.md)。

## 2026-10-31 工程重构

- 重构前的完整状态保存在分支 `archive/pre-restructure-2026-10-31`（提交 `9e8fc13`）。
- 删除了与研究无关的 AI 科研工作流（`src/ai_workflow/`、LangGraph/RAG、论文抽取、会话/沙箱/预算控制）、opencode 配置、
  过程计划文档（`docs/superpowers/`）、已被替代的毕设探索代码（旧 NumPy RL、状态编码、候选/诊断/补救、solver v1、
  参考试跑）以及对应测试和结果。
- 库代码合并为一个包 `src/fjsp_lab/`（`fjsp` / `dynamic` / `maintenance`），测试从约 120 个文件精简为 7 个文件、123 个用例
  （覆盖率 87%），实验脚本从 43 个精简为 8 个。
- 新代码在相同输入上与旧代码结果**完全一致**，见 [等价性核对](experiments/archive/restructure_equivalence)；
  旧结果原样保存在 `experiments/archive/`。

## 环境

| 用途 | 环境 |
|---|---|
| 除注意力策略外的全部代码与测试 | 项目专用 Conda 环境（`.conda-env` 或 `FJSP_CONDA_ENV`） |
| `experiments/g6_attention_policy.py`（PyTorch，GPU） | 本机已有的 PyTorch 环境；不重复安装 PyTorch |

## 各路线状态

| 路线 | 已有 | 未完成 |
|---|---|---|
| Phase 1 静态 FJSP | 实例/读取、7 条规则、CP-SAT、检查器、甘特图；30 个 FJSPLib 实例 | — （维护中） |
| Phase 2A 动态 | 三类事件、冻结、基线重调度、动态检查器；243 次协议运行全部通过 | 物流/AGV 等扩展 |
| 毕设（平行机 + 维护） | 模型与检查器（含周期性多窗口维护）；CP-SAT 与枚举核对；G3A 固定 vs 联合（n=8 证得最优，联合平均降低最优总延期约 30%–56%）；EDD/MDD/ATC；GA/SA/IGA；NumPy 打分策略；注意力策略试跑 | 论文主线确认、更大规模算例、甘特图示例、论文正文 |
| 大创（生产—物流协同） | 共用底座 | 运输、AGV、缓冲区均未实现；[最小范围草案](docs/plans/innovation_scope_draft.md)未获批 |

## 毕设关键结果（归档于 experiments/archive/）

- **固定 vs 联合维护**（exp_035）：480 次 CP-SAT 求解全部接受；n=8 全部证得最优，固定延期大于 0 时联合维护严格更好；n=24 只有 1 秒限时观察。
- **规则与打分策略**（exp_036–038）：打分策略 1 次回放比 MDD 低约 8%，9 次回放比 9 规则组合低约 1%；n=24 比 1 秒 CP-SAT 好，但比 60 秒 CP-SAT 差 6%–11%。
- **智能优化算法**（exp_040）：SA/IGA 约 0.5 秒达到 n=24 上 CP-SAT 60 秒的水平；IGA 约 11 毫秒就比打分策略 9 次回放（约 82 毫秒）好 2.7%。联合维护在 n=8 上降低 54%（证得最优），n=24 上 35.5%，窗口越宽收益越大。
- **RL 初始种群的 IGA**（exp_041）：与规则初始种群差异不显著（负结果）。
- **注意力策略试跑**（2026-10-31，未归档，仅训练/验证集）：模仿 IGA 教师 8 轮 + REINFORCE 约 300 步，验证集单次贪心 25.38，
  比旧打分策略（约 27.26）低 6.9%、比 MDD（29.13）低 12.9%；但相同时间下仍不如 IGA（IGA 1000 次解码约 14 ms 得 24.36；
  策略 16 次采样约 90 ms 得 24.04），预先登记的成功标准（同等时间显著优于 IGA）**未达到**。RL 训练瓶颈是环境步进（约 18 s/步）。

## 下一步

1. **G4（周期性预防维护 + 质量—时间曲线）已完成**，结论见 [G4 findings](experiments/results/g4_summary/findings.md)：
   - RL 的优势出现在 **n = 100、0.2–2 s** 内：显著优于 IGA 和 SA，平均 gap 约为 IGA 的 1/3。
     n = 50 时与 IGA 持平；n = 20 和长时间预算时 IGA/SA 更好。
   - 预先登记的 H1（≤ 0.2 s 内优于搜索算法）不成立：单次 GPU 推理就需要 0.15–0.3 s。
   - 协同维护：n = 20 时平均降低总延期 49%，n = 100 时 7%；窗口越宽收益越大。
2. **论文主线**：按 G4 结果，RL 的定位可以写成"大规模实例上的快速高质量调度"；[论文大纲](docs/plans/thesis_outline.md)待按此修订，并请导师确认。
3. 可选的后续工作：
   - 加快单实例推理（CPU 推理或编译模型），把 RL 曲线左移；
   - 多个训练种子；
   - 更大规模（n = 200）的泛化。
   这些都需要单独批准。
4. 重构后尚未重跑：`g1 --long`、g2–g4（单窗口 G3A 网格）。

## 文档

- 模型：[毕设模型](docs/models/graduation_model.md)、Phase 1/2A 数学模型（`docs/models/`）
- 协议：[G3A 协议](docs/protocols/g3a_protocol.md)、[Phase 2A 协议](docs/protocols/phase2a_experiment_protocol.md)
- 计划：[路线图](docs/plans/ROADMAP.md)、[论文大纲](docs/plans/thesis_outline.md)、[大创草案](docs/plans/innovation_scope_draft.md)
- 文献：[毕设文献地图](notes/literature_map_graduation.md)
- 历史验收快照（引用旧路径）：`docs/history/`
