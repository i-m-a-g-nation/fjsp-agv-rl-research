# Claim evidence traceability implementation plan

> **For agentic workers:** Use executing-plans and test-driven-development; preserve all previous uncommitted safeguards.

**Goal:** Bind extracted paper claims to literal target-source excerpts and deterministic locations without granting scientific verification.

**Architecture:** A source map records text hash, raw-file identity and code-derived PDF page spans. Each model reference names an allowlisted field and item index. A deterministic auditor produces located, missing, invalid or ambiguous results; model-provided audit/status/page claims cannot establish evidence. Existing human review binds this audit through the checkpoint artifact hash.

**Constraints:** Phase 2A only. No paid provider calls, no scheduling/checker changes, no automatic scientific verification. Text matching is distinct from entailment. Exact quoted text must be in the target excerpt actually supplied to the model. Legacy flat quotes cannot satisfy per-claim requirements.

## Review focus
- Wrong field/index, duplicate text, forged offsets or model-assigned pages/statuses.
- RAG quotes from another paper or text outside the supplied target excerpt.
- Empty reports and placeholders mistaken for fully evidenced results.
- PDF empty pages, cached prefixes and mismatched underlying PDF content.
- Markdown quotes containing markup or table delimiters.

### Task 1 — deterministic evidence auditor
- [x] Write failing tests for per-claim references, missing/invalid/ambiguous quotes, offsets, context bounds and source identity.
- [x] Add reference/audit schemas and a pure auditor; keep `evidence_status=unverified`.

### Task 2 — source locations and pipeline integration
- [x] Write failing PDF page-map and mocked-provider integration tests.
- [x] Preserve physical PDF page locations when actual extracted text matches the resolved input; otherwise expose only honest text coordinates.
- [x] Request per-field quotes in the LLM prompt; overwrite model-supplied audit metadata using deterministic source data.

### Task 3 — reviewable reporting and verification
- [x] Include claim audits and source identity in evidence review and readable reports; label codebase adaptation as project suggestions.
- [x] Test original-source/hash changes, escaping and unchanged research-acceptance semantics.
- [x] Run full coverage >=80%, native baseline checks and one independent review; fix important findings with regressions and update the guide.
