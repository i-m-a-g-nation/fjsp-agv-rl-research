# G1 execution ledger

Baseline535e0aa, clean managed branch codex/phase2a-protocol. User explicitly answered “允许，按首版范围实现 G1”, including one-operation/release0/no-shared-crew first-edition scope. Authorization extends current Phase2A only for G1 data, metrics and maintenance legality; no optimizer/model provider/RL/AGV/transport. No AGENTS or workflow-contract rewrite.

Pre-flight: Task1 produces immutable domain data and a ScheduleResult subclass; Task2 must validate the target production instance before calculating total tardiness. Task3 must combine unmodified static legality with mandatory maintenance and exact metric checks; metric calculation alone is not maintenance acceptance.

Implementation refinement: use a shared internal production-validation helper so metric and maintenance checker cannot drift. It rejects malformed/noninteger records before calling the old checker, without repairing or weakening it. The G1 example report will use manually specified schedules, never a hidden optimizer.

Task1:24data/compatibility tests observed RED before the package existed, then24GREEN. Frozen inputs copy and canonicalize sequences; each machine requires a maintenance specification; production adapter has exactly one real operation/job and no maintenance pseudo-jobs. Native ScheduleResult inheritance preserves production-only makespan.

Task2: test-helper package import corrected before observing15metric tests RED for the absent metric module. Shared production guard and exact sum-of-positive-lateness implementation then39data/metric tests GREEN. Literal witnesses4/0 and6/0 pass; earliness cancellation, malformed numbers, wrong instances and partial/duplicate schedules rejected without mutation.

Task3:34maintenance tests observed RED for the missing checker, then all73G1 tests GREEN. Strict records, mandatory idle-machine maintenance, full-window containment, half-open boundaries, fixed/joint modes, unchanged-static-checker refusal and independent reported-T agreement are exercised. No repairs occur during validation.

Task3 report: docs/graduation_g1_validation.md records the four literal input schedules, expectedT4/0/6/0, production makespans and negative cases. Its rerunnable evidence is the existing pytest fixtures, without a new experiment runner, optimizer or research-performance claim.

Final fresh read-only review: no Critical/Important findings; Declined to judge list empty. Reviewed every new source/test and original checker without running concurrent Python. Final: minor (deferred): deleting a required attribute from an already constructed mutable MaintenanceRecord can raise AttributeError rather than return diagnostics; malformed values/containers are covered, and this rare corrupted-object path never accepts an invalid schedule. This is reported for future robustness work; no second review or expansion of G1.

Task3 complete: dedicated-environment full command `python -m pytest --cov=src --cov-report=term-missing --cov-fail-under=80 -q` returned0:437passed,13upstream warnings,88.37%coverage,229.23s. No source or dependency files changed during the run. Native001/002 then returned0, all production schedules legal and toy CP-SAT11OPTIMAL; savedCSV/Gantt restored byte-for-byte. Original AGENTS/checkers/contracts and019/020 archives/protocol verified unchanged againstHEAD.

Final delivery: all three tasks complete; no Critical/Important fixes required. Documentation distinguishes user-approved G1 from future G2 optimization, workflow integration and formal research acceptance. Keep tested work on codex/phase2a-protocol; no merge/push or runtime human approval. Test logs remain local ignored diagnostics; committed tests and the human-readable fixture report provide rerunnable evidence.
