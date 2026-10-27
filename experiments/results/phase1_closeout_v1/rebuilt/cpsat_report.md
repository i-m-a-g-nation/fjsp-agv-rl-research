# CP-SAT Benchmark Report

This report summarizes 30 aggregate rows over 30 tracked FJSPLib instances. All values are derived from exp_009 CSV outputs whose schedules passed the independent feasibility checker.

Fully feasible aggregate rows: 30/30. Best worker rows with all repeated runs proved OPTIMAL: 13/30.

Best worker rows reaching the upstream FJSPLib upper bound: 14/30. Rows reaching UB without a local optimality proof: 1/30.

## Worker Summary

| workers | instances | feasible rows | proved optimal rows | mean best makespan | mean best bound | mean best gap | mean runtime s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 30 | 30 | 13 | 674.300 | 258.300 | 0.416678 | 1.918001 |

## Best Row Per Instance

| instance | best workers | best makespan | FJSPLib LB | FJSPLib UB | UB gap | reaches UB | local proof | best bound | best gap | statuses |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Brandimarte1993/mk01.fjs | 1 | 40 | 40 | 40 | 0.000000 | yes | yes | 40.000000 | 0.000000 | OPTIMAL:1 |
| Brandimarte1993/mk02.fjs | 1 | 30 | 26 | 26 | 0.153846 | no | no | 3.000000 | 0.900000 | FEASIBLE:1 |
| Brandimarte1993/mk03.fjs | 1 | 415 | 204 | 204 | 1.034314 | no | no | 20.000000 | 0.951807 | FEASIBLE:1 |
| Brandimarte1993/mk04.fjs | 1 | 60 | 60 | 60 | 0.000000 | yes | no | 14.000000 | 0.766667 | FEASIBLE:1 |
| Brandimarte1993/mk05.fjs | 1 | 181 | 172 | 172 | 0.052326 | no | no | 32.000000 | 0.823204 | FEASIBLE:1 |
| Brandimarte1993/mk06.fjs | 1 | 136 | 57 | 57 | 1.385965 | no | no | 6.000000 | 0.955882 | FEASIBLE:1 |
| Brandimarte1993/mk07.fjs | 1 | 192 | 139 | 139 | 0.381295 | no | no | 25.000000 | 0.869792 | FEASIBLE:1 |
| Brandimarte1993/mk08.fjs | 1 | 605 | 523 | 523 | 0.156788 | no | no | 182.000000 | 0.699174 | FEASIBLE:1 |
| Brandimarte1993/mk09.fjs | 1 | 589 | 307 | 307 | 0.918567 | no | no | 27.000000 | 0.954160 | FEASIBLE:1 |
| Brandimarte1993/mk10.fjs | 1 | 534 | 189 | 193 | 1.766839 | no | no | 15.000000 | 0.971910 | FEASIBLE:1 |
| ChambersBarnes1996/mt10c1.fjs | 1 | 928 | 927 | 927 | 0.001079 | no | no | 759.000000 | 0.182112 | FEASIBLE:1 |
| ChambersBarnes1996/mt10cc.fjs | 1 | 933 | 908 | 908 | 0.027533 | no | no | 655.000000 | 0.297964 | FEASIBLE:1 |
| ChambersBarnes1996/mt10x.fjs | 1 | 948 | 918 | 918 | 0.032680 | no | no | 655.000000 | 0.309072 | FEASIBLE:1 |
| DauzerePeresPaulli1994/01a.fjs | 1 | 2843 | 2505 | 2505 | 0.134930 | no | no | 1395.000000 | 0.509321 | FEASIBLE:1 |
| DauzerePeresPaulli1994/02a.fjs | 1 | 3012 | 2228 | 2228 | 0.351885 | no | no | 506.000000 | 0.832005 | FEASIBLE:1 |
| DauzerePeresPaulli1994/03a.fjs | 1 | 3894 | 2228 | 2228 | 0.747756 | no | no | 108.000000 | 0.972265 | FEASIBLE:1 |
| DauzerePeresPaulli1994/04a.fjs | 1 | 2798 | 2503 | 2503 | 0.117859 | no | no | 1385.000000 | 0.505004 | FEASIBLE:1 |
| FattahiMehrabadJolai2007/fattahi1.fjs | 1 | 66 | 66 | 66 | 0.000000 | yes | yes | 66.000000 | 0.000000 | OPTIMAL:1 |
| FattahiMehrabadJolai2007/fattahi2.fjs | 1 | 107 | 107 | 107 | 0.000000 | yes | yes | 107.000000 | 0.000000 | OPTIMAL:1 |
| FattahiMehrabadJolai2007/fattahi3.fjs | 1 | 221 | 221 | 221 | 0.000000 | yes | yes | 221.000000 | 0.000000 | OPTIMAL:1 |
| FattahiMehrabadJolai2007/fattahi4.fjs | 1 | 355 | 355 | 355 | 0.000000 | yes | yes | 355.000000 | 0.000000 | OPTIMAL:1 |
| FattahiMehrabadJolai2007/fattahi5.fjs | 1 | 119 | 119 | 119 | 0.000000 | yes | yes | 119.000000 | 0.000000 | OPTIMAL:1 |
| FattahiMehrabadJolai2007/fattahi6.fjs | 1 | 320 | 320 | 320 | 0.000000 | yes | yes | 320.000000 | 0.000000 | OPTIMAL:1 |
| FattahiMehrabadJolai2007/fattahi7.fjs | 1 | 397 | 397 | 397 | 0.000000 | yes | yes | 397.000000 | 0.000000 | OPTIMAL:1 |
| FattahiMehrabadJolai2007/fattahi8.fjs | 1 | 253 | 253 | 253 | 0.000000 | yes | yes | 253.000000 | 0.000000 | OPTIMAL:1 |
| HurinkJurischThole1994/edata/ft06.fjs | 1 | 55 | 55 | 55 | 0.000000 | yes | yes | 55.000000 | 0.000000 | OPTIMAL:1 |
| KacemHammadiBorne2002/kacem1.fjs | 1 | 11 | 11 | 11 | 0.000000 | yes | yes | 11.000000 | 0.000000 | OPTIMAL:1 |
| KacemHammadiBorne2002/kacem2.fjs | 1 | 11 | 11 | 11 | 0.000000 | yes | yes | 11.000000 | 0.000000 | OPTIMAL:1 |
| KacemHammadiBorne2002/kacem3.fjs | 1 | 7 | 7 | 7 | 0.000000 | yes | yes | 7.000000 | 0.000000 | OPTIMAL:1 |
| KacemHammadiBorne2002/kacem4.fjs | 1 | 169 | 11 | 11 | 14.363636 | no | no | 0.000000 | 1.000000 | FEASIBLE:1 |

Interpretation note: `FEASIBLE` rows are valid schedules, but their objective bounds and gaps show that the local time limit did not prove optimality. Reaching an upstream UB is therefore reported as a good feasible solution unless the local status is `OPTIMAL`.

