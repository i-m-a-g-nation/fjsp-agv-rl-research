from __future__ import annotations

from dataclasses import dataclass
import html
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Literal
import xml.etree.ElementTree as ET

import requests
from pypdf import PdfReader

from src.ai_workflow.campus_auth import download_pdf_with_campus_auth

ContentDepth = Literal["full_text", "abstract_only", "metadata_only"]

_ARXIV_ID_RE = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf)/|arxiv\s*:\s*)(\d{4}\.\d{4,5}(?:v\d+)?)",
    re.IGNORECASE,
)
_DOI_RE = re.compile(
    r"(?:doi\.org/|doi\s*:\s*)(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)",
    re.IGNORECASE,
)
_TITLE_LINE_RE = re.compile(
    r"^\s*[-*]?\s*(?:题目|标题|Title)\s*[：:]\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class PaperResolutionResult:
    """Result of checking a paper file and resolving its full text/abstract online."""

    content_depth: ContentDepth
    paper_title: str
    resolved_text: str
    arxiv_id: str | None
    doi: str | None
    downloaded_pdf_path: Path | None
    cached_fulltext_path: Path | None
    resolution_log: list[str]


def detect_content_depth(text: str) -> ContentDepth:
    """Determine if a document has full paper body, abstract only, or metadata stub only.

    A metadata stub like `notes/papers/2023_dfjsp_itr_gnn_drl.md` has < 1200 chars
    and only contains bullet items like `- 题目：`, `- DOI/链接：`, `- 是否有代码：`.
    """

    cleaned = text.strip()
    # Length alone cannot establish that an abstract or note is a full paper.
    # This remains a structural hint, not verification of individual claims.
    has_math_or_method = bool(
        re.search(r"(\$\$|\\begin\{equation\}|State Space|Reward Function|目标函数.*min|s\.t\.)", cleaned, re.IGNORECASE)
    )
    if len(cleaned) >= 1200 and has_math_or_method:
        return "full_text"

    if len(cleaned) >= 600:
        return "abstract_only"

    return "metadata_only"


def extract_identifiers_from_stub(text: str, fallback_title: str = "") -> tuple[str, str | None, str | None]:
    """Extract paper title, arXiv ID, and DOI from a markdown note or text stub."""

    title_match = _TITLE_LINE_RE.search(text)
    title = title_match.group(1).strip() if title_match else fallback_title

    arxiv_match = _ARXIV_ID_RE.search(text)
    arxiv_id = arxiv_match.group(1).strip() if arxiv_match else None

    doi_match = _DOI_RE.search(text)
    doi = doi_match.group(1).strip().rstrip(".,;)") if doi_match else None

    return title, arxiv_id, doi


def _cache_request_identity(raw_text: str, title: str, arxiv_id: str | None, doi: str | None) -> str:
    identity = {"arxiv_id": arxiv_id, "doi": doi} if (arxiv_id or doi) else {"title": title, "input": raw_text}
    return hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _write_resolved_cache(path: Path, text: str, depth: ContentDepth, arxiv_id: str | None, doi: str | None,
                          *, request_identity: str | None = None, pdf_path: Path | None = None) -> None:
    """Preserve acquisition depth, without treating it as verified paper claims."""
    path.write_text(text, encoding="utf-8")
    provenance = {"version": 2 if request_identity else 1, "content_depth": depth, "arxiv_id": arxiv_id, "doi": doi,
                  "request_identity": request_identity,
                  "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                  "pdf_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest() if pdf_path and pdf_path.is_file() else None}
    path.with_suffix(".source.json").write_text(json.dumps(provenance), encoding="utf-8")


def _cached_depth(path: Path, text: str, arxiv_id: str | None, doi: str | None, request_identity: str) -> ContentDepth | None:
    provenance_path = path.with_suffix(".source.json")
    if not provenance_path.exists():
        return None
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        bound = ((provenance.get("version") == 2 and provenance.get("request_identity") == request_identity)
                 or (provenance.get("version") == 1 and bool(arxiv_id or doi)))
        if (bound and provenance.get("arxiv_id") == arxiv_id
                and provenance.get("doi") == doi
                and provenance.get("sha256") == hashlib.sha256(text.encode("utf-8")).hexdigest()
                and provenance.get("content_depth") in {"full_text", "abstract_only"}):
            return provenance["content_depth"]
    except (ValueError, OSError, AttributeError):
        pass
    return None


def _associated_cached_pdf(cache_path: Path, pdf_path: Path) -> Path | None:
    """A nearby filename alone cannot associate a PDF with this acquisition."""
    try:
        provenance = json.loads(cache_path.with_suffix(".source.json").read_text(encoding="utf-8"))
        expected = provenance.get("pdf_sha256")
        if provenance.get("content_depth") == "full_text" and expected and pdf_path.is_file():
            if hashlib.sha256(pdf_path.read_bytes()).hexdigest() == expected:
                return pdf_path
    except (ValueError, OSError, AttributeError):
        pass
    return None


def resolve_paper_content(
    paper_path: Path | None,
    raw_text: str,
    fallback_title: str,
    download_dir: Path,
    allow_network: bool = True,
    timeout_sec: int = 20,
) -> PaperResolutionResult:
    """Inspect a paper input; if it is a metadata stub, automatically fetch full text or abstract.

    Resolution order when `detect_content_depth(raw_text) == "metadata_only"`:
    1. Check if `download_dir` already has a cached `.pdf` or `.fulltext.md` for this paper.
    2. If an `arXiv ID` is present, download the official PDF from `https://arxiv.org/pdf/{id}.pdf`,
       extract all pages via `pypdf`, and fetch the official arXiv API summary.
    3. If a `DOI` or `title` is present, query OpenAlex (`https://api.openalex.org/works`) and
       Semantic Scholar / Crossref for Open-Access PDF links and the full abstract.
    4. Return the resolved text along with an honest `content_depth` tag (`full_text`,
       `abstract_only`, or `metadata_only`) so downstream nodes never hallucinate formulas.
    """

    logs: list[str] = []
    title, arxiv_id, doi = extract_identifiers_from_stub(raw_text, fallback_title=fallback_title)
    request_identity = _cache_request_identity(raw_text, title, arxiv_id, doi)
    stem = paper_path.stem if paper_path is not None else re.sub(r"[^a-zA-Z0-9_-]", "_", fallback_title)[:40]

    initial_depth = detect_content_depth(raw_text)
    if initial_depth == "full_text":
        logs.append(f"Input file `{stem}` already contains full text ({len(raw_text)} chars).")
        return PaperResolutionResult(
            content_depth="full_text",
            paper_title=title,
            resolved_text=raw_text,
            arxiv_id=arxiv_id,
            doi=doi,
            downloaded_pdf_path=paper_path if (paper_path and paper_path.suffix.lower() == ".pdf") else None,
            cached_fulltext_path=None,
            resolution_log=logs,
        )

    logs.append(
        f"Detected `{initial_depth}` stub ({len(raw_text)} chars) for '{title}' "
        f"(arXiv={arxiv_id}, DOI={doi})."
    )
    download_dir.mkdir(parents=True, exist_ok=True)
    cached_pdf = download_dir / f"{stem}.pdf"
    cached_md = download_dir / f"{stem}.fulltext.md"

    # 1. Check local cache first
    if cached_md.exists():
        cached_text = cached_md.read_text(encoding="utf-8", errors="ignore")
        depth = _cached_depth(cached_md, cached_text, arxiv_id, doi, request_identity)
        if depth in {"full_text", "abstract_only"}:
            logs.append(f"Loaded cached resolved document from `{cached_md.name}` ({len(cached_text)} chars, {depth}).")
            return PaperResolutionResult(
                content_depth=depth,
                paper_title=title,
                resolved_text=cached_text,
                arxiv_id=arxiv_id,
                doi=doi,
                downloaded_pdf_path=_associated_cached_pdf(cached_md, cached_pdf),
                cached_fulltext_path=cached_md,
                resolution_log=logs,
            )
        logs.append("Ignored unbound, mismatched, or modified cache; select its original document explicitly or reacquire it.")

    if not allow_network:
        logs.append("Network fetching disabled (`allow_network=False`); keeping stub as-is.")
        return PaperResolutionResult(
            content_depth=initial_depth,
            paper_title=title,
            resolved_text=raw_text,
            arxiv_id=arxiv_id,
            doi=doi,
            downloaded_pdf_path=None,
            cached_fulltext_path=None,
            resolution_log=logs,
        )

    # 2. If arXiv ID is available, fetch arXiv metadata + full PDF
    if arxiv_id:
        arxiv_abs = _fetch_arxiv_abstract(arxiv_id, timeout_sec=timeout_sec, logs=logs)
        pdf_text = _download_and_parse_pdf(
            url=f"https://arxiv.org/pdf/{arxiv_id}.pdf",
            target_pdf_path=cached_pdf,
            timeout_sec=timeout_sec,
            logs=logs,
        )
        if pdf_text and len(pdf_text.strip()) > 1500:
            combined = (
                f"# {title}\n\n"
                f"- **arXiv ID**: {arxiv_id}\n\n"
                f"## Abstract\n{arxiv_abs}\n\n"
                f"## Extracted PDF Full Text\n{pdf_text}\n"
            )
            _write_resolved_cache(cached_md, combined, "full_text", arxiv_id, doi, request_identity=request_identity, pdf_path=cached_pdf)
            return PaperResolutionResult(
                content_depth="full_text",
                paper_title=title,
                resolved_text=combined,
                arxiv_id=arxiv_id,
                doi=doi,
                downloaded_pdf_path=cached_pdf,
                cached_fulltext_path=cached_md,
                resolution_log=logs,
            )
        if arxiv_abs:
            combined = f"{raw_text}\n\n## Official arXiv Abstract\n{arxiv_abs}\n"
            _write_resolved_cache(cached_md, combined, "abstract_only", arxiv_id, doi, request_identity=request_identity)
            return PaperResolutionResult(
                content_depth="abstract_only",
                paper_title=title,
                resolved_text=combined,
                arxiv_id=arxiv_id,
                doi=doi,
                downloaded_pdf_path=None,
                cached_fulltext_path=cached_md,
                resolution_log=logs,
            )

    # 3. Try Campus Auth / Institutional Credentials (Elsevier API / Saved Browser State / Cookies)
    if doi:
        ok_campus, campus_pdf_text, campus_logs = download_pdf_with_campus_auth(
            doi=doi,
            title=title,
            target_pdf_path=cached_pdf,
            elsevier_api_key=os.getenv("ELSEVIER_API_KEY", ""),
            timeout_sec=timeout_sec,
        )
        logs.extend(campus_logs)
        if ok_campus and len(campus_pdf_text.strip()) > 1500:
            combined = (
                f"# {title}\n\n"
                f"- **DOI**: {doi}\n"
                f"- **Source**: Campus Institutional Access\n\n"
                f"## Extracted PDF Full Text\n{campus_pdf_text}\n"
            )
            _write_resolved_cache(cached_md, combined, "full_text", arxiv_id, doi, request_identity=request_identity, pdf_path=cached_pdf)
            return PaperResolutionResult(
                content_depth="full_text",
                paper_title=title,
                resolved_text=combined,
                arxiv_id=arxiv_id,
                doi=doi,
                downloaded_pdf_path=cached_pdf,
                cached_fulltext_path=cached_md,
                resolution_log=logs,
            )

    # 4. If DOI or Title is available, query OpenAlex & Semantic Scholar for OA PDF + Abstract
    oa_pdf_url, abstract_text = _fetch_doi_or_title_metadata(
        doi=doi,
        title=title,
        timeout_sec=timeout_sec,
        logs=logs,
    )
    if oa_pdf_url:
        pdf_text = _download_and_parse_pdf(
            url=oa_pdf_url,
            target_pdf_path=cached_pdf,
            timeout_sec=timeout_sec,
            logs=logs,
        )
        if pdf_text and len(pdf_text.strip()) > 1500:
            combined = (
                f"# {title}\n\n"
                f"- **DOI**: {doi or 'N/A'}\n"
                f"- **Source PDF**: {oa_pdf_url}\n\n"
                f"## Abstract\n{abstract_text}\n\n"
                f"## Extracted PDF Full Text\n{pdf_text}\n"
            )
            _write_resolved_cache(cached_md, combined, "full_text", arxiv_id, doi, request_identity=request_identity, pdf_path=cached_pdf)
            return PaperResolutionResult(
                content_depth="full_text",
                paper_title=title,
                resolved_text=combined,
                arxiv_id=arxiv_id,
                doi=doi,
                downloaded_pdf_path=cached_pdf,
                cached_fulltext_path=cached_md,
                resolution_log=logs,
            )

    if abstract_text:
        combined = (
            f"{raw_text}\n\n"
            f"## Retrieved Official Abstract (via DOI/OpenAlex/SemanticScholar)\n"
            f"{abstract_text}\n"
        )
        _write_resolved_cache(cached_md, combined, "abstract_only", arxiv_id, doi, request_identity=request_identity)
        logs.append(
            "Closed-access publisher paper (no public PDF); saved official abstract "
            "and marked as `abstract_only` to prevent formula hallucination."
        )
        return PaperResolutionResult(
            content_depth="abstract_only",
            paper_title=title,
            resolved_text=combined,
            arxiv_id=arxiv_id,
            doi=doi,
            downloaded_pdf_path=None,
            cached_fulltext_path=cached_md,
            resolution_log=logs,
        )

    logs.append(
        "Could not retrieve full PDF or abstract online; marked as `metadata_only`."
    )
    return PaperResolutionResult(
        content_depth="metadata_only",
        paper_title=title,
        resolved_text=raw_text,
        arxiv_id=arxiv_id,
        doi=doi,
        downloaded_pdf_path=None,
        cached_fulltext_path=None,
        resolution_log=logs,
    )


def _fetch_arxiv_abstract(arxiv_id: str, timeout_sec: int, logs: list[str]) -> str:
    url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
    try:
        resp = requests.get(url, timeout=timeout_sec)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        summary_el = root.find(".//atom:entry/atom:summary", ns)
        if summary_el is not None and summary_el.text:
            logs.append(f"Fetched arXiv abstract for `{arxiv_id}`.")
            return summary_el.text.strip()
    except Exception as exc:
        logs.append(f"arXiv API query failed for `{arxiv_id}`: {exc}")
    return ""


def _download_and_parse_pdf(
    url: str,
    target_pdf_path: Path,
    timeout_sec: int,
    logs: list[str],
) -> str:
    try:
        headers = {"User-Agent": "fjsp-agv-rl-research/0.1 (Academic Research Bot)"}
        resp = requests.get(url, headers=headers, timeout=timeout_sec)
        resp.raise_for_status()
        if not resp.content.startswith(b"%PDF"):
            logs.append(f"URL `{url}` did not return a valid PDF header.")
            return ""
        target_pdf_path.write_bytes(resp.content)
        reader = PdfReader(str(target_pdf_path))
        pages = [page.extract_text() or "" for page in reader.pages]
        full_text = "\n\n".join(pages).strip()
        logs.append(
            f"Downloaded PDF to `{target_pdf_path.name}` ({len(reader.pages)} pages, {len(full_text)} chars)."
        )
        return full_text
    except Exception as exc:
        logs.append(f"PDF download/parse failed from `{url}`: {exc}")
        return ""


def _fetch_doi_or_title_metadata(
    doi: str | None,
    title: str,
    timeout_sec: int,
    logs: list[str],
) -> tuple[str | None, str]:
    headers = {"User-Agent": "fjsp-agv-rl-research/0.1 (mailto:research@example.edu)"}
    oa_pdf_url: str | None = None
    abstract_text = ""

    # 1. Try OpenAlex by DOI
    if doi:
        try:
            oa_url = f"https://api.openalex.org/works/https://doi.org/{doi}"
            resp = requests.get(oa_url, headers=headers, timeout=timeout_sec)
            if resp.status_code == 200:
                data = resp.json()
                oa_info = data.get("open_access") or {}
                if oa_info.get("oa_url"):
                    oa_pdf_url = str(oa_info["oa_url"])
                inv_idx = data.get("abstract_inverted_index")
                if isinstance(inv_idx, dict) and inv_idx:
                    abstract_text = _reconstruct_openalex_abstract(inv_idx)
                    logs.append(f"Fetched abstract from OpenAlex for DOI `{doi}` ({len(abstract_text)} chars).")
        except Exception as exc:
            logs.append(f"OpenAlex lookup failed for DOI `{doi}`: {exc}")

    # 2. Try Crossref if abstract still missing
    if doi and not abstract_text:
        try:
            cr_url = f"https://api.crossref.org/works/{doi}"
            resp = requests.get(cr_url, headers=headers, timeout=timeout_sec)
            if resp.status_code == 200:
                msg = resp.json().get("message", {})
                raw_abs = msg.get("abstract", "")
                if raw_abs:
                    clean_abs = re.sub(r"<[^>]+>", " ", html.unescape(raw_abs)).strip()
                    abstract_text = re.sub(r"\s+", " ", clean_abs)
                    logs.append(f"Fetched abstract from Crossref for DOI `{doi}`.")
        except Exception as exc:
            logs.append(f"Crossref lookup failed for DOI `{doi}`: {exc}")

    # 3. Try Semantic Scholar by DOI or Title
    if not abstract_text or not oa_pdf_url:
        try:
            if doi:
                s2_url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=title,abstract,openAccessPdf"
            else:
                s2_url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={requests.utils.quote(title)}&limit=1&fields=title,abstract,openAccessPdf"
            resp = requests.get(s2_url, headers=headers, timeout=timeout_sec)
            if resp.status_code == 200:
                payload = resp.json()
                paper_data = payload.get("data", [{}])[0] if "data" in payload else payload
                if not abstract_text and paper_data.get("abstract"):
                    abstract_text = str(paper_data["abstract"]).strip()
                    logs.append("Fetched abstract from Semantic Scholar.")
                oa_pdf = paper_data.get("openAccessPdf") or {}
                if not oa_pdf_url and oa_pdf.get("url"):
                    oa_pdf_url = str(oa_pdf["url"])
                    logs.append(f"Found OpenAccess PDF URL via Semantic Scholar: {oa_pdf_url}")
        except Exception as exc:
            logs.append(f"Semantic Scholar lookup skipped/failed: {exc}")

    return oa_pdf_url, abstract_text


def _reconstruct_openalex_abstract(inverted_index: dict[str, list[int]]) -> str:
    word_positions: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort(key=lambda item: item[0])
    return " ".join(word for _pos, word in word_positions)
