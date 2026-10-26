# 毕设观察的28×13纯编码器

后续[神经策略与有界试训](graduation_neural_policy_pilot.md)已实际消费该矩阵并保存训练权重；本页保留纯编码器及R2回放验证范围。

纯数据接口已实现，代码在[编码器模块](../src/graduation/state_encoding.py)。它把R1已有任务/机器特征放进统一矩阵，并能完整还原原观察。没有网络、训练器或新依赖；调度环境、R2规则、领域checker和目标均沿用原实现。

## 如何使用

```python
from src.graduation.state_encoding import (
    encode_construction_observation,
    decode_construction_observation,
)

observation = env.observe()  # 原有 ParallelMaintenanceEnv
encoded = encode_construction_observation(observation)
assert decode_construction_observation(encoded) == observation
rows = encoded.rows          # 28行，每行13个float，不可变tuple
mask = encoded.action_mask   # 原样保留的100个bool
```

直接导入该模块；原`src.graduation`包导出未改动。`TypedStateEncoding`包含原`mode/status/steps/scale/action_mask`，以及`rows/version=1`。不是把矩阵单独交给策略就足够：动作掩码、模式等辅助字段也必须携带。

前24行对应固定任务槽，载荷在0–2列；后4行是固定机器槽，载荷在3–9列。10–11列表示任务/机器类型，12列表示presence。padding也保留槽类型，载荷为0、presence为0；已安排任务仍为presence1，scheduled单独保留。完整列定义见[原方案](graduation_state_encoding_candidate.md)。

特征值直接复制，保留`-1`缺失固定维护时刻、浮点尾数及有效载荷的零符号，不重新归一化或重排。机器整数时间仍由环境保存，不能从矩阵浮点值重建。最多24任务/4机器，不裁剪或推断额外对象。

## 拒绝哪些输入

接口只接收对应类型的观察/编码；要求不可变tuple、完整行列、有限的Python内置float、布尔presence/动作掩码和合法辅助字段类型。特征中的int/bool不会悄悄转成float。非二值标志、错误行类型、非零padding或跨类型载荷、未知版本、NaN/Inf均拒绝。

这些是传输格式检查，不重新判断调度可行性，也不重新计算动作mask。编码创建和解码都会验证；即使绕过frozen约束篡改对象，解码仍会拒绝非法数据。JSON重载使用者需恢复tuple结构和原类型，不通过裁剪、补零或类型强转掩盖格式错误。

## 回放验证证明什么

新增[exp_024](../experiments/exp_024_state_encoding_check.py)：沿用exp022的四个字面算例（单机、双机、闲置机维护、后置维护），两种维护模式、EDD/SPT/Random三规则、seed42，总计24组。

脚本先获取原R2动作序列，再在新环境回放。每步保存原观察、编码矩阵、精确整数尾部及动作/奖励；逐项检查往返和固定列定义。原计划与回放计划分别经过原G1 checker、总延期独立重算、回报核对及无求解器证书检查。失败行保留trace和错误类型，接受的计划/指标置空，不因已有有效baseline而放行坏回放。

这验证的是数据传输与已有动作的回放一致性。R2仍使用原规则，没有新策略实际消费矩阵；结果一致不能证明新表示提升性能或复现论文算法。

独立手写矩阵样例和手写解码输入防止编解码同时写错列而互相抵消；故障注入覆盖错位映射、坏mask、NaN、浮点替代整数时钟及缺失维护。仅往返相等不足以通过这些测试。

## 人如何复跑

实际完成两次原生运行，各24/24通过，确定性摘要均为`f1464209a5d885f419e06e00d5f3e342a693b52f434ea486f719d9ce2494a107`。从保存文件再次独立恢复核对了48组、624份状态快照和96份计划。两次`results.json`字节完全一致，归档共享一份，保留两份运行manifest。

[结果汇总](../experiments/results/exp_024_state_encoding_v1/summary.json)、[独立恢复核对](../experiments/results/exp_024_state_encoding_v1/independent_check.json)、[全部逐步数据](../experiments/results/exp_024_state_encoding_v1/results.json)、[归档哈希](../experiments/results/exp_024_state_encoding_v1/manifest.json)。

定向测试70通过；完整专用环境回归**1075通过、2跳过、覆盖率89.99%**，351.82秒；80%门槛保持，13条第三方弃用警告，两项跳过均为Windows符号链接权限。独立审查发现的非字符串字典键导致失败材料无法落盘问题，已先复现失败、修复并通过完整回归。

```powershell
$codecPython = if ($env:FJSP_CONDA_ENV) { Join-Path $env:FJSP_CONDA_ENV 'python.exe' } else { '.\.conda-env\python.exe' }
& $codecPython -c "import sys; print(sys.executable)"
& $codecPython experiments/exp_024_state_encoding_check.py
```

默认新建结果目录；`--output-dir`可指定新的目录，已有目录拒绝覆盖。全程离线、模型调用0，不读取`.env`。结果包含输入、逐步矩阵和原始状态、奖励、计划、源码/产物哈希及确定性摘要，便于检查和重放。

下一步应把表示接到训练前的观察接口，确认策略同时正确使用presence、行类型和动作mask，再进入有界训练对照。当前大创/毕设均未验收，自动论文发现、受控改码、训练比较和结果驱动迭代仍未形成完整闭环。
