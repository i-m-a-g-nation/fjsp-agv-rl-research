# 已运行的神经策略与有界试训

**矩阵输入→合法动作→完整计划→策略梯度更新→验证集选模已跑通。** 本轮是NumPy小型MLP与REINFORCE工程基线，尚未优于EDD，也不是PPO或原论文Transformer复现。大创、毕设均未验收，论文到代码的自动科研迭代还未接通。

## 实际训练结果

四个分支为fixed/joint×训练seed17/29，每个64回合，共256次回合更新、1536训练步；单进程线程环境设为1。最多120主动秒，实际10.578秒，模型API/网络调用0，新增依赖0。四个最终网络参数均实际改变；部分零梯度更新不改变参数，如实记录。

| 探测集平均总延期，越小越好 | fixed | joint |
|---|---:|---:|
| 初始未训练神经策略 | 17.5 | 10.75 |
| 最后一次更新后的策略 | 13.125 | 9.5 |
| **只按验证集选出的策略** | **16.125** | **10.75** |
| EDD | 3.5 | 2.25 |
| SPT | 6.75 | 3.0 |
| Random | 23.0 | 13.0 |
| CP-SAT最优参考 | 3.25 | 2.25 |

每个模式有四个探测算例，神经/规则均保留两个种子的八行结果；CP同一批四例共享参考。96份策略/规则计划全部过原G1检查及独立延期重算，8份CP均OPTIMAL；没有候选优于其最优目标的矛盾。

这是两个种子、四任务双机的工程探测，不是正式G3测试或统计优势证明。最后模型在探测集有更低均值，仍按预先规定的验证集选模，不能改挑探测集最好模型。joint/seed17的验证集最好仍为第0回合，保存并标注为**未训练初始模型**；不能把它当成训练收益。

本轮决定：保留可复跑基线及全部权重，承认与EDD的差距，不追加超参数搜索、不改奖励或维护约束。下一轮先从验证轨迹诊断动作选择，再定义新的有限改进试验。

## 新代码与算法边界

| 文件 | 作用 |
|---|---|
| [neural_policy.py](../src/graduation/neural_policy.py) | 消费完整28×13矩阵、模式/状态/步数/scale辅助字段；372→16(tanh)→100，7668个float64参数；相同掩码用于采样、梯度和greedy评估 |
| [policy_training.py](../src/graduation/policy_training.py) | 完整合法回合后做一次REINFORCE更新；gamma=1，逐步reward-to-go，原奖励保持；验证集挑最早最好检查点 |
| [exp_025](../experiments/exp_025_neural_policy_pilot.py) | 固定数据/种子/预算，持久化日志与NPZ检查点、8CP参考、96探测行和失败分母 |

输入的364个矩阵值直接使用，另加mode两项、status四项、steps/28与log1p(scale)/log1p(2**50)。这是独立策略输入变换，原纯编码器及环境不变。非法动作概率和对应logit梯度为0；没有合法动作或数值异常时失败，不偷偷换动作。训练、评估都读取真实mask。

采用[REINFORCE原论文](https://doi.org/10.1007/BF00992696)的策略梯度思路；[动作掩码原论文](https://arxiv.org/abs/2006.14171v3)仅作为方法依据。实现中的矩阵格式、有限环境和试训协议是本项目设计，未声称复现这些论文的效果。已查阅[NumPy2.4 Generator](https://numpy.org/doc/2.4/reference/random/generator.html)与[tanh接口](https://numpy.org/doc/2.4/reference/generated/numpy.tanh.html)。专用环境实际为NumPy2.4.5，无Torch/Gymnasium/SB3；REINFORCE是开发者选择的最小基线，PPO与最终课题算法仍未确定。

## 训练数据和检查点怎样防止混淆

新生成器独立于G3草案和已有开发算例：训练8例、验证4例、探测4例，字段随机流和种子冻结。按底层任务(p,d)身份排除跨分割重复，不能只换维护条件就算新数据。探测集不进入梯度或检查点选择，也不是最终未见测试集。

训练回合必须n+m步齐备、每台机器维护一次、完整维护区间可行；原checker和延期重算通过后才更新。回报仍为`-总延期/100`，无折扣、换型奖励或终端奖励，梯度仅做明确的范数截断。保持原R1/R2、G1/G2、合同和依赖声明。

NPZ仅载入有限float64数组，`allow_pickle=False`，绑定文件/参数/源码/数据/配置哈希。初始、最终、所选和各验证区间状态均保存。超时/错误保留已有日志和最近检查点；两个验证点之间最近参数快照可能早于最新回合日志，当前没有自动精确续训承诺。

## 如何运行与载入

```powershell
$policyPython = if ($env:FJSP_CONDA_ENV) { Join-Path $env:FJSP_CONDA_ENV 'python.exe' } else { '.\.conda-env\python.exe' }
& $policyPython -c "import sys; print(sys.executable)"
& $policyPython experiments/exp_025_neural_policy_pilot.py --episodes 64 --max-active-seconds 120
```

新建输出目录，已有目录拒绝覆盖；`--episodes 1`可做微型接口检查，但仍保留四分支/96探测/8CP分母。程序不读取`.env`。DeepSeek用于文献工具，本轮策略学习在本机CPU执行。

归档[固定模式seed17所选权重](../experiments/results/exp_025_neural_policy_v1/checkpoints/fixed-seed17/selected.npz)及[元数据](../experiments/results/exp_025_neural_policy_v1/checkpoints/fixed-seed17/selected.json)可通过`exp_025.load_checkpoint(path, expected_sha256=元数据中的sha256)`加载，然后调用`run_policy_episode(..., deterministic=True)`；应匹配数据/源码/编码版本及模式，不能直接把权重用于不同问题。

## 验证与证据

数值差分核对梯度、更新方向、掩码及原子失败；数据隔离、验证选择、预算边界、检查点重载和CP矛盾故障测试均通过。独立审查指出的“验证已完成但预算检查先于持久化回调”问题，已先复现再修复。

完整回归：**1163通过、2跳过、覆盖率90.15%**，463.07秒；80%门槛保持，13条第三方弃用警告，两跳过均为Windows符号链接权限。独立核对52个检查点，从日志重放256次更新/1536步，重建四次选模，逐步验证288次检查点greedy动作，并复检96策略计划和8CP计划，均一致。

[结果摘要](../experiments/results/exp_025_neural_policy_v1/summary.json)、[原生manifest](../experiments/results/exp_025_neural_policy_v1/manifest.json)、[全部结果/日志索引](../experiments/results/exp_025_neural_policy_v1/results.json)、[独立重放检查](../experiments/results/exp_025_neural_policy_v1/independent_check.json)、[归档总哈希](../experiments/results/exp_025_neural_policy_v1/archive_manifest.json)。这些证据证明本轮工程执行与保存结果，不证明科研创新、泛化或课题完成。
