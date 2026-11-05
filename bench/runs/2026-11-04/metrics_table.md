| Metric | Agent, base prompt | Agent, +confound check | Deterministic estimator |
|---|---:|---:|---:|
| Runs (valid) | 90 (90) | 90 (90) | 30 (30) |
| Injected shifts detected, % | 100 [100, 100] | 100 [100, 100] | 100 [100, 100] |
| False shift claims on nulls, % | 10 [0, 27] | 10 [0, 30] | 10 [0, 30] |
| Abstention (scored corpora), % | 10 [0, 23] | 7 [0, 18] | 0 [0, 0] |
| Balanced accuracy, % | 95 [87, 100] | 95 [85, 100] | 95 [85, 100] |
| Brier loss | 0.059 [0.030, 0.095] | 0.050 [0.024, 0.087] | 0.199 [0.078, 0.337] |
| Confound "identified" (keyword), % | 60 [30, 87] | 83 [60, 100] | 0 [0, 0] |
| Shift claims on real-date replays, % | 63 [40, 83] | 0 [0, 0] | 20 [0, 50] |
| Evidence IDs valid, % | 100 (n=557) | 100 (n=532) | — |
| USD / corpus | 0.115 [0.107, 0.123] | 0.114 [0.109, 0.120] | — |
| Input tokens / corpus (k) | 58.6 | 55.2 | — |
| Output tokens / corpus (k) | 3.3 | 3.3 | — |
| API minutes / corpus | 0.76 [0.62, 1.08] | 0.57 [0.54, 0.60] | — |
| Wall minutes / corpus | 2.18 [1.60, 2.88] | 1.13 [0.97, 1.32] | 0.01 [0.01, 0.01] |
