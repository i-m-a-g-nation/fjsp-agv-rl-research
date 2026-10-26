# State facts and semantic review implementation plan

> **For agentic workers:** Use test-driven development and a fresh final review. Work in the existing isolated branch; no merge or push.

**Goal / spec:** Complete two atomic state facts from the pinned paper and add a separate, explicitly unverified model check of whether each claim is supported. Preserve originals, source identities and project constraints. Produce a concrete representation-only adaptation proposal, without domain changes or training.

**Approaches:** Location-only checks cannot detect a false claim paired with a real quote. Human-only prose would not improve program capability. Add a separate same-model review pass after successful location checking; model judgment remains distinct from human/scientific approval and cannot promote evidence_status.

**Architecture:** Share bounded JSON request/diagnostic handling between field extraction and a new semantic reviewer. Reviewer consumes exactly one re-audited claim and its source excerpt, no code/project contract. Optional explicit semantic_review in exp023 runs extraction then review under one RunBudget, persists each stage immediately, and stops on a flagged or failed review. Existing requests remain location-only.

**Constraints:** No AGV, PPO/training, dependencies, checkers, rewards, maintenance, objectives or approval policy changes. The reviewer is a separate call to the same provider/model, not an independent model or mathematical proof. Each supported review requires an exact quote inside one original span; partial/unsupported/insufficient evidence blocks readiness. Missing extraction cannot be reviewed. No auto repair for semantic batches; no implicit fallback/retry/budget reset. The prior two batches remain immutable.

**New live envelope:** At most4calls/32768reserved output tokens/300active seconds: two extraction+review pairs, enabled/max8192/60 per call, network retries0, extraction repairs0. Validate all minimum planned calls/tokens before acquisition; do not spend unused previous-batch allowance.

## Tasks

- [x] Extract common JSON invocation/diagnostics into model_json.py preserving existing16 SDK tests. Add semantic_review.py/review_paper_claim(cfg,report,paper_text,source_map,on_response=None): strict verdict/reason/quote schema, exact cited-span audit, deterministic claim/source hashes, status model_supported_unreviewed or model_flagged_unreviewed, human_approval false and evidence_status unverified. Test real SDK transport, partial/negative verdicts, invented/marker quotes, invalid input before reservation, truncation and shared budget.
- [x] Add explicit controller opt-in/preflight and tests: default preview0models; old mode unchanged; review runs only after located claim, saves extraction before review, flagged stops later units, failure/deadline/budget preserves extraction and diagnostics, no human approval synthesized.
- [x] Select two exact physical-page state spans from verified local paper; natively preview and run the bounded batch after fresh code review. Archive responses, contexts, hashes and attribution; record any failures without overwriting originals.
- [x] Map paper state/code to existing R1 information and write a concrete representation-only candidate proposal, with preserved action/reward/checker invariants and an eventual controlled comparison design. Update simple human entry. Freeze runtime and run full dedicated regression; scan secrets and commit.

## Review focus

Model-positive verdict must never become verified/scientific approval; real quote plus false or compound claim must be reviewable/flagged; reviewer receives no project/code instructions; repeated/marker/cross-span quotes cannot receive false PDF provenance; timeout or resource exhaustion after extraction must preserve it; offline preview and old requests retain behavior.
