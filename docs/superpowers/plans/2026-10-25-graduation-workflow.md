# Graduation supervised backend integration plan

> **For agentic workers:** Execute inline via executing-plans/TDD, one fresh final reviewer. User explicitly requested continuation of the previously proposed integration; no repeated design authorization.

**Goal:** Run reviewed fixed/joint graduation references through existing persistent supervision without certifying research completion.
**Architecture:** A strict request/artifact backend, thin LangGraph nodes and pinned session input, then CLI exposure. Existing contracts/checkers/solvers/protocol archives unchanged.
**Tech Stack:** Existing Python, LangGraph/SQLite, OR-Tools/pytest; dedicated Conda only.
**Spec:** docs/superpowers/specs/2026-10-25-graduation-workflow-design.md.

## Constraints and review focus

- Baseline4efe251, reuse current managed branch; no provider calls/credentials/network, auto-approval, new research algorithm or AGV/RL.
- Untrusted JSON cannot smuggle unknown model fields, mixed routes, nonfinite/boolean values or oversized resources.
- Exact original input survives scope/evidence changes and cross-process resumes; changed path/input/code/runtime cannot inherit approval.
- Mandatory maintenance including idle machines and objective-specific metadata must be validated after extraction and again from saved artifacts.
- Tampered, missing or extra registered artifact paths must reject conclusion; failed/FEASIBLE runs must not certify optimum/research.
- Routing cannot bypass existing human interrupts, budget supervision or affect old paper/dynamic-protocol behavior.

### Task1: strict request, solver backend and artifact verifier
Files: src/ai_workflow/graduation_backend.py; tests/test_graduation_backend.py.
Interfaces: describe_graduation_request(path)->dict; run_graduation_request(path,output,*,expected_request_hash)->manifest; verify_graduation_artifacts(output,manifest_hash)->manifest. JSON embeds G1 data, both fixed/joint modes and bounded solver config; immutable original hash.
- [x] RED strict malformed/unknown/duplicate/large inputs, true4/0, failure/no metric, FEASIBLE honesty, target hash and artifact tamper.
- [x] Implement bounded parser, fixed solver calls, independent domain/metadata check, saved plans and strict reconstruction verifier.
- [x] GREEN `python -m pytest tests/test_graduation_backend.py -q`; commit targeted-tested backend.

### Task2: graph and persistent input binding
Files: langgraph_pipeline.py, sessions.py, session_worker.py; tests/test_graduation_workflow.py.
- [x] RED three gates, no RAG/models, fixed/joint data+hash in scope/evidence, true request path/content binding across resumes, reject stops solving, artifact changes prevent conclusion, wrong-track/mixed route/no-review rejection.
- [x] Add graduation-specific prepare/execute nodes; preserve three reviews, context identity and budget. Session pins original request and source/runtime, defaults no provider budget; new backend acceptance always not_achieved, formal fixed-vs-joint comparison remains outstanding.
- [x] GREEN new graph/session and existing protocol/session suites; commit.

### Task3: CLI, documentation and closeout
Files: experiments/exp_018_ai_rag_workflow.py, experiments/requests/graduation_reference_v1.json; tests/test_graduation_workflow_cli.py, docs/graduation_workflow.md and current status/readmes.
- [x] RED CLI scope pause without paper, wrongtrack/live/mixed inputs before credentials, explicit resume override rejection; persistent synthetic three-review completion returns2 for unachieved research, never0.
- [x] Add --graduation-request and docs/sample, preserving existing options/default routes. No real approval files.
- [x] GREEN targeted then full coverage>=80%; no source changes during full run. One fresh read-only review, single TDD important-fix pass if needed. Native001/002 with legacy artifacts restored.
- [x] Commit tested source; start real CLI only up to scope pause with provider0, verify session/request, document exact pending review. Keep branch/worktree; no push/merge or research completion claim.
