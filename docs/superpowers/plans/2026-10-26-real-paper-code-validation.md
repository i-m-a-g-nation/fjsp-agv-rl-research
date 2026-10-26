# Real Paper and Code Validation Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for the controller. A disjoint implementer owns source_bundle.py and its tests; the parent owns the experiment driver and end-to-end verification. Reuse the isolated branch, no merge/push.

**Goal:** Execute the first real-paper/author-code evidence round with immutable versions, physical page and code-line references, bounded max extraction, and explicit adaptation limits.

**Architecture:** A read-only source acquisition tool downloads a verified PDF and selected commit-pinned UTF-8 files; an experiment controller reuses the existing extraction, budget and citation-feedback interfaces. It produces UNREVIEWED materials for the next research decision, not source patches or fabricated approvals.

**Tech Stack:** Existing requests/pypdf/LangChain/Python/pytest. No new dependencies or external code execution.

## Authorized scope and decisions

User said “开始” after the concrete two-step recommendation. Execute the real-paper milestone now, providing a reusable program entry instead of manual-only reading. Paper/source discovery is read-only; no training, checkpoint loading, new maintenance assumptions or algorithm application in this increment.

Selected Li et al., DOI10.1007/s10845-024-02470-8, publisher open access CC-BY-4.0, author repo ASnowbow/Transformer4PMSP commitb4b46b92aa67556391b7e2613ac1213dafe16c60, MIT. Publisher links repo and repo README links DOI. Unlike graduation: dynamic arrivals, heterogeneous speeds, setups, no mandatory maintenance. The paper places maintenance in future work. Original reproduction and project adaptation must stay separate.

Source request is experiments/requests/paper_code_validation_v1.json. PDF SHA256 is pinned after official download; selected files include LICENSE/README, training environment/network/config/main, validation env/config and requirements. No .pt/.pickle/executable artifacts, imports or installations. Static AST indexing is allowed.

Source bundle API: acquire_source_bundle(request:dict, output_dir:Path, *, pdf_cache:Path|None=None, remaining_seconds:Callable|None=None)->dict; verify_source_bundle(folder:Path)->dict; make_paper_context(folder:Path,pages:list[int])->tuple[str,dict]. Source download is explicit when driver runs; module import never fetches or reads credentials. Fixed GitHub API/raw and Springer HTTPS hosts only, no redirects to other hosts, no auth/query-bearing supplied PDF URLs. Strict repository/40hex commit/path/blob identities. At most12 files,256KiB each,2MiB code aggregate,10MiB PDF,3MiB API tree,100PDF pages, fixed per-request timeout<=20sec and active deadline checks while streaming. Reject symlinks/submodules/path traversal/case-colliding names, oversized/invalid content, missing license/README, truncated/mismatched tree, SHA/blob mismatch and conflicting output dirs. Keep partial failure manifest; never reuse incomplete artifacts as verified.

Manifest pins original request, PDF/text/page data, GitHub tree and every selected source file; verify all hashes before context/line access. Verify PDF DOI and author repo link plus README DOI as bidirectional linkage; text links do not authenticate authors or prove paper/code equivalence. Require MIT LICENSE header for this first supported code-license route. Original publisher PDF stored locally, not committed; new artifacts preserve retrieval URLs, hashes and essential result evidence.

Selected page contexts are complete pages with exact original page numbers, explicit excerpt notice, total<=28000chars; no silent truncation. Source maps retain PDF/context hashes for existing deterministic audit. Parent driver gathers pinned code ranges with source URLs/line numbers and keeps paper claims, code behavior and project judgments separate.

Two extraction units: state/action pages10,12,13; reward/network pages14,15,16. Concise target goals in request, at most initial+one repair each. Live max profile8192tokens/60s, retry0, cumulative4calls/32768output reservation/300active seconds including acquisition. Missing key/mode/caps, parse/provider/budget failure or incomplete citations produce honest failed/not-run rows with saved attempts, no hidden fallback/extra calls. Default driver is acquisition only, not live.

Known static mismatch to validate, not silently “fix”: paper R_opt200 vs config100; setup-dependent shaping and gamma.99 do not preserve R1 exact return=-T/100. Validation default1Head rather than proposed2Head, bool('0') and training padding/GAE concerns are static findings, not executed reproductions. Preserve original R1/G1 objective/action/maintenance/checkers; select possible representation-only future adaptation, reject direct reward/environment transplant.

## Tasks

- [x] TDD source bundle validation/download/context maps/manifest tamper rejection; dedicated environment only, print sys.executable. Files source_bundle.py and test_source_bundle.py.
- [x] TDD controller acquisition-only and bounded extraction behavior, mode/key guard, code-range evidence, partial attempts and terminal statuses. Files exp_023_paper_code_validation.py and test_paper_code_validation.py.
- [x] Run the real source bundle and max extraction; inspect paper/code matches with independent source review. Actual result: sources pass, model extraction fails; no semantic/performance acceptance.
- [x] Fresh review, full regression, byte-preserving public evidence archive without keys/full third-party PDF; update navigation/requirements with actual achieved ability and remaining loop gaps.
- [x] Commit reviewed sources/evidence, keep main and existing archives/checkers/contracts unchanged.

## Measured refinements and stopping result

- Anonymous GitHub source403 led to explicit connected-tool repository_cache input, verified with the same immutable pins; no hidden network/auth fallback. Cached source records are replayable and retain MIT licensing.
- Review found rejected credential-bearing URLs persisted before source validation, and success could be finalized after elapsed budget. Four RED regressions then fixes validated both boundaries. Fresh review approved cache/diagnostics.
- Real max calls returned no parseable/final answers; response diagnostics now capture redacted FINAL text, finish reason and numeric usage before parse, never hidden reasoning. Known length/empty/filtered/aborted responses fail even if JSON could parse.
- Ruling: redistribute remaining batch output to one constructor-only paper_excerpt16384/120 request bound to RunBudget, without changing normal caps or original batch4calls/32768/300. Profile TDD57RED then134GREEN. Prompt separates original paper facts from stored target contract. Larger request also exhausted reasoning with no final answer.
- Actual aggregate3calls/32768reserved/204.141active seconds; output allowance exhausted, so no further model calls. Sources replay passes with0calls. Max extraction remains failed; code/assumption migration and training remain unimplemented. Final904pass/1Windows-symlink skip/89.72%.
