# Benchmark Instances

This directory contains local smoke instances and a small tracked subset of
real static FJSP benchmark files.

## Local Smoke Files

- `tiny_2x2_1based.fjs`
- `toy_3x3_0based.fjs`

These files are repository-local test fixtures.

## FJSPLib Subset

The files under `fjsplib/` are copied without semantic modification from the
official ScheduleOpt FJSPLib benchmark repository:

- Library page: <https://scheduleopt.github.io/benchmarks/fjsplib>
- Source repository: <https://github.com/ScheduleOpt/benchmarks/tree/main/flexible%20jobshop>
- Upstream license: CC-BY-SA-4.0

Tracked subset:

| Local file | Upstream family | Instance | Size | FJSPLib LB | FJSPLib UB |
|---|---|---|---:|---:|---:|
| `fjsplib/FattahiMehrabadJolai2007/fattahi1.fjs` | Fattahi, Mehrabad and Jolai (2007) | `fattahi1` | 2 x 2 | 66 | 66 |
| `fjsplib/FattahiMehrabadJolai2007/fattahi2.fjs` | Fattahi, Mehrabad and Jolai (2007) | `fattahi2` | 2 x 2 | 107 | 107 |
| `fjsplib/HurinkJurischThole1994/edata/ft06.fjs` | Hurink, Jurisch and Thole (1994), edata | `ft06` | 6 x 6 | 55 | 55 |
| `fjsplib/KacemHammadiBorne2002/kacem1.fjs` | Kacem, Hammadi and Borne (2002) | `kacem1` | 4 x 5 | 11 | 11 |
| `fjsplib/Brandimarte1993/mk01.fjs` | Brandimarte (1993) | `mk01` | 10 x 6 | 40 | 40 |
| `fjsplib/Brandimarte1993/mk02.fjs` | Brandimarte (1993) | `mk02` | 10 x 6 | 26 | 26 |
| `fjsplib/Brandimarte1993/mk03.fjs` | Brandimarte (1993) | `mk03` | 15 x 8 | 204 | 204 |

The machine-readable mirror [fjsplib_bks.csv](fjsplib_bks.csv) records these
upstream bounds for quality-report scripts. Every currently tracked row has
matching LB and UB values. These are upstream references, not values inferred
from local solver runs. Run `experiments/exp_012_benchmark_metadata_audit.py`
to verify one-to-one tracked-file, metadata-row, and loader consistency.

The subset intentionally spans four source families and increasing sizes.
`mk03` is also large enough to exercise a time-limited `FEASIBLE` CP-SAT result
under the default 10-second batch limit. It may match the upstream BKS without
proving optimality during that local run.

The official benchmark table lists `kacem1` as `4 x 6`, while its official old
format file starts with `4 5 5`. This repository records the loadable file
content as `4 x 5` and retains the upstream BKS of `11`.

## Format

The tracked upstream files use the FJSPLib old text format:

```text
num_jobs num_machines mean_machines_per_operation
```

Each following job record stores its operation count, followed by eligible
machine and processing-time pairs for every operation. Upstream machine ids are
1-based in this subset; `src/data/loader.py` normalizes them to the internal
0-based convention.
