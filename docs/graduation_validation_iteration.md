# 验证轨迹诊断与单候选对照

**一次命令已能完成：核验旧证据→诊断验证轨迹→训练一名候选及原方法→合法性检查→按验证表现保留或拒绝。** 本轮历史均值候选未改善两个模式的总体结果，程序自动保留原方法。此流程面向预先声明的候选，论文发现、自动改码和跨设计研究搜索尚未接通。

## 先发现了什么

只分析上一轮的训练日志和验证数据，没有评估探测集或最终测试集。16份策略计划及112次“先按策略走若干步、再切到EDD”的完整计划均过原G1检查和独立延期重算。

- 与EDD一致的动作29/96；差异涉及26次任务顺序、16次机器分配、24次生产/维护选择及1次维护机器选择。
- 80个非空、非终止前缀切换EDD后，31个更好、47个相同、2个更差。不能据此把EDD当成所有状态下都最优的教师。
- 256次更新只裁剪了4次，暂不支持把裁剪视为主要瓶颈。原始回报权重1251个负值、285个零值，没有正值；算法方向并非因此错误，但可以检验相对历史水平的学习信号。

诊断提出的是可检验假设，不是已经证明的因果解释。平均回报baseline也不保证最优或改善，相关方法依据见[Greensmith等，JMLR2004](https://www.jmlr.org/papers/v5/greensmith04a.html)。

## 只改了一个地方

增加`train_policy(..., return_baseline='running_mean')`：为每个训练实例槽及构造步保存**过去完整回合**的回报均值。当前梯度权重用`原reward-to-go − 过去均值`；先完成合法回合及更新，再记录当前原始回报。第一遍访问均值为0，不使用当前回合自我中心化。

环境奖励仍是`-总延期/100`，gamma=1，原始samples不改；网络、学习率、梯度范数上限、数据、种子、训练顺序和64回合预算相同。`none`默认路径的日志和权重保持，四个原方法分支的初始/最终/所选权重共12个哈希与旧归档精确一致。

## 本轮结果与程序决定

**以下都是验证开发集均值，与上一轮探测集不同，不能跨表计算提升。** 每种方法/模式保留两个种子及四个验证实例，越小越好。

| 方法 | fixed | joint |
|---|---:|---:|
| 原方法none | **10.25** | **7.5** |
| 历史均值running_mean | 11.875 | 8.875 |
| EDD | 5.75 | 3.0 |
| SPT | 7.75 | 4.0 |
| Random | 20.875 | 15.625 |
| CP最优参考 | 5.25 | 2.75 |

seed17的候选在两模式略好，seed29在两模式更差；完整分母合计后，两模式均保留none。未挑出好看的种子替换总体结果，也未自动改变生产默认值。候选裁剪次数降到1/256，但验证延期没有改善，不能用更小梯度或更多参数更新冒充性能提升。

单批8分支×64回合=512次更新、3072训练步，120主动秒上限，实际22.157秒；80/80验证计划及8/8CP参考通过，CP均OPTIMAL，模型API/网络调用0、新依赖0。只运行这一名候选，没有追加调参或改用探测集选模。[四组验证曲线](../experiments/results/exp_026_validation_iteration_v1/validation_curves.png)保留每个种子的过程。

此结果只拒绝当前小预算协议下的这一配置，不证明历史baseline普遍无效。反复用于检查点和算法选择的验证集属于开发数据，当前没有独立泛化或正式G3结论。

## 代码与运行

| 文件 | 用途 |
|---|---|
| [validation_diagnostics.py](../src/graduation/validation_diagnostics.py) | 核验旧来源/检查点并重放验证及前缀EDD，跳过probe/CP JSON子树 |
| [return_baseline.py](../src/graduation/return_baseline.py) | 有界、只读中心化与更新后原子记录历史均值 |
| [policy_training.py](../src/graduation/policy_training.py) | 默认none兼容；可选历史均值，只改变梯度权重，不改变回报 |
| [exp_026](../experiments/exp_026_validation_iteration.py) | 统一诊断、八分支对照、80验证计划/8CP、检查点和逐模式决定 |

```powershell
$iterationPython = if ($env:FJSP_CONDA_ENV) { Join-Path $env:FJSP_CONDA_ENV 'python.exe' } else { '.\.conda-env\python.exe' }
& $iterationPython -c "import sys; print(sys.executable)"
& $iterationPython experiments/exp_026_validation_iteration.py --episodes 64 --max-active-seconds 120
```

默认参考上一轮exp025归档，只恢复训练8例/验证4例，连probe生成器也不调用；`--reference-archive`可指定完整旧归档。已有输出目录拒绝覆盖。计费模型不参与，不读取`.env`。

只有全部8训练分支、80验证计划、8CP及控制权重检查完成才作决定；候选验证均值严格更低才选它，同分保留none，否则STOP。迟到的写入或预算耗尽不会成为COMPLETED。初始检查点被选中时继续标注未训练；区间之间的日志可能领先最近保存的参数，仍无自动精确续训承诺。

## 验证和证据

114项定向检查通过，独立审查无可执行问题。完整回归**1238通过、2跳过、覆盖率90.67%**，516.70秒；80%门槛不变，13条第三方弃用警告，跳过为Windows符号链接权限。

独立加载104个检查点，重放512次更新/3072步，逐项核对1536个候选原回报/历史均值/优势权重，重建8次检查点选择，验证192次greedy动作及80+8份计划，结果一致。当前没有G1/G2、R1/R2、编码器、神经网络数学、目标、合同或依赖变更，旧证据和权重保留。

[本轮摘要及决定](../experiments/results/exp_026_validation_iteration_v1/summary.json)、[程序诊断](../experiments/results/exp_026_validation_iteration_v1/diagnosis.json)、[全部结果与检查点索引](../experiments/results/exp_026_validation_iteration_v1/results.json)、[独立重放](../experiments/results/exp_026_validation_iteration_v1/independent_check.json)、[归档总哈希](../experiments/results/exp_026_validation_iteration_v1/archive_manifest.json)。

下一步优先检验策略对任务/机器重编号是否敏感：这些编号不应改变调度问题本身。若验证这种结构性问题，再考虑共享任务—机器评分，先过等变性和合法性检查；当前尚无该候选实现或收益证明。大创物流协同、正式毕设比较及完整自动科研外层仍未完成。
