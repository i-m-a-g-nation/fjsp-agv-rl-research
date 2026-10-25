# Navigation and DeepSeek execution record

User requested structure organization, precise API configuration location and official-doc checking before writing. Base905f85f, existing isolated codex/phase2a-protocol worktree; main ancestor at task start0/31. Main not merged/pushed.

## Decisions

- Organize the human entry/navigation while retaining existing research paths and evidence; physical moves would add import/provenance changes unrelated to this setup task.
- DeepSeek official basehttps://api.deepseek.com, modeldeepseek-flash served byDeepSeek-V4.1-Flash-1017 as documented2026-10-25. Current bounded calls explicitly use thinkingdisabled, with optionalenabled; server defaultenabled/high differs. Existing time/token/retry caps remain unchanged.
- Keep RAGlocal; no assumption that a chat endpoint provides embeddings. Actual local.env has empty key, ignored byGit. No API calls with real credentials or live connectivity claim.

## Evidence so far

- Initial27config/checker/API-contract tests observed RED due to missing fields/script/default/API options; then27passed after initial implementation.
- Additional official-doc and installed-SDK inspection found max_tokens remapped to undocumentedmax_completion_tokens. Strengthened actual HTTP assertions (not constructor mocks):4tests reproduced missingmax_tokens. Corrected via SDKextra_body merge and omitted wrapper cap on official host. Both extraction/generation now pass exact HTTP assertions with thinkingenabled/disabled.
- Documentation agentproject_navigation_docs wrote five assigned entry/layout/model guides; no source/data/results moved. Runtime changes owned by parent, no concurrent test suites.
- Broader config/guards/evidence/sessions/CLI focused run87passed/95.84s. Detected and corrected test-fixture cleanup of synthetic environment credentials (manual teardown reproductionTrue beforefix, absent afterfix); final27config tests passed/3.88s. New-doc relative links resolve. Native offline checker exits1NOT_READY for actual blank-key.env, without printing credentials or issuing calls.
- Fresh independent review found noCritical/Important. Its onlyMinor was an official-page link label, corrected toYour First API Call. Review covered adapter, checker and session identity seams; connectivity/modelquality/full-suite evidence remain parent-owned.

## Final verification (2026-10-26)

- Full dedicated-environment command: `python -m pytest -q --cov=src --cov-report=term --cov-fail-under=80`. Result: **673 passed**, source coverage **89.46%**, 388.05 seconds. The 13 warnings are third-party Matplotlib/Pyparsing deprecations. The local full output is `.pytest_cache/deepseek-config-full.log` (ignored).
- Both real-SDK/mocked-HTTP paths preserve the configured output cap as `max_tokens` and omit `max_completion_tokens`; no credentialed provider requests were made.
- The actual local `.env` remains ignored and untracked. It was created without overwriting any prior file and with an empty key; its offline check correctly reported `NOT_READY` for the missing key. Source/checker/contracts and research archives outside this task are unchanged; the main checkout remains clean.
- Navigation, public configuration, checker and tests are ready for a non-secret commit on the current branch. Merge/push and online quality/connectivity verification remain outside this task. Local `.env` does not transfer to a different checkout through a merge.
