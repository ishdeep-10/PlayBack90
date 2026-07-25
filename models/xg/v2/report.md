# xG Model v2

Selected model: `xgboost`

## Test Metrics

| Model | Log loss | Brier | ROC AUC | AP | Calib error | xG | Goals |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| logistic | 0.498546 | 0.158636 | 0.82767 | 0.43928 | 0.25824 | 4289.916 | 1237 |
| xgboost | 0.246263 | 0.070471 | 0.84398 | 0.485252 | 0.005146 | 1198.733 | 1237 |
| xgboost_calibrated | 0.252472 | 0.07121 | 0.843555 | 0.486505 | 0.013259 | 1219.089 | 1237 |

## Notes

- Penalties are excluded from model fitting and assigned fixed xG = 0.78 in production/backfills.
- Competition/league is included as a categorical model feature.
- Time-based match split is used for train/calibration/test.