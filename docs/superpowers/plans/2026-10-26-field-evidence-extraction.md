# Field evidence extraction implementation plan

> **For agentic workers:** Use test-driven development and a fresh final review. Existing isolated worktree; no merge or push.

**Goal:** Obtain one source-located paper field per bounded model request, preserving failures and keeping source facts separate from project proposals.

**Architecture / spec:** Extend the existing verified source bundle with exact character excerpts from physical PDF pages. Add a compact single-field extractor returning the existing unverified PaperExtractionReport. Route explicitly selected field units through the existing exp_023 budget, diagnostics and evidence audit. Existing whole-page units remain compatible.

**Approaches:** Repeating whole-page requests already exhausted 8K and 16K max-thinking caps. Downgrading effort would conflict with the requested max setting. Choose small exact excerpts and a minimal schema; this follows the previously proposed next step authorized by “继续”.

**Tech stack:** Existing Python, Pydantic, LangChain/OpenAI adapter, SQLite budget and pytest; no new dependencies.

## Constraints

- No domain model/checker/contract changes, external code execution, training, candidate application or scientific acceptance.
- Only original paper evidence enters the field prompt; pinned author code stays in a separate recorded comparison context.
- Excerpts carry physical page, page text hash, zero-based half-open original character offsets, context offsets and PDF/context hashes. Reject empty, overlapping, out-of-page, changed or oversized selectors.
- At most two spans; at most 2400 characters each and 4800 selected characters total, context at most 6000 characters. No silent truncation.
- Field output is one claim and one exact quote, or explicit missing. Empty/missing fields cannot pass evidence completeness. Unknown/extra output fields fail schema parsing. Location is not entailment.
- New live batch: at most 2 calls, 16384 output tokens reserved, 150 active seconds; each enabled/max, 8192 tokens, 60 seconds, retries0, repairs0. Old batch is exhausted and immutable.

## Tasks

1. Source excerpt helper in source_bundle.py plus offline source tests: validate selectors; verify bundle and page hashes; deterministic immutable context; retain source provenance and compatible source_map.
2. Compact field extractor in field_extraction.py plus tests: whitelist paper fields, JSON-only tiny schema, official adapter and budget, safe diagnostics before parsing, reject incomplete output, construct partial report with fixed field and unverified status; no RAG/code prompt contamination.
3. exp_023 integration/tests: explicit field+excerpt mode validation, offline preview persistence without key/model call, normal feedback/audit for live, unchanged old mode. Fresh review, then bounded two-unit real reward/action batch using verified caches.
4. Archive real evidence, update human-facing report and navigation. Full dedicated regression after runtime is frozen; commit reviewed nonsecret changes.

## Review focus

Changed page text and repeated/cross-boundary evidence must not receive false provenance; absent output must remain failure; source/code text must not introduce model instructions; profile/call budgets must survive both units; offline preview must work without keys; no project adaptation may be mislabeled as paper fact.
