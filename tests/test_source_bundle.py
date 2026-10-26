"""Offline tests of immutable source acquisition; external code is never run."""

import hashlib
import importlib
import json
import os
from pathlib import Path

import pytest


DOI = "10.1007/s10845-024-02470-8"
REPO = "ASnowbow/Transformer4PMSP"
COMMIT = "a" * 40
TREE = "b" * 40
PDF = b"%PDF-1.7\nsynthetic PDF bytes"
SOURCE = {
    "LICENSE": b"MIT License\n\nCopyright (c) Example\n",
    "README.md": f"Paper: https://doi.org/{DOI}\n".encode(),
    "src/env.py": b"class Environment:\n    def reset(self):\n        return 1\n",
}


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def request():
    return {
        "version": 1,
        "paper": {"doi": DOI, "title": "Example", "license": "CC-BY-4.0",
                  "pdf_url": f"https://link.springer.com/content/pdf/{DOI}.pdf",
                  "sha256": hashlib.sha256(PDF).hexdigest()},
        "repository": {"name": REPO, "commit": COMMIT, "license": "MIT",
                       "files": [{"path": path, "blob_sha1": blob(data)}
                                 for path, data in SOURCE.items()]},
    }


class Response:
    def __init__(self, body, status=200, headers=None, chunks=None):
        self.body = body
        self.status_code = status
        self.headers = headers or {}
        self.chunks = chunks

    def iter_content(self, chunk_size):
        yield from self.chunks if self.chunks is not None else [self.body]

    def close(self):
        pass


@pytest.fixture
def offline(monkeypatch):
    module = importlib.import_module("src.ai_workflow.source_bundle")
    tree = {"sha": TREE, "truncated": False,
            "tree": [{"path": path, "mode": "100644", "type": "blob", "sha": blob(data),
                      "size": len(data)} for path, data in SOURCE.items()]}
    responses = {
        f"https://api.github.com/repos/{REPO}/git/commits/{COMMIT}":
            Response(json.dumps({"sha": COMMIT, "tree": {"sha": TREE}}).encode()),
        f"https://api.github.com/repos/{REPO}/git/trees/{TREE}?recursive=1":
            Response(json.dumps(tree).encode()),
        request()["paper"]["pdf_url"]: Response(PDF),
        **{f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/{path}": Response(data)
           for path, data in SOURCE.items()},
    }
    observed = []

    class Session:
        trust_env = True

        def get(self, url, **kwargs):
            assert self.trust_env is False
            assert kwargs["allow_redirects"] is False
            assert 0 < kwargs["timeout"] <= 20
            assert kwargs["stream"] is True
            observed.append(url)
            return responses[url]

        def close(self):
            pass

    monkeypatch.setattr(module.requests, "Session", Session)
    monkeypatch.setattr(module, "_extract_pdf", lambda path: (
        [f"DOI {DOI} https://github.com/{REPO}", "First physical page text", "Second claim"],
        {"title": "Example"},
    ))
    return module, responses, tree, observed


def complete(offline, tmp_path, **kwargs):
    module = offline[0]
    folder = tmp_path / "bundle"
    manifest = module.acquire_source_bundle(request(), folder, **kwargs)
    assert manifest["status"] == "COMPLETED", manifest
    return module, folder, manifest


def test_acquires_pinned_sources_indexes_static_functions_and_verifies(offline, tmp_path):
    module, folder, manifest = complete(offline, tmp_path)
    assert (folder / "paper.pdf").read_bytes() == PDF
    assert (folder / "code/src/env.py").read_bytes() == SOURCE["src/env.py"]
    assert manifest["linkage"]["status"] == "VERIFIED_TEXT_LINKS"
    assert manifest["repository"]["commit"] == COMMIT
    assert manifest["repository"]["files"][2]["blob_sha1"] == blob(SOURCE["src/env.py"])
    assert manifest["function_index"]["src/env.py"][0]["name"] == "Environment.reset"
    assert manifest["function_index"]["src/env.py"][0]["start"] == 2
    assert module.verify_source_bundle(folder)["status"] == "COMPLETED"


@pytest.mark.parametrize("path", ["../escape.py", "/root.py", "C:/root.py", "a\\b.py",
                                 "a/../b.py", "CON.py", "x.py.", "a:x.py", "a?.py",
                                 "weights.pt", ".env", "sub/aux.txt"])
def test_rejects_unsafe_or_non_source_paths_before_network(offline, tmp_path, path):
    module, _, _, observed = offline
    spec = request()
    spec["repository"]["files"][2]["path"] = path
    result = module.acquire_source_bundle(spec, tmp_path / "bad")
    assert result["status"] == "FAILED"
    assert not observed


@pytest.mark.parametrize("change", ["case_collision", "too_many", "floating_commit", "credentials",
                                   "query", "fragment", "wrong_host", "missing_license"])
def test_rejects_unpinned_or_untrusted_request_before_network(offline, tmp_path, change):
    module, _, _, observed = offline
    spec = request()
    if change == "case_collision":
        spec["repository"]["files"].append({"path": "readme.MD", "blob_sha1": "c" * 40})
    elif change == "too_many":
        spec["repository"]["files"] += [{"path": f"x{i}.py", "blob_sha1": "c" * 40} for i in range(10)]
    elif change == "floating_commit":
        spec["repository"]["commit"] = "main"
    elif change == "missing_license":
        spec["repository"]["files"] = spec["repository"]["files"][1:]
    else:
        spec["paper"]["pdf_url"] = {
            "credentials": "https://user:secret@link.springer.com/paper.pdf",
            "query": "https://link.springer.com/paper.pdf?token=secret",
            "fragment": "https://link.springer.com/paper.pdf#secret",
            "wrong_host": "https://example.org/paper.pdf",
        }[change]
    result = module.acquire_source_bundle(spec, tmp_path / "bad")
    assert result["status"] == "FAILED"
    assert not observed


@pytest.mark.parametrize("mutation", ["truncated", "wrong_tree", "symlink", "submodule", "wrong_blob", "missing"])
def test_rejects_untrustworthy_tree_with_partial_manifest(offline, tmp_path, mutation):
    module, responses, tree, _ = offline
    if mutation == "truncated":
        tree["truncated"] = True
    elif mutation == "wrong_tree":
        tree["sha"] = "c" * 40
    elif mutation == "symlink":
        tree["tree"][2]["mode"] = "120000"
    elif mutation == "submodule":
        tree["tree"][2].update(mode="160000", type="commit")
    elif mutation == "wrong_blob":
        tree["tree"][2]["sha"] = "c" * 40
    else:
        tree["tree"].pop()
    responses[f"https://api.github.com/repos/{REPO}/git/trees/{TREE}?recursive=1"] = Response(json.dumps(tree).encode())
    result = module.acquire_source_bundle(request(), tmp_path / "bad")
    assert result["status"] == "FAILED"
    assert json.loads((tmp_path / "bad/manifest.json").read_text())["status"] == "FAILED"
    with pytest.raises(ValueError):
        module.verify_source_bundle(tmp_path / "bad")


@pytest.mark.parametrize("mutation", ["raw_mismatch", "pdf_mismatch", "redirect", "oversize", "invalid_utf8"])
def test_rejects_corrupted_redirected_or_oversize_downloads(offline, tmp_path, mutation):
    module, responses, _, _ = offline
    url = f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/src/env.py"
    if mutation == "raw_mismatch":
        responses[url] = Response(b"print('not pinned')\n")
    elif mutation == "pdf_mismatch":
        responses[request()["paper"]["pdf_url"]] = Response(b"%PDF-wrong")
    elif mutation == "redirect":
        responses[url] = Response(b"", 302, {"Location": "https://evil.invalid/code.py"})
    elif mutation == "oversize":
        responses[url] = Response(b"x" * (256 * 1024 + 1))
    else:
        responses[url] = Response(b"\xff")
    assert module.acquire_source_bundle(request(), tmp_path / "bad")["status"] == "FAILED"


def test_expired_deadline_stops_before_network(offline, tmp_path):
    module, _, _, observed = offline
    result = module.acquire_source_bundle(request(), tmp_path / "bad", remaining_seconds=lambda: 0)
    assert result["status"] == "FAILED"
    assert not observed


def test_checks_deadline_during_stream(offline, tmp_path):
    module, responses, _, _ = offline
    remaining = [100]

    def chunks():
        yield b"%PDF-"
        remaining[0] = 0
        yield b"more"

    responses[request()["paper"]["pdf_url"]] = Response(b"", chunks=chunks())
    result = module.acquire_source_bundle(request(), tmp_path / "bad", remaining_seconds=lambda: remaining[0])
    assert result["status"] == "FAILED"
    assert "deadline" in " ".join(result["errors"]).lower()


def test_cached_pdf_must_match_pin_and_never_bypasses_linkage(offline, tmp_path):
    module, _, _, observed = offline
    cache = tmp_path / "cached.pdf"
    cache.write_bytes(PDF)
    complete(offline, tmp_path, pdf_cache=cache)
    assert request()["paper"]["pdf_url"] not in observed
    cache.write_bytes(b"changed")
    assert module.acquire_source_bundle(request(), tmp_path / "bad", pdf_cache=cache)["status"] == "FAILED"


@pytest.mark.parametrize("missing", ["doi", "repo", "mit"])
def test_requires_bidirectional_text_links_and_mit_license(offline, tmp_path, monkeypatch, missing):
    module = offline[0]
    if missing in {"doi", "repo"}:
        text = "No identifier" if missing == "doi" else DOI
        monkeypatch.setattr(module, "_extract_pdf", lambda path: ([text], {}))
    else:
        spec = request()
        data = b"Not an MIT license"
        spec["repository"]["files"][0]["blob_sha1"] = blob(data)
        tree = offline[2]
        tree["tree"][0].update(sha=blob(data), size=len(data))
        offline[1][f"https://api.github.com/repos/{REPO}/git/trees/{TREE}?recursive=1"] = Response(json.dumps(tree).encode())
        offline[1][f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/LICENSE"] = Response(data)
        assert module.acquire_source_bundle(spec, tmp_path / "bad")["status"] == "FAILED"
        return
    assert module.acquire_source_bundle(request(), tmp_path / "bad")["status"] == "FAILED"


@pytest.mark.parametrize("path", ["paper.pdf", "paper.txt", "pages.json", "request.json", "code/src/env.py"])
def test_verification_rejects_every_modified_core_artifact(offline, tmp_path, path):
    module, folder, _ = complete(offline, tmp_path)
    (folder / path).write_bytes(b"tampered")
    with pytest.raises(ValueError):
        module.verify_source_bundle(folder)
    with pytest.raises(ValueError):
        module.make_paper_context(folder, [2])


def test_verification_does_not_trust_weakened_manifest_or_traversal(offline, tmp_path):
    module, folder, manifest = complete(offline, tmp_path)
    manifest["files_sha256"].pop("code/src/env.py")
    (folder / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        module.verify_source_bundle(folder)


def test_context_keeps_complete_selected_pages_and_physical_coordinates(offline, tmp_path):
    module, folder, _ = complete(offline, tmp_path)
    context, mapping = module.make_paper_context(folder, [2, 3])
    assert "EXCERPT" in context
    assert "First physical page text" in context
    assert "Second claim" in context
    assert DOI not in context
    assert [item["page"] for item in mapping["pages"]] == [2, 3]
    assert context[mapping["pages"][0]["start"]:mapping["pages"][0]["end"]] == "First physical page text"
    assert mapping["text_sha256"] == hashlib.sha256(context.encode()).hexdigest()
    assert mapping["pdf_raw_sha256"] == hashlib.sha256(PDF).hexdigest()
    from src.ai_workflow.evidence_sources import assert_source_files_unchanged
    assert_source_files_unchanged(mapping)
    assert module.verify_source_bundle(folder)["status"] == "COMPLETED"


@pytest.mark.parametrize("pages", [[], [0], [4], [2, 2], [True], ["2"]])
def test_context_rejects_missing_duplicate_or_invalid_pages(offline, tmp_path, pages):
    module, folder, _ = complete(offline, tmp_path)
    with pytest.raises(ValueError):
        module.make_paper_context(folder, pages)


def test_context_refuses_silent_truncation(offline, tmp_path, monkeypatch):
    module = offline[0]
    monkeypatch.setattr(module, "_extract_pdf", lambda path: ([f"{DOI} https://github.com/{REPO}", "x" * 28000], {}))
    _, folder, _ = complete(offline, tmp_path)
    with pytest.raises(ValueError, match="28000"):
        module.make_paper_context(folder, [2])


def test_existing_output_is_never_overwritten(offline, tmp_path):
    module, folder, _ = complete(offline, tmp_path)
    original = (folder / "manifest.json").read_bytes()
    with pytest.raises(ValueError):
        module.acquire_source_bundle(request(), folder)
    assert (folder / "manifest.json").read_bytes() == original


@pytest.mark.parametrize("field", ["source_url", "line_count", "function_index"])
def test_verification_checks_derived_code_provenance_not_only_file_bytes(offline, tmp_path, field):
    module, folder, manifest = complete(offline, tmp_path)
    if field == "function_index":
        manifest[field]["src/env.py"][0]["start"] = 999
    else:
        manifest["repository"]["files"][2][field] = "https://evil.invalid" if field == "source_url" else 999
    (folder / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        module.verify_source_bundle(folder)


def test_rejects_case_colliding_parent_directories_before_network(offline, tmp_path):
    module, _, _, observed = offline
    spec = request()
    spec["repository"]["files"].append({"path": "SRC/another.py", "blob_sha1": "c" * 40})
    assert module.acquire_source_bundle(spec, tmp_path / "bad")["status"] == "FAILED"
    assert not observed


def test_oversize_extracted_text_cannot_be_marked_completed(offline, tmp_path, monkeypatch):
    module = offline[0]
    monkeypatch.setattr(module, "_extract_pdf", lambda path: (
        [f"{DOI} https://github.com/{REPO}", "x" * (3 * 1024 * 1024)], {}))
    assert module.acquire_source_bundle(request(), tmp_path / "bad")["status"] == "FAILED"


def test_malformed_manifest_has_clear_validation_failure(offline, tmp_path):
    module, folder, _ = complete(offline, tmp_path)
    (folder / "manifest.json").write_text("[]")
    with pytest.raises(ValueError):
        module.verify_source_bundle(folder)


def test_standard_environment_proxy_works_without_ambient_netrc_auth(offline, tmp_path, monkeypatch):
    module, responses, _, _ = offline
    proxy = {"https": "http://127.0.0.1:8888"}
    monkeypatch.setattr(module.requests.utils, "get_environ_proxies", lambda url: proxy)

    class Session:
        trust_env = True

        def get(self, url, **kwargs):
            assert self.trust_env is False
            if kwargs.get("proxies") != proxy:
                raise ValueError("Configured proxy was not used")
            return responses[url]

        def close(self):
            pass

    monkeypatch.setattr(module.requests, "Session", Session)
    complete(offline, tmp_path)


def test_proxy_credentials_are_never_sent_or_saved(offline, tmp_path, monkeypatch):
    module = offline[0]
    monkeypatch.setattr(module.requests.utils, "get_environ_proxies", lambda url: {
        "https": "http://user:proxy-secret@127.0.0.1:8888"})
    result = module.acquire_source_bundle(request(), tmp_path / "bad")
    assert result["status"] == "FAILED"
    assert "proxy-secret" not in json.dumps(result)


def repository_cache(offline, tmp_path):
    """Store the exact GitHub JSON/raw responses as an explicit replay input."""
    folder = tmp_path / "repository-cache"
    folder.mkdir()
    responses = offline[1]
    (folder / "commit.json").write_bytes(responses[f"https://api.github.com/repos/{REPO}/git/commits/{COMMIT}"].body)
    (folder / "tree.json").write_bytes(responses[f"https://api.github.com/repos/{REPO}/git/trees/{TREE}?recursive=1"].body)
    for path, data in SOURCE.items():
        target = folder / "code" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return folder


def test_replays_explicit_repository_and_pdf_caches_without_network(offline, tmp_path, monkeypatch):
    module = offline[0]
    cache = repository_cache(offline, tmp_path)
    pdf = tmp_path / "cached.pdf"
    pdf.write_bytes(PDF)

    def deny_session():
        raise AssertionError("Replay must never create a network session")

    monkeypatch.setattr(module.requests, "Session", deny_session)
    result = module.acquire_source_bundle(request(), tmp_path / "replayed", repository_cache=cache, pdf_cache=pdf)
    assert result["status"] == "COMPLETED", result
    assert result["repository"]["transport"] == "cached_github_records"
    assert module.verify_source_bundle(tmp_path / "replayed")["status"] == "COMPLETED"
    assert (tmp_path / "replayed/commit.json").read_bytes() == (cache / "commit.json").read_bytes()
    assert (tmp_path / "replayed/code/src/env.py").read_bytes() == SOURCE["src/env.py"]


@pytest.mark.parametrize("mutation", ["commit", "tree", "blob", "missing", "oversize", "unsafe_request"])
def test_cached_records_obey_the_same_immutable_identity_and_path_checks(offline, tmp_path, mutation):
    module = offline[0]
    cache = repository_cache(offline, tmp_path)
    spec = request()
    if mutation == "commit":
        (cache / "commit.json").write_text(json.dumps({"sha": "c" * 40, "tree": {"sha": TREE}}))
    elif mutation == "tree":
        tree = json.loads((cache / "tree.json").read_text())
        tree["tree"][2]["mode"] = "120000"
        (cache / "tree.json").write_text(json.dumps(tree))
    elif mutation == "blob":
        (cache / "code/src/env.py").write_bytes(b"Not the pinned code")
    elif mutation == "missing":
        (cache / "code/src/env.py").unlink()
    elif mutation == "oversize":
        (cache / "code/src/env.py").write_bytes(b"x" * (256 * 1024 + 1))
    else:
        spec["repository"]["files"][2]["path"] = "../escape.py"
    result = module.acquire_source_bundle(spec, tmp_path / "bad", repository_cache=cache)
    assert result["status"] == "FAILED"
    assert not offline[3]
    assert json.loads((tmp_path / "bad/manifest.json").read_text())["status"] == "FAILED"


def test_cached_source_symlink_is_rejected(offline, tmp_path):
    module = offline[0]
    cache = repository_cache(offline, tmp_path)
    real = tmp_path / "env.py"
    real.write_bytes(SOURCE["src/env.py"])
    target = cache / "code/src/env.py"
    target.unlink()
    try:
        target.symlink_to(real)
    except OSError:
        pytest.skip("Creating Windows symlinks requires OS permission")
    result = module.acquire_source_bundle(request(), tmp_path / "bad", repository_cache=cache)
    assert result["status"] == "FAILED"
    assert not offline[3]


def test_cached_and_network_core_bytes_have_identical_hashes(offline, tmp_path):
    module, _, network = complete(offline, tmp_path)
    cache = repository_cache(offline, tmp_path)
    pdf = tmp_path / "cached.pdf"
    pdf.write_bytes(PDF)
    replayed = module.acquire_source_bundle(request(), tmp_path / "replayed", repository_cache=cache, pdf_cache=pdf)
    assert replayed["status"] == "COMPLETED", replayed
    assert replayed["files_sha256"] == network["files_sha256"]
    expected_repo = {**network["repository"], "transport": "cached_github_records"}
    assert replayed["repository"] == expected_repo


@pytest.mark.parametrize("invalid", [None, {}, {"version": 1}, "credentials", "query"])
def test_public_request_validation_rejects_unsafe_inputs_without_persistence(offline, tmp_path, invalid):
    module = offline[0]
    spec = request()
    if invalid == "credentials":
        spec["paper"]["pdf_url"] = "https://user:validation-secret@link.springer.com/paper.pdf"
    elif invalid == "query":
        spec["paper"]["pdf_url"] += "?token=validation-secret"
    else:
        spec = invalid
    with pytest.raises(ValueError) as caught:
        module.validate_source_request(spec)
    assert "validation-secret" not in str(caught.value)
    assert not list(tmp_path.iterdir())
    assert not offline[3]


def test_public_request_validation_accepts_the_supported_pinned_request(offline):
    assert offline[0].validate_source_request(request()) is None


def excerpt(page=2, start=0, end=5, text="First physical page text"):
    return {"page": page, "start": start, "end": end,
            "page_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def test_excerpt_validation_accepts_ordered_adjacent_spans_without_file_access(offline, tmp_path):
    validate = getattr(offline[0], "validate_excerpt_selection", None)
    assert callable(validate), "Public pure excerpt validation is required"
    selections = [excerpt(end=2400), excerpt(start=2400, end=4800)]
    original = json.dumps(selections)
    assert validate(selections) is None
    assert json.dumps(selections) == original
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("invalid", [
    None, {}, (), [], [excerpt(), excerpt(), excerpt()], [None],
    [{**excerpt(), "extra": "selection-secret"}],
    [{key: value for key, value in excerpt().items() if key != "page_sha256"}],
    [{**excerpt(), "page": True}], [{**excerpt(), "page": "2"}],
    [{**excerpt(), "page": 0}], [{**excerpt(), "page": -1}],
    [{**excerpt(), "start": False}], [{**excerpt(), "start": 0.0}],
    [{**excerpt(), "start": -1}], [{**excerpt(), "end": True}],
    [{**excerpt(), "end": "5"}], [excerpt(start=5, end=5)],
    [excerpt(start=5, end=4)], [excerpt(end=2401)],
    [{**excerpt(), "page_sha256": None}],
    [{**excerpt(), "page_sha256": "A" * 64}],
    [{**excerpt(), "page_sha256": "g" * 64}],
    [{**excerpt(), "page_sha256": "a" * 63}],
    [excerpt(page=3), excerpt(page=2)],
    [excerpt(start=5, end=10), excerpt(start=0, end=5)],
    [excerpt(start=0, end=6), excerpt(start=5, end=10)],
    [excerpt(), excerpt()],
])
def test_excerpt_validation_rejects_unsafe_oversize_or_unordered_selectors(offline, invalid):
    with pytest.raises(ValueError) as caught:
        offline[0].validate_excerpt_selection(invalid)
    assert "selection-secret" not in str(caught.value)


def test_excerpt_keeps_exact_source_offsets_page_identity_and_compatible_audit(offline, tmp_path):
    module, folder, manifest = complete(offline, tmp_path)
    make_excerpt = getattr(module, "make_paper_excerpt", None)
    assert callable(make_excerpt), "Public bounded excerpt context is required"
    context, mapping = make_excerpt(folder, [excerpt(start=6, end=19),
                                           excerpt(page=3, end=12, text="Second claim")])
    first, second = mapping["pages"]
    assert context[first["start"]:first["end"]] == "physical page"
    assert context[second["start"]:second["end"]] == "Second claim"
    assert (first["page"], first["source_start"], first["source_end"]) == (2, 6, 19)
    assert (second["page"], second["source_start"], second["source_end"]) == (3, 0, 12)
    assert first["page_text_sha256"] == excerpt()["page_sha256"]
    assert second["page_text_sha256"] == excerpt(text="Second claim")["page_sha256"]
    assert "First" not in context and DOI not in context and "return 1" not in context
    assert len(context) <= 6000
    assert mapping["selected_pages"] == [2, 3]
    assert mapping["is_excerpt"] is True
    assert mapping["source_kind"] == "pdf_backed_text"
    assert mapping["text_length"] == len(context)
    assert mapping["text_sha256"] == mapping["raw_sha256"] == hashlib.sha256(context.encode("utf-8")).hexdigest()
    assert mapping["pdf_raw_sha256"] == manifest["paper"]["sha256"]
    assert Path(mapping["pdf_source_path"]) == (folder / "paper.pdf").resolve()
    from src.ai_workflow.evidence_sources import assert_source_files_unchanged
    from src.ai_workflow.evidence import audit_claim_evidence
    from src.ai_workflow.schemas import PaperExtractionReport
    assert_source_files_unchanged(mapping)
    report = PaperExtractionReport(title="Example", problem_type="Claim", math_model={},
                                   rl_formulation={}, codebase_alignment={},
                                   claim_evidence=[{"field": "problem_type", "quote": "physical page",
                                                    "source_start": first["start"]}])
    audited = audit_claim_evidence(report, context, source_map=mapping)
    claim = audited.evidence_audit["claims"][0]
    assert claim["status"] == "located_unreviewed"
    assert claim["locations"][0]["page_start"] == claim["locations"][0]["page_end"] == 2
    assert audited.evidence_status == "unverified"
    assert module.verify_source_bundle(folder)["status"] == "COMPLETED"


def test_excerpt_repeated_same_page_text_preserves_each_original_span(offline, tmp_path, monkeypatch):
    module = offline[0]
    text = "same exact repeated evidence | same exact repeated evidence"
    monkeypatch.setattr(module, "_extract_pdf", lambda path: (
        [f"{DOI} https://github.com/{REPO}", text], {}))
    _, folder, _ = complete(offline, tmp_path)
    context, mapping = module.make_paper_excerpt(folder, [excerpt(start=0, end=28, text=text),
                                                         excerpt(start=31, end=59, text=text)])
    assert mapping["selected_pages"] == [2]
    assert [(row["page"], row["source_start"], row["source_end"]) for row in mapping["pages"]] == [
        (2, 0, 28), (2, 31, 59)]
    for row in mapping["pages"]:
        assert context[row["start"]:row["end"]] == "same exact repeated evidence"
    assert mapping["pages"][0]["end"] < mapping["pages"][1]["start"]


def test_excerpt_offsets_count_unicode_characters_and_hash_utf8_page_text(offline, tmp_path, monkeypatch):
    module = offline[0]
    text = "前😀缀选中的证据后缀"
    monkeypatch.setattr(module, "_extract_pdf", lambda path: (
        [f"{DOI} https://github.com/{REPO}", text], {}))
    _, folder, _ = complete(offline, tmp_path)
    context, mapping = module.make_paper_excerpt(folder, [excerpt(start=3, end=8, text=text)])
    row = mapping["pages"][0]
    assert context[row["start"]:row["end"]] == "选中的证据"
    assert row["end"] - row["start"] == 5
    assert row["page_text_sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("selections", [
    [excerpt(page=4)], [excerpt(end=25)], [{**excerpt(), "page_sha256": "0" * 64}],
    [excerpt(), excerpt(page=3, end=13, text="Second claim")],
])
def test_excerpt_rejects_missing_out_of_page_or_stale_hash_without_context_writes(offline, tmp_path, selections):
    module, folder, _ = complete(offline, tmp_path)
    before = set(folder.iterdir())
    with pytest.raises(ValueError):
        module.make_paper_excerpt(folder, selections)
    assert set(folder.iterdir()) == before


@pytest.mark.parametrize("artifact", ["paper.pdf", "pages.json", "paper.txt"])
def test_excerpt_reverifies_pinned_bundle_before_using_a_page(offline, tmp_path, artifact):
    module, folder, _ = complete(offline, tmp_path)
    (folder / artifact).write_bytes(b"changed")
    with pytest.raises(ValueError):
        module.make_paper_excerpt(folder, [excerpt()])
    assert not list(folder.glob("excerpt-*.txt"))


def test_excerpt_accepts_maximum_selection_without_silent_truncation(offline, tmp_path, monkeypatch):
    module = offline[0]
    text = "a" * 2400 + "b" * 2400 + "OUTSIDE" * 30
    monkeypatch.setattr(module, "_extract_pdf", lambda path: (
        [f"{DOI} https://github.com/{REPO}", text], {}))
    _, folder, _ = complete(offline, tmp_path)
    context, mapping = module.make_paper_excerpt(folder, [excerpt(end=2400, text=text),
                                                         excerpt(start=2400, end=4800, text=text)])
    first, second = mapping["pages"]
    assert context[first["start"]:first["end"]] == "a" * 2400
    assert context[second["start"]:second["end"]] == "b" * 2400
    assert "OUTSIDE" not in context
    assert 4800 < len(context) <= 6000


def test_excerpt_context_is_content_addressed_and_existing_identical_output_is_not_rewritten(offline, tmp_path):
    module, folder, _ = complete(offline, tmp_path)
    selections = [excerpt(start=6, end=19)]
    context, mapping = module.make_paper_excerpt(folder, selections)
    target = Path(mapping["source_path"])
    assert mapping["raw_sha256"] in target.name
    assert target.parent == folder.resolve() and target.suffix == ".txt"
    assert target.read_bytes() == context.encode("utf-8")
    os.utime(target, ns=(1_000_000_000, 1_000_000_000))
    timestamp = target.stat().st_mtime_ns
    assert module.make_paper_excerpt(folder, selections) == (context, mapping)
    assert target.stat().st_mtime_ns == timestamp
    another_context, another_mapping = module.make_paper_excerpt(folder, [excerpt(end=5)])
    assert another_mapping["source_path"] != mapping["source_path"]
    assert another_context != context
    assert target.read_bytes() == context.encode("utf-8")


@pytest.mark.parametrize("conflict", ["changed_file", "directory", "symlink"])
def test_excerpt_rejects_output_conflicts_and_unsafe_links_without_overwrite(offline, tmp_path, conflict):
    module, folder, _ = complete(offline, tmp_path)
    _, mapping = module.make_paper_excerpt(folder, [excerpt()])
    target = Path(mapping["source_path"])
    target.unlink()
    if conflict == "changed_file":
        target.write_bytes(b"existing-conflict")
    elif conflict == "directory":
        target.mkdir()
    else:
        outside = tmp_path / "outside.txt"
        outside.write_bytes(b"existing-conflict")
        try:
            target.symlink_to(outside)
        except OSError:
            pytest.skip("Creating Windows symlinks requires OS permission")
    with pytest.raises(ValueError):
        module.make_paper_excerpt(folder, [excerpt()])
    if conflict == "directory":
        assert target.is_dir() and not list(target.iterdir())
    else:
        assert target.read_bytes() == b"existing-conflict"
