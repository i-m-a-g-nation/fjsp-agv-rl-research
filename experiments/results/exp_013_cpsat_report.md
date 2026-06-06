# CP-SAT Benchmark Report

This report summarizes 60 aggregate rows over 30 tracked FJSPLib instances. All values are derived from exp_009 CSV outputs whose schedules passed the independent feasibility checker.

Fully feasible aggregate rows: 60/60. Best worker rows with all repeated runs proved OPTIMAL: 13/30.

## Worker Summary

| workers | instances | feasible rows | proved optimal rows | mean best makespan | mean best bound | mean best gap | mean runtime s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 30 | 30 | 12 | 674.333 | 258.067 | 0.451173 | 1.939294 |
| auto | 30 | 30 | 12 | 590.367 | 358.900 | 0.273244 | 1.879550 |

## Best Row Per Instance

| instance | best workers | best makespan | best bound | best gap | statuses |
| --- | --- | --- | --- | --- | --- |
| Brandimarte1993/mk01.fjs | 1 | 40 | 40.000000 | 0.000000 | OPTIMAL:2 |
| Brandimarte1993/mk02.fjs | auto | 30 | 20.000000 | 0.333333 | FEASIBLE:2 |
| Brandimarte1993/mk03.fjs | auto | 234 | 74.000000 | 0.683761 | FEASIBLE:2 |
| Brandimarte1993/mk04.fjs | auto | 64 | 40.000000 | 0.411765 | FEASIBLE:2 |
| Brandimarte1993/mk05.fjs | auto | 183 | 83.000000 | 0.546448 | FEASIBLE:2 |
| Brandimarte1993/mk06.fjs | auto | 85 | 27.000000 | 0.686047 | FEASIBLE:2 |
| Brandimarte1993/mk07.fjs | auto | 189 | 74.000000 | 0.614583 | FEASIBLE:2 |
| Brandimarte1993/mk08.fjs | auto | 563 | 236.000000 | 0.592401 | FEASIBLE:2 |
| Brandimarte1993/mk09.fjs | auto | 446 | 54.000000 | 0.881166 | FEASIBLE:2 |
| Brandimarte1993/mk10.fjs | auto | 340 | 74.000000 | 0.782353 | FEASIBLE:2 |
| ChambersBarnes1996/mt10c1.fjs | auto | 927 | 864.000000 | 0.067961 | FEASIBLE:2 |
| ChambersBarnes1996/mt10cc.fjs | auto | 908 | 835.000000 | 0.080396 | FEASIBLE:2 |
| ChambersBarnes1996/mt10x.fjs | auto | 922 | 862.000000 | 0.065076 | FEASIBLE:2 |
| DauzerePeresPaulli1994/01a.fjs | auto | 2687 | 2103.000000 | 0.217343 | FEASIBLE:2 |
| DauzerePeresPaulli1994/02a.fjs | auto | 2676 | 1049.000000 | 0.607997 | FEASIBLE:2 |
| DauzerePeresPaulli1994/03a.fjs | auto | 2846 | 426.000000 | 0.850316 | FEASIBLE:2 |
| DauzerePeresPaulli1994/04a.fjs | auto | 2628 | 1974.000000 | 0.252556 | FEASIBLE:2 |
| FattahiMehrabadJolai2007/fattahi1.fjs | 1 | 66 | 66.000000 | 0.000000 | OPTIMAL:2 |
| FattahiMehrabadJolai2007/fattahi2.fjs | 1 | 107 | 107.000000 | 0.000000 | OPTIMAL:2 |
| FattahiMehrabadJolai2007/fattahi3.fjs | 1 | 221 | 221.000000 | 0.000000 | OPTIMAL:2 |
| FattahiMehrabadJolai2007/fattahi4.fjs | 1 | 355 | 355.000000 | 0.000000 | OPTIMAL:2 |
| FattahiMehrabadJolai2007/fattahi5.fjs | 1 | 119 | 119.000000 | 0.000000 | OPTIMAL:2 |
| FattahiMehrabadJolai2007/fattahi6.fjs | 1 | 320 | 320.000000 | 0.000000 | OPTIMAL:2 |
| FattahiMehrabadJolai2007/fattahi7.fjs | 1 | 397 | 397.000000 | 0.000000 | OPTIMAL:2 |
| FattahiMehrabadJolai2007/fattahi8.fjs | 1 | 253 | 253.000000 | 0.000000 | OPTIMAL:2 |
| HurinkJurischThole1994/edata/ft06.fjs | 1 | 55 | 55.000000 | 0.000000 | OPTIMAL:2 |
| KacemHammadiBorne2002/kacem1.fjs | 1 | 11 | 11.000000 | 0.000000 | OPTIMAL:2 |
| KacemHammadiBorne2002/kacem2.fjs | auto | 11 | 11.000000 | 0.000000 | OPTIMAL:2 |
| KacemHammadiBorne2002/kacem3.fjs | auto | 7 | 7.000000 | 0.000000 | OPTIMAL:2 |
| KacemHammadiBorne2002/kacem4.fjs | auto | 21 | 10.000000 | 0.523810 | FEASIBLE:2 |

Interpretation note: `FEASIBLE` rows are valid schedules, but their objective bounds and gaps show that the local time limit did not prove optimality. Matching an upstream BKS is therefore reported as a good feasible solution unless the local status is `OPTIMAL`.

