# Project Navigation and DeepSeek Configuration Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for the runtime task; an independent documentation agent owns disjoint navigation files. Checkboxes record completion.

**Goal:** Give the human one project entry point and a correct, editable, offline-checkable DeepSeek official API configuration.

**Architecture:** Retain all research files in place; add navigation and local ignored `.env` from tracked `.env.example`. Existing Chat Completions calls gain explicit DeepSeek thinking options without changing offline/default research permissions.

**Tech Stack:** Existing dedicated Python, LangChain/OpenAI-compatible client, pytest; no new dependencies.

**Spec:** The requirements and decisions below are the complete small-change spec. User explicitly requested structure organization and model setup after consulting official documentation; no merge was requested.

## Global Constraints / Small-change Spec

- Keep current managed worktree and branch. Main is an ancestor, but merge/push is outside this task. No existing source/data/experiment directories move.
- Official docs checked2026-10-25: `https://api-docs.deepseek.com/api/responses`, `/api/create-chat-completion/`, `/guides/thinking_mode/`, `/quick_start/pricing/`.
- Official Base URL `https://api.deepseek.com`; official model ID `deepseek-flash`, currently served by DeepSeek-V4.1-Flash-1017. Do not use an Alibaba/other host model ID on this endpoint or append `/chat/completions` to SDK base_url.
- DeepSeek server thinking default is enabled/high. This project's existing short bounded extraction/selector calls explicitly default to disabled; expose `LLM_THINKING_MODE=enabled|disabled` and document that this is a project choice, not server default. Keep existing token/time/retry caps unchanged.
- Add `LLMConfig.chat_request_options()` returning DeepSeek `extra_body={thinking:{type:mode}}` only for official `api.deepseek.com` host. Other providers receive no DeepSeek-only option. Apply at both existing ChatOpenAI call sites. Thinking configuration is included in existing session identity via dataclass fields.
- Wire-level investigation: installed ChatOpenAI rewrites max_tokens to max_completion_tokens, while official DeepSeek docs require max_tokens. For DeepSeek pass max_tokens=None to the wrapper and include the exact max_tokens limit with thinking in extra_body; generic hosts keep the previous wrapper cap. Both final HTTP bodies must contain max_tokens and omit max_completion_tokens. This refinement follows observed SDK source and4reproducing RED tests.
- Dataclass API key repr is hidden. `.env` is ignored, initially empty-key, never overwrite existing content, never print secrets. Creating LLMConfig does not implicitly load `.env`; CLI live mode and explicit config checker load it.
- `scripts/check_model_config.py` performs offline validation only, no model/network calls; accepts `--env-file`, validates URL before printing, reports presence of key as boolean, and exits1 for incomplete/invalid configuration. Query/fragment/embedded credentials and full endpoint paths are rejected. Official host model must be deepseek-flash or deepseek-v4-pro; generic compatible providers keep their own model IDs. Valid root/v1 SDK base paths allowed.
- Example uses local RAG hashing; it does not assume DeepSeek chat endpoint provides an embedding model. No RL/model training, paper fetching, synthetic approvals, API-key purchase or paid live call in this task.
- Dedicated Conda only, verify sys.executable before Python command groups. New runtime behavior gets meaningful RED/GREEN tests; documentation changes do not need implementation-mirroring tests.

## Review Focus

- Official endpoint/model/thinking wire payload, real SDK serialization through in-memory HTTP transport.
- Both extraction and candidate generation receive the option; generic hosts do not.
- Offline paths do not read credentials or make network requests.
- Configuration/exception output never includes the API key or credentials embedded in a malformed URL.
- Config changes cannot resume a previously approved persistent session; current source/identity guards remain in force.

### Task 1: Runtime configuration, editable template and offline checker

Files: `src/ai_workflow/config.py`, `src/ai_workflow/langgraph_pipeline.py`, new `scripts/check_model_config.py`, `.env.example`, ignored `.env`, new `tests/test_model_config.py`.

- [x] Write RED tests for new official default, thinking options/validation, key repr and config checker incomplete/valid/malformed/precedence behavior.
- [x] Implement minimum code and template, add actual SDK mocked-wire contract coverage and exercise both pipeline call sites.
- [x] Run focused config/workflow guards/evidence/session/CLI tests to GREEN; preserve existing offline semantics.

### Task 2: Human navigation and official-source usage documentation

Disjoint documentation agent owns new `START_HERE.md`, `docs/project_structure.md`, `docs/model_interface.md`, and top/structure updates to `README.md`, `README.zh-CN.md`. Read this spec; commands/config keys must match Task1. Clearly separate implemented runtime from autonomous-research goal; describe main/worktree `.env` locality. Do not call APIs or move files.

- [x] Write navigation with real relative paths, three-track status and four human-facing file locations.
- [x] Explain exact official settings, project/server thinking difference, local RAG, no live verification claim and model suitability as an unevaluated project judgment.

## Closeout

- [x] One fresh independent code/docs review; full dedicated-environment regression and offline checker validation.
- [x] Confirm `.env` ignored/untracked, original checkers/contracts/archives unchanged; commit owned non-secret files and report exact config path and merge recommendation.
