# FJSP-AGV-RL Research

Chinese version: [README.zh-CN.md](README.zh-CN.md)

**Start with [START_HERE.md](START_HERE.md) for the maintained project status, latest evidence and next step.** Use the [project structure guide](docs/project_structure.md) to find code and the [experiment guide](experiments/README.md) to choose a reproducible run. This README covers setup and stable project conventions.

The project studies flexible job shop scheduling (FJSP). Its foundation is the Phase 1 static platform and Phase 2A dynamic events, frozen execution history and rescheduling. Project boundaries and authorized extensions are recorded in [AGENTS.md](AGENTS.md) and the current-status entry above.

## Environment and checks

Create a dedicated Conda environment; do not use `base`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_env.ps1
```

The default environment is the project's `.conda-env`. Set `FJSP_CONDA_ENV` before setup to use a custom local location; local environment paths do not belong in tracked files.

Run the local CI-style checks:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_checks.ps1
```

For individual checks, verify the interpreter before running Python:

```powershell
.\.conda-env\python.exe -c "import sys; print(sys.executable)"
.\.conda-env\python.exe experiments\exp_001_toy_instance.py
.\.conda-env\python.exe experiments\exp_002_solver_check.py
.\.conda-env\python.exe -m pytest
```

The printed executable must belong to the dedicated environment. If you set `FJSP_CONDA_ENV`, replace `.\.conda-env\python.exe` with that environment's Python. See the [experiment guide](experiments/README.md) for larger benchmark, dynamic, graduation and research-controller runs.

Model configuration is optional for offline experiments. For model-backed runs, put credentials in `.env` at the root of the **current worktree**, using [`.env.example`](.env.example) and the [model interface guide](docs/model_interface.md). The ignored local `.env` does not transfer through branch merges.

## Code and data

| Location | Purpose |
|---|---|
| [`src/data/`](src/data/), [`src/scheduling/`](src/scheduling/), [`src/solvers/`](src/solvers/) | FJSP instances, encoding/decoding, unified results, feasibility, rules and CP-SAT |
| [`src/dynamic/`](src/dynamic/) | Dynamic events, state, frozen history and rescheduling |
| [`src/graduation/`](src/graduation/) | Graduation maintenance/tardiness model, reference solvers and policy tools |
| [`src/ai_workflow/`](src/ai_workflow/) | Research requirements, evidence, budgets, sessions and review/controller routes |
| [`src/vis/`](src/vis/) | Gantt rendering |
| [`instances/`](instances/README.md) | Smoke instances, tracked FJSPLib subset, provenance and bounds |
| [`experiments/`](experiments/README.md) | Executable experiments, protocols and saved evidence |
| [`tests/`](tests/), [`scripts/`](scripts/) | Tests, environment setup and checks |

The [project structure guide](docs/project_structure.md) provides a task-to-file map. The [Phase 1 code walkthrough](docs/code_walkthrough_phase1.md) and [reproduction checklist](docs/reproducibility_phase1.md) explain the static foundation.

## Scheduling and evidence conventions

Instance data uses `jobs[job_id][op_id] = [(machine_id, processing_time), ...]`. Scheduling algorithms return a unified `ScheduleResult` containing `ScheduleRecord` entries. Results must pass the appropriate feasibility checker before being reported as valid.

The checker verifies exact operation coverage, precedence, machine capacity and eligibility, processing times, and makespan consistency. CP-SAT uses optional operation-machine intervals, exactly-one assignment, precedence and `NoOverlap`, with a time limit. Only `OPTIMAL` proves local optimality; `FEASIBLE` is a time-limited feasible reference. Matching an upstream upper bound is not a local proof.

| Evidence to inspect | Entry |
|---|---|
| Static benchmark inputs and result files | [Instance provenance](instances/README.md), [saved results](experiments/results/README.md) |
| Dynamic protocol and sequential replay | [Phase 2A protocol](docs/phase2a_experiment_protocol.md), [sequential validation](docs/phase2a_sequential_validation.md) |
| Graduation and research execution | [Graduation workflow](docs/graduation_workflow.md), [research workflow](docs/research_workflow.md), [controller guide](docs/research_controller_validation.md) |
| Engineering evidence versus research acceptance | [Phase 2A checklist](docs/phase2a_acceptance.md), [research acceptance map](docs/research_acceptance_map.md) |

**Validation reports, dated documents and saved result tables are snapshots of their stated source, input and run configuration.** They do not replace the current status in [START_HERE.md](START_HERE.md). Reproduce the corresponding run before claiming a fresh validation result. Development specifications and plans in [`docs/superpowers/`](docs/superpowers/) are retained history, not required reading for everyday use.

## Models and CI

- Phase 1 model: [English source](docs/math_model_phase1.tex) / [PDF](docs/math_model_phase1_en.pdf); [Chinese source](docs/math_model_phase1_zh.tex) / [PDF](docs/math_model_phase1_zh.pdf).
- Phase 2A model: [source](docs/math_model_phase2a.tex) / [PDF](docs/math_model_phase2a.pdf), with a [Chinese reading note](docs/phase2a_dynamic_model_zh.md).
- [CI workflow](.github/workflows/ci.yml): benchmark metadata audit, report generation, dynamic smoke checks and pytest coverage, with an 80% minimum. Latest local validation belongs in [START_HERE.md](START_HERE.md).

Random experiments record seeds; solver comparisons record time limits and worker settings. Preserve prior results and read each report together with its manifest and raw evidence. Correctness and reproducibility take priority over performance.
