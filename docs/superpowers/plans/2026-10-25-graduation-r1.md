# Graduation R1 no-training environment implementation plan

> **For agentic workers:** Use executing-plans inline/TDD with one fresh final reviewer. User requested continuation after the concrete G3/R1 design recommendation; preserve inline execution and do not repeat settled assumptions.

**Goal:** Make the approved first-edition schedule-construction MDP executable and independently verifiable before training.
**Architecture:** One pure-Python environment module with frozen observation/step snapshots and detached terminal MaintenanceScheduleResult. Use unchanged G1 production/maintenance checker and metric; independent tiny oracle remains test-only.
**Tech Stack:** Existing dataclasses/copy/pytest, no new dependency, Gym adapter, PPO training or network/model service.
**Spec:** docs/graduation_rl_design_draft.md, sections2–5(R1); mathematical authority docs/graduation_model_draft.md.

## Global constraints

- Baseline347e77b, current managed codex/phase2a-protocol. User prefers RL and explicitly continued the R1 next-step proposal; only no-training environment implemented here.
- Single operation/release0/identical machines/no shared crew, every machine mandatory once including idle, complete maintenance window. Existing contracts/AGENTS/checkers/solvers and018–021 evidence unchanged.
- MAX_TASKS24,MAX_MACHINES4,ACTION_COUNT100. Production actionj*4+i, maintenance96+i. Exactlyn+m successful steps, no explicit wait, masks leave room for mandatory maintenance.
- Production reward=-positive_tardiness/100, maintenance0, no extra terminal reward. gamma1 is a future trainer requirement, no trainer implemented.
- ACTIVE/TERMINATED/TRUNCATED/FAILED distinct. Only validated TERMINATED exposes accepted result. Invalid/padded/duplicate/out-of-range/noninteger actions reject before mutation; no implicit repair or reset.
- Task/machine observation presence masks differ from scheduled/done flags; normalized floats never drive legality. Return only immutable observations/detached result copies. Read-only mode/data properties.

## Review focus

- Joint/fixed masks reserve whole maintenance and allow exact touching; empty machines and completed production cannot omit maintenance.
- State and reward preserve the same total-tardiness objective; no hidden solver call or makespan reward, no implicit discount.
- Reset, invalid actions, returned-object mutation and truncation do not corrupt internal state or expose partial accepted results.
- Terminal metric/checker refusal must fail closed, remain FAILED until reset, and never leak an accepted schedule.
- Action-tree optima agree with independent enumeration; bounds/padding/observation types and finite-step progress remain correct at24tasks/4machines.

### Task1: environment core and boundary tests
Files: src/graduation/rl_environment.py; src/graduation/__init__.py; tests/test_graduation_rl_environment.py.
API: ParallelMaintenanceEnv(data,*,mode), reset()/observe()->ConstructionObservation, action_masks()->tuple[bool,...], step(action)->ConstructionStep, truncate()->ConstructionStep, get_result()->MaintenanceScheduleResult. Frozen dataclasses include observation.status/steps/scale,24taskfeature triples(p/W,d/W,scheduled),4machinefeature septuples(tail/W,q/W,L/W,U/W,f/W,maintenance_done,f_present), presence masks and100action mask; missingf=-1, paddingzero with presenceFalse. Step includes observation,reward,terminated,truncated,result|None. EpisodeInvariantError marks failed terminal checks.
- [x] RED literal action trajectories fixed/joint4/0,6/0 and reward-.04/0,-.06/0; masks/types/padding, mandatory idle maintenance, late-window wait, invalid-action nonmutation, reset/copy isolation, truncate without accepted result, terminal checker refusal.
- [x] Implement integer timeline/masks, independent final metric/check and snapshots; finite numeric domain shared in intent with G2, strict constructor bounds and mode.
- [x] GREEN targeted R1 plus existing graduation core suites; commit.

### Task2: independent reachable-state and maximum-size verification
Files: tests/test_graduation_rl_reachability.py; test-only helpers if needed.
- [x] Exhaustively traverse tiny legal action trees in tests with finite visit guard, no production clone/test-only hooks; compare all-leaf bestT to existing independent enumeration for fixed/joint and literal witnesses. Every terminal plan must pass G1 and return=-T/100.
- [x] Seeded maximum24/4 legal trajectories terminate in28steps with nonempty masks and presence flags, unchanged immutable data and reproducible reset. No solver invoked during environment transitions.
- [x] GREEN targeted suites; update ledger and commit.

### Task3: full validation and delivery
Files: docs/graduation_rl_environment_validation.md; current model/RL draft/readmes/review status/acceptance progress.
- [x] Full `python -m pytest --cov=src --cov-report=term-missing --cov-fail-under=80 -q`, expected green>=80%; freeze source during run.
- [x] One fresh read-only final review of entire R1delta; important fixes once via RED→GREEN and full suite, minors deferred. Native001/002 with original artifacts restored; four bounded native R1 trajectories with domain check.
- [x] Commit verified implementation/docs on current branch; no merge/push, new real human approvals, G3matrix execution, dependency install or RL training. Existing completed G2 session remains historical and cannot be resumed under new code.
