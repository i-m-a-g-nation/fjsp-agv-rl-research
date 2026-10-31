# 归档结果（重构前）

这里是 2026-10-31 重构之前由旧代码（`src/graduation/`、`src/solvers/` 等）产生的、论文和阶段验收会用到的结果。
文件**逐字节保持原样**（`.gitattributes` 禁止换行转换），只是从 `experiments/results/` 移到了这里。

- 各结果的 `manifest.json` 记录的源码路径和 SHA-256 指向旧代码；文中链接也仍是旧路径（`experiments/results/...`
  即本目录）。按哈希核验请检出分支 `archive/pre-restructure-2026-10-31`。
- 重构后的 `fjsp_lab` 在相同输入上与旧代码结果完全相同（实例、规则、环境与特征、打分策略推理和训练、GA/SA/IGA、
  教师轨迹、CP-SAT、枚举、静态 FJSP 规则、Phase 2A 协议），见 [restructure_equivalence/](restructure_equivalence/)。
  因此这些数字可以与新脚本的结果直接比较。
- 新结果写入 `experiments/results/`，旧编号与新脚本的对应见 [../README.md](../README.md)。

| 结果 | 内容 |
|---|---|
| `exp_001`–`exp_013`（CSV/MD） | Phase 1：玩具实例、规则、CP-SAT、时间/线程扫描、基准矩阵、元数据审计 |
| `exp_001_gantt/` | Phase 1 玩具实例甘特图 |
| `phase1_hardening_v1/`、`phase1_closeout_v1/`、`phase1_delivery_followup_v1/`、`phase1_ci_3bb926d_v1/` | Phase 1 加固与验收记录 |
| `exp_014`–`exp_017`、`exp_019_phase2a_protocol_v1/`、`exp_020_sequential_reschedule_v1/` | Phase 2A：事件文件、243 次协议运行、顺序回放 |
| `exp_021_graduation_g2_v1/` | 维护模型 G2：小规模 CP-SAT 与独立枚举核对 |
| `exp_034_graduation_solver_v2_v1/` | solver_v2 目标上界验收规则核对 |
| `exp_035_graduation_main_v2_v1/` | G3A 固定 vs 联合维护，480 次 CP-SAT 1 s 全部接受 |
| `exp_036_scoring_policy_v1/` | NumPy 打分策略训练（3 种子）与测试 |
| `exp_037_sampling_decoding_v1/` | 采样解码，按相同回放次数对比规则 |
| `exp_038_g3b_comparison_v1/` | 策略 vs 规则 vs CP-SAT 1 s/60 s |
| `exp_039_atc_k2_baseline_v1/` | ATC k=2 复核 |
| `exp_040_metaheuristics_v1/` | GA/SA/改进 GA |
| `exp_041_seeded_iga_v1/` | 以 RL 解为初始种群的 IGA |
| `restructure_equivalence/` | 重构等价性核对脚本与输出 |
