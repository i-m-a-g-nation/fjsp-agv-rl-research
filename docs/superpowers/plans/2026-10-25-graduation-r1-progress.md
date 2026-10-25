# R1 execution ledger

Baseline347e77b, clean managed codex/phase2a-protocol. User “继续” follows the R1 no-training-environment recommendation and prior stated RL preference. Approved G1 model and written R1 design supply requirements; do not infer PPO/G3batch approval.

Preflight: pure Python MDP core, separate frozen observations and detached terminal results. No new dependencies/adapter/training; no existing checker/solver/contract changes. Test core action/return boundaries first, then independently exhaust reachable tiny trees. Latest baseline538passed/88.82%. One fresh final review after full implementation.

Task1:24core tests observed RED for absent module, then97R1/G1 core tests GREEN. Literal fixed/joint trajectories yield4/0 and6/0, per-step return matches-T/100; immutable padded observations, read-only mode, exact touching/window waiting, required idle-machine maintenance, action nonmutation, detached result/instance copies, reset, truncation and checker-refusal FAILED state verified. Numeric/size bounds reject rather than crop. Production core uses integers, no stochastic policy/solver/trainer/Gym import.

Task2 complete: added16independent validation cases, no production behavior changes required. All40R1tests GREEN. Complete tiny action trees (100000visit guard) have only G1-valid leaves, exactn+msteps and reward/T agreement, their bestT equals literals4/0/6/0 and the independent oracle on6seeded cases in both modes. CP-SAT invocation forbidden during seeded-tree tests. Six24task/4machine legal rollouts terminate in28steps and reproduce after reset. Test-only deepcopy traversal adds no production hook or search routine.
