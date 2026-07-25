# xPass Model v1

Selected model: `xgboost`

xPass: modeled probability that an attempted pass is completed.

## Test Metrics

| Model | Log loss | Brier | ROC AUC | AP | Calib error | xPass completed | Actual completed | +/- Expected |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| logistic | 0.279036 | 0.08394552 | 0.902441 | 0.974066 | 0.01587391 | 274930.641 | 277716 | 2785.359 |
| xgboost | 0.225228 | 0.06849568 | 0.937778 | 0.984912 | 0.00661473 | 276003.75 | 277716 | 1712.25 |
| xgboost_calibrated | 0.23885 | 0.07043196 | 0.937778 | 0.984912 | 0.02956253 | 276579.185 | 277716 | 1136.815 |

## Notes

- Training universe is attempted pass rows.
- Target is pass completion.
- Outcome-specific accurate/inaccurate flags are not model inputs; they are only collapsed into neutral pass type/play pattern categories.
- Time-based match split is used for train/calibration/test.