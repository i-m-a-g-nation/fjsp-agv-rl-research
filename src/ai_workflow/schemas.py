from __future__ import annotations

from pydantic import BaseModel, Field


class MathematicalModelSpec(BaseModel):
    """Structured extraction of a scheduling paper's mathematical formulation."""

    sets_and_indices: list[str] = Field(
        default_factory=list,
        description="Sets and indices explicitly present in the paper text (or marked missing if abstract-only)",
    )
    parameters: list[str] = Field(
        default_factory=list,
        description="Model parameters explicitly present in the paper text",
    )
    decision_variables: list[str] = Field(
        default_factory=list,
        description="Decision variables explicitly present in the paper text",
    )
    objectives: list[str] = Field(
        default_factory=list,
        description="Objective functions explicitly stated in the paper text",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Key constraints explicitly stated in the paper text",
    )


class RLFormulationSpec(BaseModel):
    """Structured extraction of a reinforcement learning or dispatching formulation."""

    state_space: list[str] = Field(
        default_factory=list,
        description="State features or graph node/edge features from the paper",
    )
    action_space: list[str] = Field(
        default_factory=list,
        description="Action space definition from the paper",
    )
    action_masking: list[str] = Field(
        default_factory=list,
        description="Rules used to mask out invalid actions",
    )
    reward_function: str = Field(
        default="",
        description="Mathematical formula of step/terminal reward (if missing from text, explicitly state [缺失：原文未提供具体公式])",
    )
    network_architecture: str = Field(
        default="",
        description="Policy/value network or heuristic scoring structure",
    )


class CodebaseAlignmentSpec(BaseModel):
    """Mapping from the paper's concepts to `fjsp-agv-rl-research` modules."""

    reusable_modules: list[str] = Field(
        default_factory=list,
        description="Existing modules in src/ that directly support this paper",
    )
    missing_gaps: list[str] = Field(
        default_factory=list,
        description="Features required by the paper/project that are not yet in src/",
    )
    candidate_rule_description: str = Field(
        default="",
        description="How to express the paper's core heuristic/scoring idea using candidate tuple (job_id, op_id, machine_id, ready_time, start, finish, processing_time)",
    )


class PaperExtractionReport(BaseModel):
    """Full structured output produced by the literature extraction node."""

    title: str
    problem_type: str = Field(
        description="e.g., Static FJSP, Dynamic FJSP + AGV, Parallel Machine + Maintenance"
    )
    content_depth: str = Field(
        default="full_text",
        description="One of `full_text`, `abstract_only`, or `metadata_only`",
    )
    missing_warnings: list[str] = Field(
        default_factory=list,
        description="Explicit warnings about missing full text or unverified formulas (anti-hallucination guard)",
    )
    resolution_log: list[str] = Field(
        default_factory=list,
        description="Step-by-step log of automatic online PDF/abstract resolution",
    )
    math_model: MathematicalModelSpec
    rl_formulation: RLFormulationSpec
    codebase_alignment: CodebaseAlignmentSpec
    retrieved_sources: list[str] = Field(default_factory=list)

    def to_markdown(self) -> str:
        """Render the structured extraction report as clean Markdown."""

        depth_badge = {
            "full_text": "✅ `full_text`（已获取并解析论文 PDF 全文与公式）",
            "abstract_only": "⚠️ `abstract_only`（闭源期刊未公开 PDF，已联网抓取官方摘要，具体公式未脑补）",
            "metadata_only": "❌ `metadata_only`（仅含标题/链接元数据，缺失正文与公式）",
        }.get(self.content_depth, self.content_depth)

        lines = [
            f"# 文献深度解析与代码对齐报告：{self.title}",
            "",
            f"- **问题类型**：{self.problem_type}",
            f"- **文献正文完整度**：{depth_badge}",
            f"- **RAG 检索参考源**：{', '.join(self.retrieved_sources) if self.retrieved_sources else '无'}",
            "",
        ]
        if self.resolution_log:
            lines.extend(
                [
                    "## 0. 自动联网全文/摘要解析日志 (Auto-Fetch Resolution Log)",
                    *[f"- {entry}" for entry in self.resolution_log],
                    "",
                ]
            )
        if self.missing_warnings:
            lines.extend(
                [
                    "> [!WARNING]",
                    "> **防幻觉审查提示（缺失内容说明）**：",
                    *[f"> - {w}" for w in self.missing_warnings],
                    "",
                ]
            )

        lines.extend(
            [
                "## 1. 数学模型提取 (Mathematical Model)",
                "### 集合与索引",
                *[f"- {item}" for item in self.math_model.sets_and_indices],
                "### 参数",
                *[f"- {item}" for item in self.math_model.parameters],
                "### 决策变量",
                *[f"- {item}" for item in self.math_model.decision_variables],
                "### 目标函数",
                *[f"- {item}" for item in self.math_model.objectives],
                "### 约束条件",
                *[f"- {item}" for item in self.math_model.constraints],
                "",
                "## 2. 强化学习 / 调度决策设计 (RL & Dispatching Design)",
                "### 状态空间 (State Space)",
                *[f"- {item}" for item in self.rl_formulation.state_space],
                "### 动作空间 (Action Space)",
                *[f"- {item}" for item in self.rl_formulation.action_space],
                "### 动作掩码 (Action Masking)",
                *[f"- {item}" for item in self.rl_formulation.action_masking],
                f"### 奖励函数 (Reward Function)\n{self.rl_formulation.reward_function}",
                f"### 网络与算法架构\n{self.rl_formulation.network_architecture}",
                "",
                "## 3. 与当前项目 (`fjsp-agv-rl-research`) 接口对齐分析",
                "### 可直接复用的现有模块",
                *[f"- {item}" for item in self.codebase_alignment.reusable_modules],
                "### 待扩展差距 (Gap Analysis)",
                *[f"- {item}" for item in self.codebase_alignment.missing_gaps],
                "### 候选派工规则 / 评分函数转化方案",
                self.codebase_alignment.candidate_rule_description,
                "",
            ]
        )
        return "\n".join(lines)
