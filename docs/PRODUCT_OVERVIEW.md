# Product overview

Food Commodity Procurement Intelligence is a reproducible decision-support research system for monthly wheat procurement. Its users are procurement analysts, data scientists and reviewers who need to connect forecast accuracy to operational cost and service, rather than select a model using prediction error alone.

## Decision supported

At month-end, allocate the current order across two suppliers with different premiums, lead times and capacities. Project three delivery months, execute only the current order, then replan using newly available information. Compare Fixed, Forecast-Aware (FA), scenario Risk-Neutral (RN) and Risk-Aware (RA) policies under identical external conditions and independent inventory states.

| Input | Contract | Output |
|---|---|---|
| Monthly Wheat US HRW observations | nominal USD/metric tonne; source/snapshot/publication metadata; as-of access | origin-local features and available history |
| Fixed model specifications | Seasonal Naive, SARIMAX, direct LightGBM; H1/H2/H3 | immutable forecasts, fit/issuance evidence, metrics |
| Mature OOF forecasts and observations | horizon calibration separate from complete-vector Joint maturity | statistical intervals, joint planning scenarios |
| Public inventory/pipeline, supplier and cost assumptions | no future actual prices/demand/delays | current orders, future plans, checked solver status |
| Evaluator-owned external world | isolated from policy; receipt-month settlement | receipts, stock, shortage, cost and fill-rate ledgers |

## Capabilities and evidence

The core MVP has five accepted requirements: monthly forecasts, rolling-origin backtesting, equal-condition two-policy comparison, traceability from source through cost, and saved-result verification. All five passed in the historical evidence package. Extensions preserve five additional policies, CVaR, operational sensitivity, provenance-aware sequential forecasting and Legacy restoration.

Historical Validation used real market prices with synthetic operations. Separate synthetic integration qualified software boundaries; it is not market validation. [Validation results](VALIDATION_RESULTS.md) report the unfavorable main result without retuning: better SARIMAX accuracy did not produce lower procurement cost.

## Product interfaces

Use named configuration roles in `configuration.CONFIG_FILES` and `load_spec(name, root)`. Core APIs are ordinary Python functions/classes:

- `data.availability.DevelopmentPriceStore`, `data.sequential.SequentialObservationStore`: released observations only.
- `features.price.build_features`, `forecasts` from `forecasting.seasonal_naive.predict` and the two model modules' `fit_predict` functions.
- `forecasting.publisher.NativeForecastPublisher`, `forecasting.legacy.LegacyReconstructedForecast` and `planning_points`: separate evidence types with a common numeric planning view.
- `uncertainty.horizon_sequential.HorizonSequentialOOF` and `provenance_sequential.ProvenanceSequentialOOF`: maturity-aware calibration/Joint lifecycles.
- `optimization.deterministic.solve_plan`, `scenario_lp.solve_risk_plan`, `policies.*` and `simulation.engine.run_simulation`.
- `evaluation.policy_backtest.run_historical_policy`, `sequential_runner.run_policy_calendar`: evaluation, state isolation and accounting.

These APIs do not grant data access. Safe executable checks are described in [Reproducibility](REPRODUCIBILITY.md). Actual Source/Seed Runtime remains NOT_VERIFIED; Final Holdout remains unevaluated and locked.

## Navigation

[Architecture](SYSTEM_ARCHITECTURE.md) · [Data/as-of](DATA_AND_ASOF_CONTRACT.md) · [Forecasts](FORECASTING_METHOD.md) · [Uncertainty](UNCERTAINTY_AND_SCENARIOS.md) · [Procurement](PROCUREMENT_OPTIMIZATION.md) · [Limitations](LIMITATIONS_AND_FUTURE_WORK.md) · [Migration and evidence](MIGRATION_AND_EVIDENCE.md).
