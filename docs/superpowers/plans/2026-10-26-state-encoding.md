# Lossless typed state encoding implementation plan

> **For agentic workers:** Use TDD and a fresh final review. Existing isolated worktree, no merge/push.

**Goal / spec:** Implement the previously reviewed 28x13 representation-only proposal from graduation_state_encoding_candidate.md. Preserve every R1 observation field and demonstrate unchanged replay of saved R2 actions. No neural policy or training is implemented.

**Architecture:** New independent src/graduation/state_encoding.py, without editing the original environment/rules/checkers or package exports. Frozen TypedStateEncoding(mode,status,steps,scale,rows,action_mask,version=1); encode_construction_observation(observation)->TypedStateEncoding; decode_construction_observation(encoded)->ConstructionObservation. A fresh exp024 runs the existing four R2 cases x two modes x three rules and saves encoded traces, independently checked plans and deterministic hashes.

**Format:** rows tuple of28 tuple rows,13 finite built-in floats per row. First24taskrows carry existing3taskfeatures in0:3 and zeros3:10; next4machine rows zeros0:3 and existing7machinefeatures in3:10. Columns10:12 are fixed types(1.,0.)/(0.,1.) even padding;12presence0./1. Padding payloads zero. Scheduled/maintenance_done/f_present are binary floats. Original -1missingfixed sentinel and all payload values copied without coercion, normalization, sorting or rounding. mode/status/steps/scale/action_mask copied exactly; version strictly1.

**Boundary validation:** exact typed objects and immutable tuple shapes, finite built-in floats (bool/int/numpy scalars not accepted as feature floats), strict boolean presences/action masks, modefixed/joint, statusACTIVE/TERMINATED/TRUNCATED/FAILED, strictint steps0..28 and scale>0, binary flags, fixed row types, no nonzero discarded or padding payloads. Both encode/decode revalidate so object.__setattr__ bypasses cannot silently erase data. These are transport-format checks, not a new domain feasibility checker; do not infer legal actions or integer times from features.

**Constraints:** No API/model calls, new dependencies, network, reward/action/domain/contract changes, source method execution or training. Original G1/R1/R2 and previous evidence remain unchanged. Replay proves format/interface equivalence, not policy improvement or a matrix-consuming R2 implementation. Both research targets remainnot_achieved.

## Tasks

1. Parent: codec tests RED then minimal implementation; literal row golden expectations, independent decode fixture, sentinel/padding/flags, signed-zero/fractional exact preservation, shape/type/nonfinite/corrupted data rejection, deep immutability, all lifecycle states and24/4boundary.
2. Worker owns only experiments/exp_024_state_encoding_check.py and tests/test_state_encoding_check.py. Reuse exp022 build_cases/config and R2 episodes; verify baseline/each replayed observation roundtrip and full mask, preserve exact machine clocks; save before/after encoded observations, rewards/actions and plans. Require G1 checks and independent tardiness; no solver certificates, identical schedules/metrics to baseline, no accepted metrics on failure. Fresh output directories only, deterministic outcome digest, source/artifact hashes, failure evidence and nonzeroCLI. Tests include tampered encoder/decoder or invalid plan rejection, repeatability, overwrite refusal and independent restore.
3. Fresh review of codec/runner increment, fix important issues with regression tests. Freeze runtime, run two native24case matrices and independently restore/recheck archived encodings/plans. Full dedicated pytest with80%coverage gate. Human docs/entry and immutable archive, secret scan, commit.

## Review focus

Encoder/decoder sharing the same wrong column mapping must be caught by independent literal fixtures; invalid padding/cross-type columns must never be silently dropped; normalization/sentinels/floatbits and auxiliary fields must roundtrip; replay does not claim policy/representation superiority; every plan/metric independently passes original domain checker; serialization remains bounded and reproducible; failed rows retain diagnostics without accepted metrics.
