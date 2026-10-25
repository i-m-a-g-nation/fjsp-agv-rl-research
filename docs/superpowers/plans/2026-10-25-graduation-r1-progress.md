# R1 execution ledger

Baseline347e77b, clean managed codex/phase2a-protocol. User “继续” follows the R1 no-training-environment recommendation and prior stated RL preference. Approved G1 model and written R1 design supply requirements; do not infer PPO/G3batch approval.

Preflight: pure Python MDP core, separate frozen observations and detached terminal results. No new dependencies/adapter/training; no existing checker/solver/contract changes. Test core action/return boundaries first, then independently exhaust reachable tiny trees. Latest baseline538passed/88.82%. One fresh final review after full implementation.

Task1:24core tests observed RED for absent module, then97R1/G1 core tests GREEN. Literal fixed/joint trajectories yield4/0 and6/0, per-step return matches-T/100; immutable padded observations, read-only mode, exact touching/window waiting, required idle-machine maintenance, action nonmutation, detached result/instance copies, reset, truncation and checker-refusal FAILED state verified. Numeric/size bounds reject rather than crop. Production core uses integers, no stochastic policy/solver/trainer/Gym import.
