# Validation results

These are preserved development results, not a new experiment. Forecasts and procurement used real World Bank Validation prices; supplier/demand/inventory/cost assumptions were synthetic. Separate software integration used a synthetic price world. Actual Holdout results do not exist.

## Forecasts and MVP acceptance

Validation:36origins2021-06..2024-05,108origin-horizon keys/model,38unique target months2021-07..2024-08. All point models had complete108key coverage with no forecast failure.

| Model | MAE USD/t | Fold-as-of MASE | MAE improvement vs Seasonal Naive |
|---|---:|---:|---:|
| Seasonal Naive12 |100.0296|3.2300|—|
| SARIMAX |41.8757|1.3624|58.1367%|
| LightGBM Direct |48.6620|1.5912|51.3524%|

SARIMAX H1/H2/H3 MAE:31.9368/43.4305/50.2599; LightGBM:41.9029/48.2184/55.8647. Fold-as-of MASE uses past seasonal scales and is not the same as baseline-relative improvement. Targets overlap, so108errors are not108independent months.

The five MVP requirements passed: monthly forecasting; rolling-origin backtesting; equal-condition representative two-policy comparison; source→forecast→order→receipt→cost traceability; stored-result reproducibility verification. The [aggregate evidence](../evidence/portfolio_summary.json) retains these results and original source-summary hashes. Full forecasts/ledgers/source data remain excluded local evidence.

## Representative procurement comparison

| Metric | Fixed | FA SARIMAX |
|---|---:|---:|
| Total Simulated Cost USD |1,351,501.68|1,365,914.16|
| Purchase USD |1,336,441.68|1,328,834.16|
| Holding USD |13,260.00|5,280.00|
| Shortage USD |0|30,000.00|
| Terminal USD |1,800.00|1,800.00|
| Transport / disposal USD |0 /0|0 /0|
| Fill Rate |100%|99.4737%|
| Shortage t |0|20|
| Mean month-end stock t |116.3158|46.3158|

FA costs **14,412.48USD(+1.0664%) more**. Purchase−7,607.52 and holding−7,980 are outweighed by shortage+30,000. Active35months saves38,415.36, but Runoff3months adds52,827.84. At the last decision, FA has stock20+pipeline80+maximum current orders180=280t against300t remaining demand. Its stored OPTIMAL plan already shows20t final shortage. This is an accounting/physical-state diagnosis, not proof that forecast error alone caused the outcome.

**Better price forecasting does not automatically translate into lower procurement costs.** Lead times, stock, capacity, Runoff and service penalties matter.

## Seven-policy extension

| Policy | Total Simulated Cost USD | Fill Rate | Shortage t | Difference vs Fixed USD |
|---|---:|---:|---:|---:|
| Fixed |1,351,501.68|100%|0|0|
| FA SARIMAX |1,365,914.16|99.4737%|20|+14,412.48|
| RN SARIMAX |1,352,495.76|100%|0|+994.08|
| RA SARIMAX |1,350,903.84|100%|0|−597.84|
| FA LightGBM |1,333,962.24|100%|0|−17,539.44|
| RN LightGBM |1,333,962.24|100%|0|−17,539.44|
| RA LightGBM |1,348,234.20|100%|0|−3,267.48|

On the same scenarios, RA−RN is−1,591.92USD for SARIMAX but+14,271.96 for LightGBM; both have zero shortage. RN/RA stock increases111.0526→115.7895t(SAR) and52.6316→98.3630t(LGB). The first-state planned E/CVaR is34,457.74/40,270.07→34,461.47/39,774.22 for SAR and35,650.01/42,846.71→35,696.47/42,073.71 for LGB. Lower planned tail can cost more in expectation and does not establish realized long-run market CVaR. FA-to-RA also changes point/scenario inputs, so it is not a pure CVaR effect.

All seven historical policies completed;216optimization decisions were checked OPTIMAL, with no missing forecast/scenario, solver failure or fallback. Validation-only Active performance must not be detached from inherited Runoff states. Failure tests stop full comparisons and preserve a conservative confirmed prefix; they do not fabricate missing partial ledgers.

## Operational sensitivity

The11completed cells are baseline+8OAT+2stress. Another three horizon/lag requests were audited as unsupported, not omitted successful runs. The table is a preserved aggregate diagnostic on one shared price path, not eleven independent market trials.

| Cell | Fixed | FA S | RN S | RA S | FA L | RN L | RA L |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline |1,351,501.68|1,365,914.16|1,352,495.76|1,350,903.84|1,333,962.24|1,333,962.24|1,348,234.20|
| initial inventory100 |1,490,401.68|1,401,831.12|1,388,412.72|1,383,280.56|1,366,338.96|1,366,338.96|1,381,240.44|
| initial inventory300 |1,362,001.68|1,331,836.08|1,318,775.04|1,318,307.76|1,301,366.16|1,301,366.16|1,316,449.80|
| shortage penalty750 |1,351,501.68|1,350,914.16|1,352,495.76|1,350,903.84|1,333,962.24|1,333,962.24|1,348,234.20|
| shortage penalty3000 |1,351,501.68|1,395,914.16|1,352,495.76|1,350,903.84|1,333,962.24|1,333,962.24|1,348,234.20|
| terminal weight0 |1,349,701.68|1,364,114.16|1,350,695.76|1,349,103.84|1,332,162.24|1,332,162.24|1,346,434.20|
| terminal weight30 |1,355,701.68|1,370,114.16|1,356,695.76|1,355,103.84|1,338,162.24|1,338,162.24|1,352,434.20|
| holding6 |1,364,761.68|1,369,018.32|1,359,098.64|1,364,012.68|1,339,487.28|1,339,962.24|1,353,786.52|
| B capacity60 |1,351,501.68|1,368,834.72|1,352,971.44|1,350,903.84|1,340,646.72|1,340,646.72|1,347,241.40|
| demand120stress |1,436,101.68|1,395,371.52|1,381,953.12|1,380,361.20|1,363,419.60|1,363,419.60|1,379,947.26|
| A delay1stress |1,348,602.96|1,465,295.28|1,349,597.04|1,348,005.12|1,433,343.36|1,433,343.36|1,381,982.20|

S=SARIMAX,L=LightGBM. Initial-inventory costs are sunk; different initial-stock cell totals are not policy savings. Demand120 in2022-01..03 and A cohort delay1 for the same order months were evaluator-only; planned demand100/nominal delay0 stayed fixed. Horizon2/6 and publication lag2 are unsupported under the frozen3horizon/lag1 contracts; no H4..6 or relabeled forecasts were invented.

No policy wins every cell; LGB FA/RN advantages are sensitive to low stock/A delay, while the tiny SAR RA–Fixed difference is often a near tie and RA–RN ordering can reverse with holding cost. These post-hoc diagnostics did not select new defaults. Coverage/tail probabilities, revisions, synthetic operations and [other limitations](LIMITATIONS_AND_FUTURE_WORK.md) remain.
