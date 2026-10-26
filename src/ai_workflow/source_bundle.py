"""Acquire bounded, immutable evidence without executing third-party code.

The manifest is a local integrity record, not a signature or proof of authorship.
Textual DOI/repository cross-links establish only the stated source linkage.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
import time
from typing import Callable
from urllib.parse import quote, urlsplit

import requests


_CODE_LIMIT = 256 * 1024
_CODE_TOTAL = 2 * 1024 * 1024
_PDF_LIMIT = 10 * 1024 * 1024
_API_LIMIT = 3 * 1024 * 1024
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
_TEXT_SUFFIXES = {".py", ".md", ".txt", ".rst", ".json", ".toml", ".yaml", ".yml", ".cfg", ".ini"}
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def _json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _safe_path(value: str, *, source: bool = False) -> str:
    if not isinstance(value, str) or not value or len(value) > 200:
        raise ValueError("Invalid relative file path")
    parts = value.split("/")
    if any(not part or part in {".", ".."} or part.endswith((" ", "."))
           or not re.fullmatch(r"[A-Za-z0-9_. -]+", part)
           or part.split(".")[0].upper() in _RESERVED for part in parts):
        raise ValueError("Unsafe Windows-relative file path")
    if source and (any(part.startswith(".") for part in parts)
                   or (value != "LICENSE" and PurePosixPath(value).suffix.lower() not in _TEXT_SUFFIXES)):
        raise ValueError("Only selected plain-text source files are supported")
    return value


def _validate_request(spec: dict) -> None:
    if not isinstance(spec, dict) or spec.get("version") != 1:
        raise ValueError("Unsupported source request version")
    paper, repo = spec["paper"], spec["repository"]
    if not _REPO.fullmatch(repo["name"]) or not _HEX40.fullmatch(repo["commit"]):
        raise ValueError("Repository and full immutable commit are required")
    if repo.get("license") != "MIT" or paper.get("license") != "CC-BY-4.0":
        raise ValueError("This source route requires MIT code and CC-BY-4.0 paper")
    if not _HEX64.fullmatch(paper["sha256"]) or not re.fullmatch(r"10\.[0-9]{4,9}/[A-Za-z0-9._;()/-]+", paper["doi"]):
        raise ValueError("Pinned PDF SHA256 and DOI are required")
    url = urlsplit(paper["pdf_url"])
    if (url.scheme != "https" or url.netloc != "link.springer.com" or url.username or url.password
            or url.query or url.fragment or not url.path.startswith("/content/pdf/")
            or url.path != f"/content/pdf/{paper['doi']}.pdf"):
        raise ValueError("Only a credential-free official Springer PDF URL is supported")
    files = repo["files"]
    if not isinstance(files, list) or not 2 <= len(files) <= 12:
        raise ValueError("Select between 2 and 12 source files")
    paths = []
    for item in files:
        paths.append(_safe_path(item["path"], source=True))
        if not _HEX40.fullmatch(item["blob_sha1"]):
            raise ValueError("Every code file requires its Git blob SHA1")
    if len({path.casefold() for path in paths}) != len(paths):
        raise ValueError("Case-colliding selected source paths")
    spellings = {}
    for path in paths:
        parts = path.split("/")
        for index in range(1, len(parts) + 1):
            prefix = "/".join(parts[:index])
            key = prefix.casefold()
            if key in spellings and spellings[key] != prefix:
                raise ValueError("Case-colliding source directories")
            if index < len(parts) and key in {item.casefold() for item in paths}:
                raise ValueError("Source file conflicts with a parent directory")
            spellings[key] = prefix
    if "LICENSE" not in paths or "README.md" not in paths:
        raise ValueError("Selected LICENSE and README.md are required")


def validate_source_request(request: dict) -> None:
    """Validate before persistence, with no network, file access or input echo."""
    try:
        _validate_request(request)
    except (KeyError, TypeError, AttributeError, ValueError):
        raise ValueError("Invalid or unsafe pinned source request") from None


def _is_link(path: Path) -> bool:
    try:
        return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0)
                                         & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except FileNotFoundError:
        return False


def _read(folder: Path, relative: str, limit: int) -> bytes:
    _safe_path(relative)
    path = folder / relative
    # Resolving alone would permit a symlink into another location in the bundle.
    if any(_is_link(parent) for parent in (path, *path.parents)
           if parent != folder.parent and folder.parent in parent.parents):
        raise ValueError("Symlinks and junctions are not source artifacts")
    if not path.resolve().is_relative_to(folder.resolve()) or not path.is_file() or path.stat().st_size > limit:
        raise ValueError(f"Missing, unsafe or oversized source artifact: {relative}")
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Source artifact exceeds size limit")
    return data


def _check_tree(spec: dict, commit: dict, tree: dict) -> None:
    repo = spec["repository"]
    tree_sha = commit.get("tree", {}).get("sha", "")
    if commit.get("sha") != repo["commit"] or not _HEX40.fullmatch(tree_sha):
        raise ValueError("Commit identity mismatch")
    if tree.get("sha") != tree_sha or tree.get("truncated") is not False or not isinstance(tree.get("tree"), list):
        raise ValueError("Truncated or mismatched immutable Git tree")
    nodes = {}
    for node in tree["tree"]:
        path = node["path"]
        if path in nodes:
            raise ValueError("Duplicate paths in Git tree")
        nodes[path] = node
    for item in repo["files"]:
        node = nodes.get(item["path"], {})
        if (node.get("mode") != "100644" or node.get("type") != "blob"
                or node.get("sha") != item["blob_sha1"]
                or type(node.get("size")) is not int or not 0 <= node["size"] <= _CODE_LIMIT):
            raise ValueError(f"Missing, non-regular or mismatched blob: {item['path']}")
        for parent in PurePosixPath(item["path"]).parents:
            if str(parent) != "." and str(parent) in nodes:
                if nodes[str(parent)].get("mode") != "040000" or nodes[str(parent)].get("type") != "tree":
                    raise ValueError("Source path traverses a non-tree entry")


def _extract_pdf(path: Path) -> tuple[list[str], dict]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 100:
        raise ValueError("Encrypted PDF or PDF outside 1..100 physical pages")
    pages = [page.extract_text() or "" for page in reader.pages]
    metadata = {str(key): str(value) for key, value in (reader.metadata or {}).items()}
    return pages, metadata


def _linkage(spec: dict, texts: dict[str, str], pages: list[str]) -> dict:
    normalize = lambda text: re.sub(r"\s+", "", text).casefold()
    doi = normalize(spec["paper"]["doi"])
    repo_url = f"https://github.com/{spec['repository']['name']}"
    pdf_text = normalize("\n\n".join(pages))
    if doi not in normalize(texts["README.md"]) or doi not in pdf_text or normalize(repo_url) not in pdf_text:
        raise ValueError("Missing README DOI or PDF DOI/author-repository textual linkage")
    if not texts["LICENSE"].lstrip("\ufeff \t\r\n").startswith("MIT License\n") and not texts["LICENSE"].lstrip("\ufeff \t\r\n").startswith("MIT License\r\n"):
        raise ValueError("Missing MIT LICENSE header")
    return {"status": "VERIFIED_TEXT_LINKS", "readme_doi": True, "pdf_doi": True,
            "pdf_repository_url": repo_url,
            "notice": "Text links do not authenticate authors or establish paper/code equivalence."}


def _functions(text: str) -> list[dict]:
    result = []

    def walk(node, prefix=""):
        for child in ast.iter_child_nodes(node):
            name = f"{prefix}{child.name}" if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) else None
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                result.append({"name": name, "start": child.lineno, "end": child.end_lineno})
            walk(child, f"{name}." if name else prefix)

    walk(ast.parse(text))
    return result


def _index_sources(texts: dict[str, str]) -> tuple[dict, dict]:
    index, errors = {}, {}
    for path, text in texts.items():
        if path.endswith(".py"):
            try:
                index[path] = _functions(text)
            except (SyntaxError, ValueError, RecursionError) as exc:
                errors[path] = type(exc).__name__
    return index, errors


def _proxies(url: str) -> dict:
    """Honor standard transport proxies without enabling ambient netrc auth."""
    proxies = {}
    for key, value in requests.utils.get_environ_proxies(url).items():
        if key not in {"http", "https", "all"}:
            continue
        proxy = urlsplit(value)
        if (proxy.scheme not in {"http", "https"} or not proxy.hostname or proxy.username or proxy.password
                or proxy.query or proxy.fragment or proxy.path not in {"", "/"}):
            raise ValueError("Unsafe environment proxy configuration")
        proxies[key] = value
    return proxies


def acquire_source_bundle(request: dict, output_dir: Path, *, pdf_cache: Path | None = None,
                          repository_cache: Path | None = None,
                          remaining_seconds: Callable | None = None) -> dict:
    """Fetch a fresh bundle, preserving a FAILED manifest on any acquisition error.

    Existing nonempty directories are conflicts and are never modified. An optional
    PDF cache must pass the same pin and content/linkage checks as a network PDF.
    An explicit repository cache contains commit.json, tree.json and code/<path>;
    it passes the same identity checks and never falls back to the network.
    """
    folder = Path(output_dir)
    if _is_link(folder) or (folder.exists() and (not folder.is_dir() or any(folder.iterdir()))):
        raise ValueError("Source output directory conflicts with existing artifacts")
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {"version": 1, "status": "INCOMPLETE", "files_sha256": {}, "errors": []}
    deadline = time.monotonic() + 300
    session = None

    def check():
        remaining = deadline - time.monotonic()
        if remaining_seconds is not None:
            external = float(remaining_seconds())
            if not math.isfinite(external):
                raise ValueError("Invalid external deadline")
            remaining = min(remaining, external)
        if remaining <= 0:
            raise ValueError("Source acquisition deadline exhausted")
        return remaining

    def save(relative, data):
        check()
        limit = _PDF_LIMIT if relative == "paper.pdf" else _CODE_LIMIT if relative.startswith("code/") else _API_LIMIT
        if len(data) > limit:
            raise ValueError("Source or extracted artifact exceeds size limit")
        target = folder / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        manifest["files_sha256"][relative] = _sha(data)
        (folder / "manifest.json").write_bytes(_json_bytes(manifest))

    def download(url, limit):
        nonlocal session
        timeout = min(20, check())
        if session is None:
            session = requests.Session()
            session.trust_env = False  # No ambient .netrc auth or credential lookup.
        response = session.get(url, stream=True, allow_redirects=False, timeout=timeout, proxies=_proxies(url))
        try:
            if response.status_code != 200:
                raise ValueError(f"Source HTTP status {response.status_code}")
            length = response.headers.get("Content-Length")
            if length is not None and (not str(length).isdigit() or int(length) > limit):
                raise ValueError("Declared source size exceeds limit")
            data = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                check()
                if len(data) + len(chunk) > limit:
                    raise ValueError("Streamed source size exceeds limit")
                data.extend(chunk)
            check()
            return bytes(data)
        finally:
            response.close()

    def repository_bytes(relative, url, limit):
        check()
        data = (_read(Path(repository_cache), relative, limit) if repository_cache is not None
                else download(url, limit))
        check()
        return data

    try:
        validate_source_request(request)
        manifest["request"] = json.loads(_json_bytes(request))
        save("request.json", _json_bytes(request))
        manifest["request_sha256"] = manifest["files_sha256"]["request.json"]
        repo, paper = request["repository"], request["paper"]
        api = f"https://api.github.com/repos/{repo['name']}/git"
        commit_data = repository_bytes("commit.json", f"{api}/commits/{repo['commit']}", _API_LIMIT)
        commit = json.loads(commit_data)
        if commit.get("sha") != repo["commit"] or not _HEX40.fullmatch(commit.get("tree", {}).get("sha", "")):
            raise ValueError("Commit identity mismatch")
        save("commit.json", commit_data)
        tree_data = repository_bytes("tree.json", f"{api}/trees/{commit['tree']['sha']}?recursive=1", _API_LIMIT)
        tree = json.loads(tree_data)
        _check_tree(request, commit, tree)
        save("tree.json", tree_data)
        files, texts, total = [], {}, 0
        for item in repo["files"]:
            url = f"https://raw.githubusercontent.com/{repo['name']}/{repo['commit']}/{quote(item['path'], safe='/')}"
            data = repository_bytes(f"code/{item['path']}", url, min(_CODE_LIMIT, _CODE_TOTAL - total))
            total += len(data)
            if _blob(data) != item["blob_sha1"]:
                raise ValueError(f"Git blob mismatch: {item['path']}")
            texts[item["path"]] = data.decode("utf-8")
            if "\0" in texts[item["path"]]:
                raise ValueError("NUL-containing source is not plain text")
            save(f"code/{item['path']}", data)
            files.append({**item, "sha256": _sha(data), "source_url": url,
                          "line_count": len(texts[item["path"]].splitlines())})
        if pdf_cache is not None:
            cache = Path(pdf_cache)
            if not cache.is_file() or _is_link(cache) or cache.stat().st_size > _PDF_LIMIT:
                raise ValueError("Invalid PDF cache")
            with cache.open("rb") as handle:
                pdf = handle.read(_PDF_LIMIT + 1)
            check()
        else:
            pdf = download(paper["pdf_url"], _PDF_LIMIT)
        if len(pdf) > _PDF_LIMIT or not pdf.startswith(b"%PDF-") or _sha(pdf) != paper["sha256"]:
            raise ValueError("PDF format or SHA256 mismatch")
        save("paper.pdf", pdf)
        pages, metadata = _extract_pdf(folder / "paper.pdf")
        check()
        if not 1 <= len(pages) <= 100 or any(not isinstance(page, str) for page in pages):
            raise ValueError("Invalid extracted PDF pages")
        save("paper.txt", "\n\n".join(pages).encode("utf-8"))
        save("pages.json", _json_bytes([{"page": i, "text": text} for i, text in enumerate(pages, 1)]))
        manifest.update(repository={"name": repo["name"], "commit": repo["commit"], "license": "MIT",
                                    "tree_sha1": tree["sha"], "files": files,
                                    "transport": "cached_github_records" if repository_cache is not None else "anonymous_https"},
                        paper={**paper, "metadata": metadata, "page_count": len(pages)},
                        linkage=_linkage(request, texts, pages), function_index={}, function_index_errors={})
        manifest["function_index"], manifest["function_index_errors"] = _index_sources(texts)
        check()
        manifest["status"] = "COMPLETED"
    except Exception as exc:
        manifest["status"] = "FAILED"
        # Do not include supplied URLs or request payloads in exception output.
        manifest["errors"].append(f"{type(exc).__name__}: {exc}" if not isinstance(exc, requests.RequestException)
                                  else f"{type(exc).__name__}: source request failed")
    finally:
        if session is not None:
            session.close()
        (folder / "manifest.json").write_bytes(_json_bytes(manifest))
    return manifest


def verify_source_bundle(folder: Path) -> dict:
    """Verify all immutable artifacts and their pinned identities before access."""
    folder = Path(folder)
    try:
        manifest = json.loads(_read(folder, "manifest.json", _API_LIMIT))
        if not isinstance(manifest, dict) or manifest.get("status") != "COMPLETED":
            raise ValueError("Source bundle is incomplete")
        request_data = _read(folder, "request.json", _API_LIMIT)
        spec = json.loads(request_data)
        validate_source_request(spec)
        expected = {"request.json", "commit.json", "tree.json", "paper.pdf", "paper.txt", "pages.json"}
        expected.update(f"code/{item['path']}" for item in spec["repository"]["files"])
        if set(manifest["files_sha256"]) != expected or manifest.get("request") != spec or manifest.get("request_sha256") != _sha(request_data):
            raise ValueError("Source manifest does not cover the complete original request")
        artifacts = {}
        for relative in expected:
            limit = _PDF_LIMIT if relative == "paper.pdf" else _CODE_LIMIT if relative.startswith("code/") else _API_LIMIT
            data = _read(folder, relative, limit)
            if _sha(data) != manifest["files_sha256"][relative]:
                raise ValueError(f"Source artifact changed: {relative}")
            artifacts[relative] = data
        _check_tree(spec, json.loads(artifacts["commit.json"]), json.loads(artifacts["tree.json"]))
        pdf = artifacts["paper.pdf"]
        if not pdf.startswith(b"%PDF-") or _sha(pdf) != spec["paper"]["sha256"]:
            raise ValueError("Pinned PDF identity changed")
        texts, total = {}, 0
        for item in spec["repository"]["files"]:
            data = artifacts[f"code/{item['path']}"]
            total += len(data)
            if _blob(data) != item["blob_sha1"] or b"\0" in data:
                raise ValueError("Pinned code blob identity changed")
            texts[item["path"]] = data.decode("utf-8")
        if total > _CODE_TOTAL:
            raise ValueError("Code aggregate exceeds limit")
        indexed = json.loads(artifacts["pages.json"])
        pages, metadata = _extract_pdf(folder / "paper.pdf")
        if (not 1 <= len(pages) <= 100 or indexed != [{"page": i, "text": text} for i, text in enumerate(pages, 1)]
                or artifacts["paper.txt"] != "\n\n".join(pages).encode("utf-8")):
            raise ValueError("PDF text/page index is inconsistent with pinned PDF")
        if manifest.get("linkage") != _linkage(spec, texts, pages):
            raise ValueError("Source linkage manifest changed")
        repo = manifest["repository"]
        if (repo["name"] != spec["repository"]["name"] or repo["commit"] != spec["repository"]["commit"]
                or repo.get("transport") not in {"anonymous_https", "cached_github_records"}
                or repo["tree_sha1"] != json.loads(artifacts["tree.json"])["sha"]
                or manifest["paper"] != {**spec["paper"], "metadata": metadata, "page_count": len(pages)}):
            raise ValueError("Source metadata changed")
        if len(repo["files"]) != len(spec["repository"]["files"]):
            raise ValueError("Incomplete code provenance")
        for selected, record in zip(spec["repository"]["files"], repo["files"]):
            url = f"https://raw.githubusercontent.com/{repo['name']}/{repo['commit']}/{quote(selected['path'], safe='/')}"
            expected_record = {**selected, "sha256": _sha(artifacts[f"code/{selected['path']}"]),
                               "source_url": url, "line_count": len(texts[selected["path"]].splitlines())}
            if record != expected_record:
                raise ValueError("Code provenance changed")
        index, index_errors = _index_sources(texts)
        if manifest.get("function_index") != index or manifest.get("function_index_errors") != index_errors:
            raise ValueError("Static function index changed")
        return manifest
    except (OSError, KeyError, TypeError, AttributeError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed or missing source bundle artifact") from exc


def make_paper_context(folder: Path, pages: list[int]) -> tuple[str, dict]:
    """Return complete selected physical pages with explicit excerpt coordinates."""
    folder = Path(folder)
    manifest = verify_source_bundle(folder)
    if (not isinstance(pages, list) or not pages or any(type(page) is not int for page in pages)
            or len(set(pages)) != len(pages) or any(page < 1 or page > manifest["paper"]["page_count"] for page in pages)):
        raise ValueError("Select unique existing physical PDF page numbers")
    indexed = json.loads(_read(folder, "pages.json", _API_LIMIT))
    context = "[EXCERPT: complete selected physical PDF pages; other pages are outside this context.]\n"
    coordinates = []
    for page in pages:
        context += f"\n[Physical PDF page {page}]\n"
        start = len(context)
        context += indexed[page - 1]["text"]
        coordinates.append({"page": page, "start": start, "end": len(context)})
        context += "\n"
    if len(context) > 28000:
        raise ValueError("Selected complete pages exceed 28000 characters; choose fewer pages")
    relative = f"context-{'-'.join(str(page) for page in pages)}.txt"
    target = folder / relative
    if _is_link(target):
        raise ValueError("Unsafe context output path")
    data = context.encode("utf-8")
    if target.exists() and target.read_bytes() != data:
        raise ValueError("Existing context artifact conflicts with selected pages")
    target.write_bytes(data)
    return context, {"source_kind": "pdf_backed_text", "source_path": str(target.resolve()),
                     "raw_sha256": _sha(data), "text_sha256": _sha(data), "text_length": len(context),
                     "pdf_source_path": str((folder / "paper.pdf").resolve()),
                     "pdf_raw_sha256": manifest["paper"]["sha256"], "pages": coordinates,
                     "selected_pages": pages, "is_excerpt": True, "warnings": []}
