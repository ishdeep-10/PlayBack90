# xGOT Model v1

Selected model: `xgboost`

## Test Metrics

| Model | Log loss | Brier | ROC AUC | AP | Calib error | xGOT | Goals |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| logistic | 0.413841 | 0.134199 | 0.862734 | 0.729321 | 0.015703 | 1305.94 | 1324 |
| xgboost | 0.388343 | 0.124458 | 0.880563 | 0.767998 | 0.009926 | 1291.03 | 1324 |
| xgboost_calibrated | 0.397146 | 0.1259 | 0.880834 | 0.769699 | 0.031239 | 1309.212 | 1324 |

## Notes

- xGOT is trained only on on-target, non-blocked shots with goalmouth placement.
- Off-target and blocked shots are assigned xGOT = 0 in production/backfills.
- The existing pre-shot xG is included as a model feature.
- Time-based match split is used for train/calibration/test.