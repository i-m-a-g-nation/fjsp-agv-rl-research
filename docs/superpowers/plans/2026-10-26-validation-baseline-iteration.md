# Validation-only diagnostic and single return-baseline candidate

> **For agentic workers:** TDD, isolated ownership, fresh final review; existing worktree, no merge/push.

**Goal / authorization:** User continued after validation-trajectory diagnosis and one bounded improvement next step. Implement an executable diagnose->singlecandidate->validationdecision experiment, preserving the original method/evidence and excluding probe/final-test evaluation this round.

## Diagnosis before candidate

Read-only validated old selected checkpoints on16validationepisodes and112prefix-to-EDD continuations. EDDagreement29/96; divergence26productionorder/16machineassignment/24production-v-maintenance/1maintenancemachine. EDDlowerTT11/16,equal5/16; nonterminalprefixswitchimproves31/80,equal47/80,worsens2/80. Trainingcoefficients1251negative/285zero, no positive; clipping4/256, so no evidence of clipping as primarycause. This supports a hypothesis to test, not a proof that a baseline will fix the gap.

**Approaches:** Increasing architecture/budget would confound the next comparison; EDDsupervision/priors would introduce a teacher. Choose one optional past-return runningmean baseline, holding network/reward/data/budget/seeds fixed. Source context JMLR2004Greensmith/Bartlett/Baxter, https://www.jmlr.org/papers/v5/greensmith04a.html: baselines affect estimatorvariance; average-reward baselines can be suboptimal. No guaranteedvariance/performance improvement or optimalbaseline claim.

## Parent: return baseline + trainer integration

- New src/graduation/return_baseline.py, tests/test_return_baseline.py. `RunningReturnBaseline.center(key:str, returns:tuple[float,...])->dict` gives `baselines`, `advantages`, `count` from PAST complete episodes only. `observe(key,returns)` atomically records rawreturns AFTERsuccessfuloptimizerupdate. `snapshot()->dict` detached counts/means. Max16keys,28steps/key,64observations/key; finitebuilt-infloat values, nonemptyimmutabletuples and boundednonemptystr keys. Firstbaselinezero. Samekeylengthfixed; invalidvalues/overflow reject withoutmutatingstats. Runningmeans weightedpreviousmean andnewreturn. Never center on sameepisode's own mean.
- Extend `train_policy(...,return_baseline='none')` optional literalnone/running_mean, preflightbeforevalidation. Defaultnone path retains exact oldstate hashes/logfields/8returnkeys. For running_mean center using stabletrainingindex key `train:{index}` and originalsamples' gamma1returns, create adjustedPolicySamplecopies, updateonce, thenobserve rawreturns. Originalepisodes/samples/rewards/TT untouched. Log raw_returns, baselines, advantages, baseline_count in `log['return_baseline']` onlycandidate. Include optional baseline_state in candidatevalidationevents fordurability, no exactresume claim. Actor/codec/environment/rules/checkers/contracts/dependencies unchanged.
- Tests literalmeans/counts, keys/stepisolation, firstzero, negative/positiveadvantages, immutablecopies, invalid/overflowatomicity; sameepisodecannotcontaminatebaseline, countbeforeupdate andobserveafter; defaultnone exactoldfixture, invalidflagpreflight, no validationgradient/statupdates.

## Diagnostic worker

Own src/graduation/validation_diagnostics.py +tests/test_validation_diagnostics.py only. `diagnose_validation(archive_dir:Path,*,check_budget=None)->dict`. Turn the read-onlyaudit into reusable code: verify nativeartifact andselectedNPZ/state hashes with safe pathboundaries and allow_pickleFalse; evaluate only training_runs/splits.training/validation (no probe/cprows evaluation), unchanged originalactor/core hashes; oldtrainerhash can be historicalcode because currentoptionalbaselineaddition is intentional and inferenceusesunchangedactor/core. Replay16selectedvalidationplans andprefixes0..n+m using freshenv+originalinteger-tailEDDhelper; G1+TT checks. Report agreement/divergence/P_EDDvsuniform, perrunTT/EDD, prefixoutcomes, traininggradientclip/negativezero counts. No scientificcausationclaim; no source/weight mutation. Budgetcallback beforeloops/steps. Smallhand-fixturetests plus missing/tamperedartifacts/path rejection/probe-exclusion.

## Experiment worker

Own experiments/exp_026_validation_iteration.py +tests/test_validation_iteration.py only. `run_experiment(output_dir:Path,*,episodes=64,max_active_seconds=120,reference_archive=None)->manifest`. Freshdir, offline, oneprocess/nativeBLASenv1; max8trainingruns=2methods(none,running_mean)x2modesx2seeds17/29,64episodes/n4m2=3072trainingsteps. Beforetraining call diagnose_validation(oldexp025archive, budget); save sourcebounddiagnosis. Reuse exp025 frozen training8/validation4 ONLY; do not execute/read/select on probe examples, and omit probe metadata fromnewoutput.

Same init/hyperparameters/trainingorder/actionseeds,64updates perrun,gamma1. Persist callbacklogs/intervalNPZ+initial/final/selected safehashes; baselineextraeventstate retained. Explicit initialselection0 remainsuntrained. Preservefailures/notrun denominators and checkedcompletedprogress ontimeout. Reuse oldpilot safeutilities whereappropriate without editing oldpilot.

Evaluate selectedmethods32validationplans (2methodsx2modesx2seedsx4cases) +EDD/SPT/Random48validationplans (2modesx2seedsx4casesx3rules), total80;8CP1srefs onvalidation only. AlloriginalG1/independentTT/return/replay/certificates. Fail ifcandidatebeatsCP_OPTIMAL. Topper-mode decision onlywhenfullplanneddenominatorscomplete: choose running_mean onlyif strictlower meanvalidationTT than none, ties retainnone; reportbothseeds andallcheckpoints regardlessdecision. Mark developmentselection, not independentperformanceproof or finaltest. No automatedproductiondefaultchange orhuman/scientificapproval.

Bind source/data/config/diagnosis/plan/checkpoint hashes; deterministicoutcome excludesCPtime/paths/runtime. Controlnone64 selected/finalparameterstates must exactlymatch archivedexp025, provingbackcompat. Tinytests episodes1; nativeone8run64batch only afterreview, no tuning/retries. Deadline checks include lastwork/write; checkpointsbetweenintervals remainlastpersistedversion, no implicitexactresume. Tests data/probeexclusion via forbiddenprobe sentinel, samebudgets/decisions/ties/failuredenominators/checkpointload/defaultcontrol, hardstop/overwrite.

## Verification and report

Parenttargetedtests/freshreview/fix, thenfreeze, one120snativetrial andfull dedicatedpytest80% gate. Independentlyreplay rawreturnbaselines/gradientupdates/selection/checkpoints/80+8plans, verifycontrolhash equality andprobeexcluded. Archive alloutcomes evenifcandidatefails. Originaleed1124pilot/metadata/weights unchanged. Outcome is a controlled researchiteration component; unifiedpaper->code->trainingouterloop andbothresearchacceptances remainincomplete.
