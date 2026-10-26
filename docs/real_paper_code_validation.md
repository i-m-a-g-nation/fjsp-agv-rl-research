# 首轮真实论文与代码验证

后续进展：[单字段短片段验证](paper_field_validation.md)已用新的有界批次完成两次max调用及引用定位。本页保留首轮失败经过，不能用后续成功覆盖历史记录。

**来源绑定和静态对照完成；真实 max 提取没有通过。** 新增程序入口可以获取/复用固定来源、核验提交及文件、构造带物理页码的上下文，并保存有界模型调用及失败。尚未执行原论文方法、训练模型或把候选算法应用到项目。

## 本次选了什么

Li 等人的 [A transformer-based deep reinforcement learning approach for dynamic parallel machine scheduling problem with family setups](https://doi.org/10.1007/s10845-024-02470-8)，在线发表于2024年、卷期2025年。出版社 Data availability 直接链接作者 [Transformer4PMSP](https://github.com/ASnowbow/Transformer4PMSP)，README 反向链接论文 DOI。

- 论文：34页，官方 PDF SHA256 `50ff0f7d470550cf3c13c5234538a7f9c80a84aae8a70ee3454b6de3b1b24993`，CC-BY-4.0；完整 PDF 留在本机忽略目录。
- 作者代码：固定提交 `b4b46b92aa67556391b7e2613ac1213dafe16c60`，真实根 tree `a74db1b7e90424b4c85452b95409fe1c3a8f1d65`，MIT。选取9个源文件，逐个核对 Git blob SHA1、SHA256、大小及许可证。
- 只读源文件与静态 AST 函数索引；没有安装作者依赖、执行作者程序或加载预训练权重。

论文同样优化总延期，但有动态到达、机器速度差异和换型，未建模本项目的强制维护。论文第27物理页将维护列为未来扩展，不能把它视为本毕设的现成维护模型。

## 实际运行结果

| 尝试 | 结果 | 模型调用 |
|---|---|---:|
| 匿名获取 | GitHub 返回403，停止来源阶段 | 0 |
| 连接器缓存首验 | commit/tree标识不一致，被拒绝；随后按真实tree重新获取 | 0 |
| 初次论文片段提取 | 来源验证通过；模型输出 JSONDecodeError，当时未保留结束元数据，不能确定具体原因 | 1 |
| 缩小片段并记录诊断 | `length`，8192生成tokens全部为思考，最终答案为空 | 1 |
| 一次较长论文专用请求 | `length`，16384生成tokens全部为思考，最终答案仍为空 | 1 |

累计 **3次调用，输出预占32768，主动执行204.141秒**，未超过预设4次/32768/300秒。每次失败均保留，续批次从剩余额度中扣减；没有通过新目录重置本轮资源额度。最后一次用尽输出预占后停止，没有再调用模型。

`paper_excerpt` 是显式构造、必须绑定 `RunBudget` 的论文专用请求类型，上限16384/120秒；不能通过 `.env` 启用。普通 `bounded` 类型的默认4096/30和上限8192/60均保持。大请求仍先预占整个输出上限，计数失败也不退款。

这些结果不能推出 max 无法处理论文，只说明当前请求设计与预算没有得到可验收的最终答案。下一轮应先实现按字段/段落的短上下文，不继续整页投入，也不把人工阅读的结果冒充程序提取成功。

## 已核实的论文—源码差异

| 项目 | 可查证事实 | 对本项目的决定 |
|---|---|---|
| 零延期奖励 | 论文第15物理页写 `R_opt=200`；固定版本 `config.py` 的 `final_reward=100` | 分开保存论文与代码行为；拒绝直接复制奖励 |
| 奖励与目标 | 作者环境还有依赖顺序的换型奖励，γ=.99；本项目没有换型，R1要求未折扣回报精确为 `-总延期/100` | 保留现有奖励及目标，不把作者 shaping 当作保持目标不变的证明 |
| 动作与维护 | 作者先选最早空闲机器，策略选job；没有每机强制维护动作 | 保留R1原动作、维护窗口、idle机器维护和领域checker |
| 主模型验证配置 | 默认 `1HeadAttention-1`，论文主方法是2-head；`bool("0")` 还会把消融标志解析为真 | 原方法复现必须另行固定配置，当前未执行复现 |
| 全局状态 | 论文使用全局job/machine信息；R1已经保存任务及全部机器尾部 | token/attention编码可列为未来候选，不能当作补上了R1缺失信息或已实现创新 |

这些是基于原文和固定代码的静态阅读/常量解析，不是作者训练效果的运行结论。其他 padding/GAE 风险还需独立复现，不据此宣称其公开结果无效。

## 人如何运行

入口：[exp_023](../experiments/exp_023_paper_code_validation.py)，原始请求：[paper_code_validation_v1.json](../experiments/requests/paper_code_validation_v1.json)。运行脚本会获取公开来源；**默认不加载 `.env`、不调用模型**。`--extract` 才启用本机max配置和计费调用。与018三审路线分开，没有新增自动批准能力。

先选专用环境并核对路径，然后只复跑来源验证：

```powershell
$paperPython = if ($env:FJSP_CONDA_ENV) { Join-Path $env:FJSP_CONDA_ENV 'python.exe' } else { '.\.conda-env\python.exe' }
& $paperPython -c "import sys; print(sys.executable)"
& $paperPython experiments/exp_023_paper_code_validation.py --repository-cache experiments/results/exp_023_real_paper_code_v1/repository_cache --pdf-cache papers/auto_fetched/transformer4pmsp_2026-10-26/paper.pdf
```

本机 PDF 不存在时可省略 `--pdf-cache`，程序尝试从已固定的官方URL下载并验SHA。缓存选项不跳过身份校验；完整来源缓存由已连接的 GitHub 工具获得，并明确记录 `cached_github_records`。当前环境的匿名GitHub入口403问题未被伪称修复，新的论文发现/连接器编排仍待接入。

已用归档缓存实际复跑得到 `SOURCES_VERIFIED_UNREVIEWED`、模型调用0。**此状态只说明来源完整性及文本关联通过，不能替代文献语义审核。**

## 证据与当前边界

- [本轮汇总及累计预算](../experiments/results/exp_023_real_paper_code_v1/batch_summary.json)
- [论文—代码对照及迁移决定](../experiments/results/exp_023_real_paper_code_v1/paper_code_alignment.json)
- [最后一次真实响应诊断](../experiments/results/exp_023_real_paper_code_v1/run_5_result.json)
- [来源缓存、许可与归档哈希](../experiments/results/exp_023_real_paper_code_v1/manifest.json)，原文/源码归属见 [ATTRIBUTION](../experiments/results/exp_023_real_paper_code_v1/ATTRIBUTION.json)

完整回归 **904通过、1跳过、覆盖率89.72%**。跳过项是Windows无法创建符号链接的测试；其他路径和缓存校验通过。13条第三方弃用警告；80%覆盖门槛不变。独立审查发现的无效URL落盘、超时后仍成功两处问题均以回归测试修复，后续缓存/诊断/专用请求类型复审无新问题。

本轮没有完成受控代码候选、RL训练或结果驱动的自动实验选择。毕设与大创仍未达成；下一步是字段级提取验收，通过后再进入独立的维护模型适配实验。
