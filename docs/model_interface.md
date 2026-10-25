# 模型接口：配置、检查与 DeepSeek 选择

**只需在当前工作树根目录的 `.env` 填密钥。** 配置模板是[`.env.example`](../.env.example)，程序配置在[`src/ai_workflow/config.py`](../src/ai_workflow/config.py)。无需把密钥写进 Python 文件。

## 1. 填配置

如果当前根目录还没有 `.env`，从模板复制一次；已有文件不要覆盖：

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
```

打开 `.env`，填写自己的官方 DeepSeek API key：

```dotenv
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.deepseek.com
LLM_MODEL_NAME=deepseek-flash
LLM_THINKING_MODE=enabled
LLM_REASONING_EFFORT=max
LLM_MAX_OUTPUT_TOKENS=8192
LLM_REQUEST_TIMEOUT_SECONDS=60
RAG_EMBEDDING_BACKEND=hybrid_local
```

`OPENAI_` 是兼容客户端使用的变量名，此处连接的是 DeepSeek 官方 API。SDK 的 base URL 填服务根地址，不追加 `/chat/completions`。模型填写官方 API ID `deepseek-flash`，不要填展示名 `DeepSeek-V4.1-Flash-1017` 或其他平台的模型 ID。

`.env` 被 Git 忽略，只属于这份检出目录；合并分支不会把它复制到 main 所在目录。`.env.example` 是可提交的空密钥模板。切换到另一工作树或机器时，在那里单独创建 `.env`。当前工作树可以直接检查和运行，不以先合并 main 为前提。

已有进程环境变量优先于 `.env`；修改文件后若看不到预期设置，先检查终端是否已设置同名变量。`LLMConfig()` 本身只读取进程环境，不自动加载文件；现有 CLI 的 live 模式和显式配置检查器才加载 `.env`。默认 offline 路线不因填写密钥而自动变成在线。

## 2. 离线检查

在项目根目录运行。专用环境不存在时先执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_env.ps1
```

选择专用 Python 并打印路径：

```powershell
$modelPython = if ($env:FJSP_CONDA_ENV) { Join-Path $env:FJSP_CONDA_ENV 'python.exe' } else { '.\.conda-env\python.exe' }
& $modelPython -c "import sys; print(sys.executable)"
```

确认输出确实位于 `.conda-env` 或 `FJSP_CONDA_ENV` 指定的专用目录，随后运行：

```powershell
& $modelPython scripts/check_model_config.py
```

也可用 `--env-file <文件路径>` 显式指定配置文件。检查器只做本地配置检查，显示密钥是否存在的布尔值，不显示密钥；密钥缺失或配置无效时返回 1。空模板未填密钥时失败是预期行为。

**通过只说明配置完整且通过本地校验。** 它不发网络/API 请求，不验证密钥有效性、账户额度、真实连通性或模型效果。实际在线运行仍通过 [`exp_018`](../experiments/exp_018_ai_rag_workflow.py) 的 live 路线及范围、证据、结论三道人审，参照[工作流说明](research_workflow.md)，并使用新会话；修改模型配置不能继承旧配置的批准。

## 3. 官方接口与本项目选择

以下官方信息最近核对日期为 **2026-10-26**，服务名称和供应版本以后可能变化：

| 项目 | 官方信息 / 本项目设置 |
|---|---|
| 官方服务 | `https://api.deepseek.com`；官方模型 ID `deepseek-flash` 当前由 `DeepSeek-V4.1-Flash-1017` 提供服务，见[官方首次 API 调用说明](https://api-docs.deepseek.com/api/responses) |
| 当前调用方式 | 本项目现有客户端使用 OpenAI 兼容 Chat Completions，即 `POST /chat/completions`，见[官方 Chat Completions 文档](https://api-docs.deepseek.com/api/create-chat-completion/) |
| 官方思考默认值 | 官方当前默认开启思考、使用 high effort，见[官方思考模式说明](https://api-docs.deepseek.com/guides/thinking_mode/) |
| 当前本地配置 / 新模板 | `LLM_THINKING_MODE=enabled` 加 `LLM_REASONING_EFFORT=max`；实际 HTTP 请求包含 `thinking={"type":"enabled"}` 和 `reasoning_effort="max"`，两者共同表达当前选择 |
| 构造器兼容默认值 | 没有显式加载 `.env` 或传参时，`LLMConfig()` 仍默认思考关闭，effort 值为 max；关闭时不发送 effort。填了文件不等于所有 Python 调用都已加载文件 |
| 可选降档 / 关闭 | effort 支持 `low/high/max`；模式支持 `enabled/disabled`。其他兼容服务不接收 DeepSeek 专用字段 |
| RAG | `hybrid_local` 使用本地检索/哈希向量，不要求 DeepSeek chat 服务提供 embedding；不要仅因 chat 配通就改成远程 embedding |

开启 max 不会自动增加会话预算；思考和最终回答都受生成上限约束。预算不足、空回答、截断和超时均不能当作成功。未配置时仍默认 4096 tokens / 30 秒；当前本地与新模板明确设置 `LLM_MAX_OUTPUT_TOKENS=8192`、`LLM_REQUEST_TIMEOUT_SECONDS=60`，均在原有硬上限内。持久会话默认输出预占 16384：提取及一次纠正各用 8192 时会用完，后续生成可能因预算不足停止。模型不会因此增加训练或修改项目源码的工具能力。

本项目已为现有LangChain客户端的字段转换增加适配：官方DeepSeek请求使用`max_tokens`，不发送`max_completion_tokens`。通过SDK的`extra_body`合入真实HTTP请求体，避免客户端自动改名破坏接口或预算；两个调用入口均有内存HTTP测试，覆盖思考关闭及开启时的 low/high/max。依据为[官方参数表](https://api-docs.deepseek.com/api/create-chat-completion/)和[官方集成兼容说明](https://api-docs.deepseek.com/quick_start/agent_integrations/oh_my_pi/)。请求字段正确与某次真实调用质量通过是不同的验证结论。

## 4. 引用缺项怎样处理

在线提取后逐条重新检查引用位置；缺失、无效、重复未消歧的引用或无有效陈述会触发一次纠正，精确反馈字段和下标。每次调用仍先预占原有预算；纠正不等于 SDK 网络重试。`LLMConfig.extraction_repair_attempts` 仅允许 0 或 1，默认 1。

两次完成的提取仍不完整时，状态为 `EVIDENCE_INCOMPLETE`，保留每次报告及诊断，代码生成、沙箱、调度实验和实验记忆均不执行。完整时仍标记 `unverified` 并进入原有 evidence 人审；定位完整不证明语义或公式正确。离线模板及显式降级仍有独立标签，不能作为论文证据。

持久会话在每次提取完成后立即写入会话根目录的 `extraction-attempts.json`，因此纠正请求超时、解析失败或预算耗尽时仍保留第一次材料；错误类型保留，错误消息正文不写入诊断。预算耗尽继续按原有状态停止，不自动加预算。若调用者显式允许降级，旧的降级策略保留，失败材料另附在 `extraction_quality.failed_live_extraction` 中，不能被模板覆盖。

## 5. Flash1017 适不适合这个项目

**可以继续作为受检查的工作助手，但当前非思考模式未通过首次小样本全部验收。** [2026-10-26 真实接口诊断](model_api_validation_2026-10-26.md)已确认连通；同时发现一个调度数值/计划不一致，以及 4 条缺少逐项引用的提取陈述。这不是完整模型评测，尚无模型对比实验支持：

后续 [max 档诊断](model_api_max_validation_2026-10-26.md)用相同输入验证，调度答案一致、引用 7/7 可定位，未触发纠正；实际请求均为 enabled/max。输出与时间预算同时调整，两个样本不构成受控模型对比，也不验证真实论文质量。

- 文献筛读、结构化提取、原文片段定位：适合先用少量人工标注样本检验，逐项核对原文支持关系。
- 受限静态派工候选函数：接口能承载现有短调用，生成结果仍须经过代码约束、隔离执行和独立合法性检查。
- 数学建模、论文复现、算法优势和训练方案：目前不能据模型名称或接口可用性给出正确性、创新性或性能保证。

继续评价提取准确率、引用支持关系、候选合法率和真实调用耗时，再决定是否需要其他模型。连通及 max 小样本已验证，真实论文质量和模型对比仍未验证；不据此承诺模型优于其他方案，也不编造价格。
