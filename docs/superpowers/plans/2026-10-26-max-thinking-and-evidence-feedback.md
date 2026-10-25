# Max Thinking and Evidence Feedback Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for the coupled pipeline change; a disjoint implementer may own model configuration. Preserve the existing isolated worktree. Checkboxes track implementation and verification.

**Goal:** Make the requested DeepSeek max reasoning explicit and stop citation-incomplete live extraction from entering candidate generation after one bounded repair.

**Architecture:** Extend existing public configuration, add a focused extraction-feedback helper, and branch the existing graph to a failure report when evidence locations remain incomplete. Retain existing domain checkers and human reviews.

**Tech Stack:** Existing Python, LangChain/OpenAI-compatible client, LangGraph and pytest; no new dependencies.

## Authorized small-change design

User said “完善” after the proposed citation feedback/limited repair/independent checking work and challenged whether max thinking had been enabled. Prior calls were explicitly nonthinking and remain historical evidence. Continue this scope without another approval cycle.

- Official docs checked 2026-10-26: Chat Completions and Thinking Mode at api-docs.deepseek.com. Official request must contain `thinking={type:enabled}` AND `reasoning_effort=max`. `max_tokens` continues to use the existing SDK adapter. Generic providers get no DeepSeek-specific fields.
- Add `LLMConfig.reasoning_effort` from `LLM_REASONING_EFFORT`, restricted to low/high/max, default max. Send it only to official DeepSeek with thinking enabled; disabled mode omits effort. Keep the code's existing disabled default for compatibility, but make the tracked example and this user's local profile enabled/max. Parent alone edits the ignored `.env`, preserving its key and other contents.
- Add `LLMConfig.extraction_repair_attempts: int = 1`, allowed integers 0..1 (not bool). Existing session identity automatically includes these fields. Existing request/session time, token, retry ceilings remain unchanged.
- New `extract_with_feedback(cfg, extract_once, *, paper_text, source_map=None)` returns `(report, quality)`. Callback receives one feedback string. Re-audit every report against the exact source; one initial attempt and at most one repair. History retains both actual reports, issue paths, summaries and feedback. All-empty claims fail completeness. No fabricated quotes or promotion to verified.
- Feedback lists actual missing/invalid/ambiguous claim field/index/status and rejected-reference reasons, bounded in size; it instructs the model to quote supplied text or explicitly remove unsupported inferences. No semantic-entailment guarantee. JSON/schema/provider failures retain existing failure semantics; do not blindly retry them.
- Add optional `feedback=""` to existing `_llm_extract_paper()`. The live extraction graph uses the helper. Exhausted citation issues produce `overall_status=EVIDENCE_INCOMPLETE`, `eval_passed=False`, a readable failure report, and END before code generation/sandbox/memory. Complete evidence still reaches the normal human evidence gate; location completeness does not certify correctness. Existing explicit offline/degraded modes remain labelled as before.
- No changes to AGENTS, research contracts, scheduling/maintenance checkers, solvers, AGV/RL stages, prior evidence, approvals, merge or push.
- After offline verification, at most three diagnostic provider calls (known arithmetic, extraction, optional one repair), max 8192 output tokens each, 60-second request timeout, SDK retry 0, 180 seconds cumulative active budget and 24576 output reservation. Thinking tokens share output caps; truncation/timeouts are failures and do not trigger budget increases. Save exact request-field evidence and only reasoning presence/counts, not reasoning text.

## Tasks

- [x] Configuration TDD: effort validation, official/generic/disabled behavior, both final SDK HTTP payloads, identity and checker public settings. Files: config.py, check_model_config.py, .env.example, test_model_config.py.
- [x] Feedback TDD: complete first attempt, successful repair, exhausted/zero repair, missing/invalid/ambiguous/rejected references, empty claims, stale audit overwrite, budget exhaustion before retry, no source mutation. Files: new extraction_quality.py, tests/test_extraction_quality.py.
- [x] Pipeline TDD: feedback in actual prompt; citation failure never generates/executes a selector; successful repair retains history and reaches evidence review in persistent mode; offline routes unchanged. Files: langgraph_pipeline.py and focused workflow tests.
- [x] Parent updates ignored local thinking settings without printing credentials; verifies no key is staged. Update human interface/workflow guides with exact mode, cap and failure behavior.
- [x] Run focused tests, complete regression with coverage >=80%, independent review, and bounded max-thinking diagnostic. Preserve failed or truncated outputs honestly and recheck numerical claims with existing domain code.
- [x] Archive public results with byte-preserving hashes; commit source/docs/evidence and report actual mode, tests and limitations.

Measured refinement: expose LLM_MAX_OUTPUT_TOKENS / LLM_REQUEST_TIMEOUT_SECONDS env settings with unchanged defaults4096/30 and hard ceilings8192/60; local/example choose8192/60. This follows the actual max extraction8156 completion tokens, not an unbounded budget increase. Each reviewed source refinement received another complete regression; final770passed/89.57%.
