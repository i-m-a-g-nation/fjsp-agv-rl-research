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
LLM_THINKING_MODE=disabled
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
| 本项目思考默认值 | `LLM_THINKING_MODE=disabled`；对现有短文本提取和受限候选生成，显式传入 `extra_body={"thinking":{"type":"disabled"}}`，这是本项目选择 |
| 可选开启 | 改为 `LLM_THINKING_MODE=enabled`；只对官方 DeepSeek 主机发送此选项，其他兼容服务不接收 DeepSeek 专用字段 |
| RAG | `hybrid_local` 使用本地检索/哈希向量，不要求 DeepSeek chat 服务提供 embedding；不要仅因 chat 配通就改成远程 embedding |

开启思考不会增加现有每次请求的输出、超时、重试或会话预算，也不会给模型增加训练、任意工具或自主修改项目源码的能力。需要调整预算时应单独设计和审核，不能把一个开关当成完整研究系统。

本项目已为现有LangChain客户端的字段转换增加适配：官方DeepSeek请求使用`max_tokens`，不发送`max_completion_tokens`。通过SDK的`extra_body`合入真实HTTP请求体，避免客户端自动改名破坏接口或预算；两个调用入口均有内存HTTP测试。依据为[官方参数表](https://api-docs.deepseek.com/api/create-chat-completion/)和[官方集成兼容说明](https://api-docs.deepseek.com/quick_start/agent_integrations/oh_my_pi/)。这不等于真实密钥的在线连通已验证。

## 4. Flash1017 适不适合这个项目

**可以继续作为受检查的工作助手，但当前非思考模式未通过首次小样本全部验收。** [2026-10-26 真实接口诊断](model_api_validation_2026-10-26.md)已确认连通；同时发现一个调度数值/计划不一致，以及 4 条缺少逐项引用的提取陈述。这不是完整模型评测，尚无模型对比实验支持：

- 文献筛读、结构化提取、原文片段定位：适合先用少量人工标注样本检验，逐项核对原文支持关系。
- 受限静态派工候选函数：接口能承载现有短调用，生成结果仍须经过代码约束、隔离执行和独立合法性检查。
- 数学建模、论文复现、算法优势和训练方案：目前不能据模型名称或接口可用性给出正确性、创新性或性能保证。

继续评价提取准确率、引用支持关系、候选合法率和真实调用耗时，再决定是否需要更强模型或思考模式。连通已验证，真实论文质量、思考模式和模型对比仍未验证；不据此承诺模型优于其他方案，也不编造价格。
