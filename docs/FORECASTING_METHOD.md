# Forecasting method

## Features and training boundary

`features/price.py` computes15features from each origin's released history: lags1/3/6/12; means3/6/12; sample standard deviations3/6/12(ddof1); monthly/yearly changes; origin month, target month and forecast horizon. Price windows end at t−1, not at target. Required missing history fails explicitly; there is no interpolation, imputation, scaler or full-sample feature selection. Calendar/horizon features are known in advance. Each vector preserves dependency months and their publication timestamps.

TrainingBatch pairs historical-origin features with fully mature three-horizon labels. At evaluation t, eligible origin o must satisfy o+3≤t−1 plus every actual availability timestamp. MASE scales use each origin's expanding as-of seasonal differences; undefined/zero scale remains null with a reason, never an arbitrary epsilon.

## Fixed model specifications

| Model | Frozen specification |
|---|---|
| Seasonal Naive12 | target-minus12 observation; not last-observed-price substitution |
| SARIMAX | levels `(1,1,0)×(1,0,0,12)`, no trend/exogenous/log/interpolation; stationarity/invertibility enforced; L-BFGS100maximum iterations; minimum120months; refit each origin |
| LightGBM Direct | independent H1/H2/H3 L2 regressors;100rounds, learning rate.05,7leaves,depth3,min leaf20,L2=1;15features;minimum120mature rows/horizon; shared complete-vector mask;seed20261027,thread1,deterministic,force_col_wise |

No search, early stopping, validation labels at fit time, recursive horizon feedback or hidden fallback. SARIMAX forecasts four steps from t−1 and exports indices1/2/3 for delivery H1/H2/H3. Nonconvergence is a fold failure; valid forecasts with warnings retain recorded warnings. Positive finite point predictions are mandatory.

Named settings live in `configs/forecasting/models.toml` and `features.toml`; `configuration.load_spec('models', root)` returns the same fixed numerical model contract. Point/model schemas prevent unit, horizon or origin substitution. LGB L2 point is not q50.

## Issuance and rolling evaluation

`publisher.NativeForecastPublisher` records origin/cutoff, history identity, latest mature training label/publication, feature/model specs and successful events. An issuance is immutable. Legacy reconstructed rows retain their lower evidence grade; their absent Native history/session/live proof is not manufactured.

Rolling Validation uses36origins2021-06..2024-05 with all three targets per origin. Forecasts are generated before a validation-only evaluator obtains actual labels. Each output retains fit/provenance/failure information; incomplete successful-key subsets cannot be reported as the full108key result. Fold MASE is the average of scaled errors, not pooled MAE divided by an unrelated global scale.

The resulting forecast MAE/MASE and policy implications are in [Validation results](VALIDATION_RESULTS.md). Better prediction error is evaluated separately from procurement cost, fill rate and terminal feasibility.
