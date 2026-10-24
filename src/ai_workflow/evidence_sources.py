"""Code-derived text identity and optional physical PDF page coordinates."""

from __future__ import annotations

import hashlib
from pathlib import Path


def _file_hash(path: Path | None):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path is not None and path.is_file() else None


def make_source_map(text: str, *, source_path: Path | None = None, pdf_path: Path | None = None) -> dict:
    source_path = Path(source_path) if source_path else None
    pdf_path = Path(pdf_path) if pdf_path else None
    if pdf_path is None and source_path is not None and source_path.suffix.lower() == ".pdf":
        pdf_path = source_path
    mapping = {"source_path": str(source_path or ""), "source_kind": "text",
               "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
               "text_length": len(text), "raw_sha256": _file_hash(source_path),
               "pdf_source_path": str(pdf_path or ""), "pdf_raw_sha256": _file_hash(pdf_path),
               "pages": [], "warnings": []}
    if pdf_path is None or not pdf_path.is_file():
        return mapping
    try:
        from pypdf import PdfReader
        pages = [page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages]
        body = "\n\n".join(pages)
        left_trim = 0
        offset = text.find(body) if body.strip() else -1
        # The existing downloader strips only the outer whitespace of the
        # joined body. Retain physical page numbers while clipping that prefix.
        if offset < 0 and body.strip():
            left_trim = len(body) - len(body.lstrip())
            body = body.strip()
            offset = text.find(body)
        if offset < 0 or text.find(body, offset + 1) != -1:
            mapping["warnings"].append("PDF body is empty, absent, or repeated in resolved text; no physical pages assigned")
            return mapping
        position = 0
        for number, page in enumerate(pages, 1):
            start = offset + min(len(body), max(0, position - left_trim))
            end = offset + min(len(body), max(0, position + len(page) - left_trim))
            mapping["pages"].append({"page": number, "start": start, "end": end})
            position += len(page) + 2
        mapping["source_kind"] = "pdf_backed_text"
    except Exception as exc:
        mapping["warnings"].append(f"Physical PDF locations unavailable: {type(exc).__name__}")
    return mapping


def assert_source_files_unchanged(mapping: dict):
    for path_key, hash_key in (("source_path", "raw_sha256"), ("pdf_source_path", "pdf_raw_sha256")):
        expected, path = mapping.get(hash_key), mapping.get(path_key)
        if expected and (not path or _file_hash(Path(path)) != expected):
            raise ValueError("Evidence source file changed or is missing; create a new session")
