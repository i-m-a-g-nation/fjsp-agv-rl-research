# Execution ledger

User asked to continue model/experiment validation. Reuse current clean managed branch codex/phase2a-protocol, baseline3cdc389; no new worktree. Continue native execution as already chosen; user has opted for action rather than repeated design questions.

Pre-flight: Task1's successful/failed ReplayEpisode is Task2's sole source of result validity. Task2 must never export a successful prefix as a final result for a failed episode.

Task1 starting: hand-checkable tests before implementation.

Task1: 12 new replay tests observed RED (missing module), then replay and existing dynamic suites GREEN, 25 tests. Hand checks confirm final makespans9/13/12, same-time grouping, newly arrived job history frozen at later events, failed prefix never exposed as final. Added fault injection to independently exercise both checker gates and instance identity.

Task1 complete: 15 replay tests GREEN, including checker fault injection. Task2: 5 export/CLI tests RED before Experiment020 existed; new replay/experiment plus existing dynamic suite then GREEN, 28 tests. Negative episode keeps its two successful prefix steps and rejects final makespan across all3 rules.

Native development run: 9/9 episodes,18timestamp groups; separate-directory replay matched trace hashes and digest b9fd42d91316a9ee66d677726fc3a06ecb18ee3b88baf3ad02aa40ce363e64dc. Manually inspected chronology: t1/t4 freezeJ0O0; t6 freezes J0O0(0-3),J0O1(5-9),J1O0(4-6). Planned Cmax11/11/13. Native001/002 passed with original artifacts restored; toy CP-SAT11 OPTIMAL.

Independent final review: no Critical, Important or Minor findings. Read-only probes confirmed all9 combinations, frozen induction, record isolation, exact interval boundaries, same-time arrival then duration change, invalid event/time rejection. Full parent coverage run pending.

Final: Ruling: replay returns the last event's complete future plan, without physical preemption or advancing actual execution to all completions — matches the Phase2A idle-only deterministic model — cost if wrong: physical failures and real-world completion need a richer validated model.

Final: Ruling: preserve the existing mutable ScheduleResult API; internal replay isolates prior records, exported hashes protect saved evidence — cost if wrong: callers can still alter returned objects in memory and must manage that responsibility.

Final: Ruling: development validation does not complete real human approval or research acceptance — no real decisions generated; code changes require a new matching-version session — cost if wrong: the two research topics and human-reviewed execution remain incomplete.

Final complete verification:359/359 passed,88.08% source coverage (80% minimum),13 upstream deprecation warnings, no skipped tests. Native001/002 green and legacy artifacts restored. No corrective code pass required by review. Source freeze and committed-version evidence export in progress.

Source committed as0b6c75b. Saved020 evidence generated from that revision; all source/artifact fingerprints and separate-directory trace hashes verified, digest unchanged. Prepared a new code-matching019 scope session (phase2a-after-sequential-review), provider budget0/calls0, WAITING_HUMAN, no real approval. Prior019 protocol and archived results untouched. All tasks complete; final Git byte verification and artifact commit follow.
