# xA Model v1

Selected model: `xgboost_calibrated`

Provider-style xA: modeled probability that a completed pass becomes a goal assist.

## Test Metrics

| Model | Log loss | Brier | ROC AUC | AP | Calib error | xA | Assists |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| logistic | 0.198162 | 0.05829562 | 0.978545 | 0.174812 | 0.11012034 | 32865.084 | 716 |
| xgboost | 0.160618 | 0.04787958 | 0.980518 | 0.218392 | 0.08731676 | 26207.691 | 716 |
| xgboost_calibrated | 0.00985 | 0.00224001 | 0.980518 | 0.218392 | 0.00048114 | 655.045 | 716 |
| legacy_rf | 0.015583 | 0.00227316 | 0.895993 | 0.160119 | 0.00071936 | 864.226 | 716 |

## Notes

- Training universe is completed passes only.
- Target is provider-style actual goal assist probability.
- Direct shot-assist and linked shot xG columns are kept only for diagnostics and future xAG work.
- Time-based match split is used for train/calibration/test.