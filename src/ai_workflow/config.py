from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Literal


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


load_dotenv_if_present()


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

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key and self.api_key.strip())
