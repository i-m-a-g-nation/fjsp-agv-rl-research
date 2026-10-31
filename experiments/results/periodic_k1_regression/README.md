# 多窗口扩展后的单窗口回归（2026-10-31）

加入周期性预防维护（每台机器 K_i 个窗口）后，用与 `experiments/archive/restructure_equivalence/` 相同的方法，
把新代码与重构前的原始代码（分支 `archive/pre-restructure-2026-10-31`）在单窗口实例上逐项比较。
唯一的区别：构造环境的动作编号从固定布局（job×4+machine，96+machine）改为随规模变化的布局（job×m+machine，n×m+machine），
脚本先把旧编号换算成新编号再比较。

结果见 [output.txt](output.txt)：16 项全部一致，所以 `experiments/archive/` 中 exp_035–041 的结论对扩展后的代码仍然成立。
运行时的源码与提交"feat(maintenance): periodic preventive maintenance windows"中的 `src/` 相同。
