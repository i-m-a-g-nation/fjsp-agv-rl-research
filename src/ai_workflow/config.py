from __future__ import annotations

from dataclasses import dataclass, field
import math
import os
from pathlib import Path
from typing import Literal
from src.ai_workflow.runtime_budget import RunBudget


def default_project_root() -> Path:
    """Return the root directory of fjsp-agv-rl-research."""

    return Path(__file__).resolve().parents[2]


def load_dotenv_if_present(env_path: Path | None = None) -> None:
    """Load key=value pairs from a local `.env` file into `os.environ` without overwriting set variables."""

    target = env_path or (default_project_root() / ".env")
    if not target.exists() or not target.is_file():
        return
    try:
        for raw_line in target.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception:
        pass


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for OpenAI-compatible LLM and Embedding endpoints.

    Automatically reads from `.env` in project root or environment variables.
    Supports DeepSeek, Qwen (DashScope), SiliconFlow, OpenAI, or local mock mode
    when no API key is set (for deterministic offline unit testing).
    """

    api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    base_url: str = field(
        default_factory=lambda: os.getenv(
            "OPENAI_BASE_URL",
            "https://api.deepseek.com",
        )
    )
    model_name: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL_NAME", "deepseek-chat")
    )
    embedding_model: str = field(
        default_factory=lambda: os.getenv(
            "EMBEDDING_MODEL_NAME",
            "text-embedding-3-small",
        )
    )
    embedding_backend: Literal["hybrid_local", "openai"] = field(
        default_factory=lambda: (
            "openai"
            if os.getenv("RAG_EMBEDDING_BACKEND") == "openai"
            else "hybrid_local"
        )
    )
    temperature: float = 0.2
    allow_fallback: bool = False
    request_timeout_seconds: float = 30.0
    max_output_tokens: int = 4096
    max_retries: int = 0
    budget: RunBudget | None = field(default=None, repr=False, compare=False)

    def provider_timeout(self, *, output_tokens: int) -> float:
        if self.budget is None:
            return self.request_timeout_seconds
        self.budget.reserve_provider_call(output_tokens=output_tokens, attempts=1 + self.max_retries)
        return min(self.request_timeout_seconds, self.budget.remaining_seconds())

    def __post_init__(self) -> None:
        if (not math.isfinite(self.request_timeout_seconds) or not 0 < self.request_timeout_seconds <= 60
                or type(self.max_output_tokens) is not int or not 1 <= self.max_output_tokens <= 8192
                or type(self.max_retries) is not int or not 0 <= self.max_retries <= 1):
            raise ValueError("Model call budget exceeds allowed timeout, token, or retry bounds")

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key and self.api_key.strip())
