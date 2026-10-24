from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable, Literal

import faiss
import numpy as np

from src.ai_workflow.config import LLMConfig, default_project_root
from src.ai_workflow.runtime_budget import BudgetExceeded

ChunkCategory = Literal["literature", "codebase", "experiment_memory"]


@dataclass(frozen=True)
class KnowledgeChunk:
    """One indexed document chunk in the local RAG store."""

    chunk_id: str
    category: ChunkCategory
    source_path: str
    title: str
    content: str
    score: float = 0.0
    track_id: str = "shared"
    review_status: str = "reference"


class LocalEmbeddingsProvider:
    """Hybrid embedding provider supporting OpenAI API or deterministic local hashing.

    Why support both?
    1. When `OPENAI_API_KEY` + `RAG_EMBEDDING_BACKEND=openai` are configured,
       it calls the OpenAI-compatible embedding endpoint (e.g., BGE-M3 on
       SiliconFlow, DashScope text-embedding-v3, or OpenAI).
    2. By default (`hybrid_local`), it computes a fast, character/word n-gram
       L2-normalized feature vector (dim=512) using FAISS IndexFlatIP. This
       works 100% offline in CI/pytest and handles mixed Chinese + English +
       LaTeX math formulas (`C_max`, `p_{ijk}`, `ScheduleResult`) reliably
       without requiring a multi-GB model download.
    """

    def __init__(self, config: LLMConfig | None = None, dim: int = 512) -> None:
        self.config = config or LLMConfig()
        self.dim = dim

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)

        if self.config.embedding_backend == "openai" and self.config.has_api_key:
            try:
                from openai import OpenAI

                client = OpenAI(
                    api_key=self.config.api_key,
                    base_url=self.config.base_url,
                    timeout=self.config.provider_timeout(output_tokens=0),
                    max_retries=self.config.max_retries,
                )
                response = client.embeddings.create(
                    model=self.config.embedding_model,
                    input=texts,
                )
                vecs = np.array(
                    [item.embedding for item in response.data],
                    dtype=np.float32,
                )
                faiss.normalize_L2(vecs)
                return vecs
            except BudgetExceeded:
                raise
            except Exception as exc:
                # Mixing remote and local vector spaces would invalidate retrieval.
                raise RuntimeError("Embedding request failed; vector backend was not silently changed") from exc

        return self._embed_local_ngrams(texts)

    def _embed_local_ngrams(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dim), dtype=np.float32)
        token_pattern = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]")

        for row_idx, text in enumerate(texts):
            lowered = text.lower()
            tokens = token_pattern.findall(lowered)
            # Combine unigrams, bigrams, and trigrams for semantic + symbol recall
            features: list[str] = list(tokens)
            features.extend(
                f"{tokens[i]}_{tokens[i + 1]}" for i in range(len(tokens) - 1)
            )
            features.extend(
                f"{tokens[i]}_{tokens[i + 1]}_{tokens[i + 2]}"
                for i in range(len(tokens) - 2)
            )
            if not features:
                features = [lowered[:32]]

            for feat in features:
                digest = hashlib.md5(feat.encode("utf-8")).digest()
                bucket = int.from_bytes(digest[:4], "little") % self.dim
                sign = 1.0 if (digest[4] & 1) == 0 else -1.0
                # Boost domain-critical scheduling/RL terms
                weight = 2.0 if len(feat) > 3 else 1.0
                matrix[row_idx, bucket] += sign * weight

        faiss.normalize_L2(matrix)
        return matrix


class ResearchRAGStore:
    """FAISS-backed local RAG knowledge base for FJSP-AGV-RL research.

    Indexes three distinct knowledge domains:
    1. `literature`: Papers in `notes/papers/`, `papers/`, `.tex` math models, and PDFs
    2. `codebase`: Core Python contracts (`src/data`, `src/scheduling`, `src/dynamic`, `src/solvers`)
    3. `experiment_memory`: Historical experiment logs and AI evolution records
    """

    def __init__(
        self,
        project_root: Path | None = None,
        config: LLMConfig | None = None,
        chunk_size: int = 900,
        chunk_overlap: int = 150,
    ) -> None:
        self.project_root = project_root or default_project_root()
        self.config = config or LLMConfig()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.embedder = LocalEmbeddingsProvider(self.config)
        self.chunks: list[KnowledgeChunk] = []
        self.index: faiss.IndexFlatIP | None = None

    def build_from_workspace(
        self,
        extra_paths: Iterable[Path] = (),
    ) -> int:
        """Scan workspace literature, codebase, and experiment memory into FAISS."""

        collected: list[KnowledgeChunk] = []

        # 1. Literature & math models
        lit_dirs = [
            self.project_root / "notes",
            self.project_root / "papers",
            self.project_root / "docs",
        ]
        seen_stems_in_auto: set[str] = set()
        for folder in lit_dirs:
            if not folder.exists():
                continue
            for file_path in sorted(folder.rglob("*")):
                if not file_path.is_file():
                    continue
                # Avoid indexing both .pdf and .fulltext.md in auto_fetched
                if "auto_fetched" in file_path.parts and file_path.suffix.lower() == ".pdf":
                    if file_path.with_suffix(".fulltext.md").exists():
                        continue
                if file_path.suffix.lower() in {
                    ".md",
                    ".tex",
                    ".bib",
                    ".pdf",
                }:
                    collected.extend(
                        self._chunk_file(file_path, category="literature")
                    )

        # 2. Codebase API & contracts
        src_dir = self.project_root / "src"
        if src_dir.exists():
            for py_path in sorted(src_dir.rglob("*.py")):
                if "ai_workflow" in py_path.parts:
                    continue
                collected.extend(self._chunk_file(py_path, category="codebase"))

        # 3. Experiment memory & rules (exclude rag_index directory!)
        memory_files = [
            self.project_root / "AGENTS.md",
            self.project_root / "README.zh-CN.md",
        ]
        exp_memory_dir = self.project_root / "experiments" / "ai_memory"
        if exp_memory_dir.exists():
            for mem_file in sorted(exp_memory_dir.glob("*.md")):
                memory_files.append(mem_file)

        for mem_path in memory_files:
            if mem_path.exists() and mem_path.is_file():
                chunks = self._chunk_file(mem_path, category="experiment_memory")
                if exp_memory_dir in mem_path.parents:
                    from dataclasses import replace
                    chunks = [replace(chunk, review_status="unreviewed") for chunk in chunks]
                collected.extend(chunks)

        # 4. Any user-provided extra PDFs or Markdown documents
        for extra in extra_paths:
            if extra.exists() and extra.is_file():
                collected.extend(self._chunk_file(extra, category="literature"))

        self.chunks = list({chunk.chunk_id: chunk for chunk in collected}.values())
        self._rebuild_faiss_index()
        return len(self.chunks)

    def add_memory_note(
        self, title: str, content: str, source_tag: str = "ai_memory", *,
        track_id: str = "shared", review_status: str = "unreviewed",
    ) -> None:
        """Append an episodic experiment record directly into the live RAG store."""

        chunk = KnowledgeChunk(
            chunk_id=f"mem_{len(self.chunks):04d}",
            category="experiment_memory",
            source_path=source_tag,
            title=title,
            content=content,
            track_id=track_id,
            review_status=review_status,
        )
        self.chunks.append(chunk)
        self._rebuild_faiss_index()

    def search(
        self,
        query: str,
        top_k: int = 5,
        category: ChunkCategory | None = None,
        track_id: str | None = None,
    ) -> list[KnowledgeChunk]:
        """Retrieve top_k relevant chunks via FAISS inner-product similarity."""

        if not self.chunks or self.index is None:
            return []

        q_vec = self.embedder.embed_texts([query])
        search_k = len(self.chunks)
        scores, indices = self.index.search(q_vec, search_k)

        results: list[KnowledgeChunk] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.chunks):
                continue
            chunk = self.chunks[idx]
            if chunk.review_status not in {"reference", "approved"}:
                continue
            if track_id is not None and chunk.track_id not in {"shared", track_id}:
                continue
            if category is not None and chunk.category != category:
                continue
            results.append(
                KnowledgeChunk(
                    chunk_id=chunk.chunk_id,
                    category=chunk.category,
                    source_path=chunk.source_path,
                    title=chunk.title,
                    content=chunk.content,
                    score=float(score),
                    track_id=chunk.track_id,
                    review_status=chunk.review_status,
                )
            )
            if len(results) >= top_k:
                break
        return results

    def save(self, directory: Path) -> None:
        """Persist FAISS index and chunk metadata to disk (Unicode-path safe on Windows)."""

        directory.mkdir(parents=True, exist_ok=True)
        if self.index is not None:
            serialized = faiss.serialize_index(self.index)
            (directory / "index.faiss").write_bytes(serialized.tobytes())
        metadata_path = directory / "chunks.json"
        payload = [asdict(c) for c in self.chunks]
        metadata_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, directory: Path, config: LLMConfig | None = None, *, rebuild_missing_index: bool = True) -> ResearchRAGStore:
        """Load a saved FAISS index and chunk metadata from disk."""

        store = cls(config=config)
        metadata_path = directory / "chunks.json"
        if not metadata_path.exists():
            raise FileNotFoundError(f"RAG metadata not found at {metadata_path}")
        raw_items = json.loads(metadata_path.read_text(encoding="utf-8"))
        for item in raw_items:
            if (item.get("category") == "experiment_memory" and "review_status" not in item
                    and item.get("source_path") not in {"AGENTS.md", "README.zh-CN.md"}):
                item["review_status"] = "unreviewed"
        store.chunks = [KnowledgeChunk(**item) for item in raw_items]
        index_path = directory / "index.faiss"
        if index_path.exists():
            raw_bytes = np.frombuffer(index_path.read_bytes(), dtype=np.uint8)
            store.index = faiss.deserialize_index(raw_bytes)
        else:
            if store.chunks and not rebuild_missing_index:
                raise ValueError("Associated RAG vectors are missing; refusing implicit rebuild")
            store._rebuild_faiss_index()
        return store

    def _rebuild_faiss_index(self) -> None:
        if not self.chunks:
            self.index = None
            return
        texts = [f"{c.title}\n{c.content}" for c in self.chunks]
        vectors = self.embedder.embed_texts(texts)
        dim = vectors.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(vectors)
        self.index = index

    def _chunk_file(
        self,
        file_path: Path,
        category: ChunkCategory,
    ) -> list[KnowledgeChunk]:
        text = self._read_file_text(file_path)
        if not text.strip():
            return []

        # Provenance follows the document, not the caller's chosen ingestion route.
        marker = re.match(r"\s*<!-- fjsp-generated-report track=(foundation|innovation|graduation) -->", text)
        generated = ("ai_memory" in file_path.parts or marker is not None
                     or text.lstrip().startswith("# 文献深度解析与代码对齐报告："))
        track_id, review_status = "shared", "reference"
        if generated:
            category, review_status = "experiment_memory", "unreviewed"
            if marker:
                track_id = marker.group(1)
            elif "ai_memory" in file_path.parts:
                suffix = file_path.parts[file_path.parts.index("ai_memory") + 1:]
                if suffix and suffix[0] in {"foundation", "innovation", "graduation"}:
                    track_id = suffix[0]

        try:
            rel_path = file_path.relative_to(self.project_root).as_posix()
        except ValueError:
            rel_path = file_path.name

        title = file_path.stem
        paragraphs = self._split_text(text)
        chunks: list[KnowledgeChunk] = []
        for idx, part in enumerate(paragraphs):
            chunks.append(
                KnowledgeChunk(
                    chunk_id=f"{category}_{rel_path}_{idx}",
                    category=category,
                    source_path=rel_path,
                    title=title,
                    content=part,
                    track_id=track_id,
                    review_status=review_status,
                )
            )
        return chunks

    def _read_file_text(self, file_path: Path) -> str:
        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader

                reader = PdfReader(str(file_path))
                pages = [page.extract_text() or "" for page in reader.pages]
                return "\n\n".join(pages)
            except Exception:
                return ""
        try:
            return file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""

    def _split_text(self, text: str) -> list[str]:
        cleaned = text.strip()
        if len(cleaned) <= self.chunk_size:
            return [cleaned]

        chunks: list[str] = []
        start = 0
        step = max(1, self.chunk_size - self.chunk_overlap)
        while start < len(cleaned):
            piece = cleaned[start : start + self.chunk_size].strip()
            if piece:
                chunks.append(piece)
            start += step
        return chunks
