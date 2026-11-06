# Uncertainty and scenarios

## Raw forecasts and validity

SARIMAX produces its native central80% interval and Gaussian q10/q50/q90; LightGBM uses fixed direct quantile objectives at.1/.5/.9 with the existing features/specification. The L2 point remains distinct from q50. Raw crossing is recorded, never sorted away or clipped.

The common validator requires numeric Real values excluding bool, positive finite points, finite ordered intervals and aligned q10≤q50≤q90/endpoints. Nonfinite quantiles cannot be hidden by moving them into base fields. Finite zero/negative statistical bounds remain flagged NONPOSITIVE_BOUND_REVIEW; actual and scenario prices must stay strictly positive. Invalid intervals are excluded from score calibration, while a valid positive point can still contribute to Joint vectors after full maturity.

## Horizon-wise calibration

For each model/horizon/raw method separately, use only previously issued and now-published residuals. A forecast at origin o releases h when `o+h≤t−1` and actual_available_at≤d_t. Select the most recent60eligible scores; minimum24:

```math
s_i=\max(L_i-y_i,\ y_i-U_i,\ 0),\qquad
k=\lceil(n+1)\times0.8\rceil,\qquad
[L',U']=[L-s_{(k)},U+s_{(k)}].
```

There is no interpolation. These are expanded interval endpoints, not newly identified q10/q90; corrected q fields are null and original base quantiles are retained. Pinball loss for these interval-only endpoints is NA. Insufficient pool explicitly retains a valid raw interval with `insufficient_raw_fallback`; raw invalid gives `raw_invalid_uncalibrated`. This declared statistical status is separate from solver/policy fallback, which is absent.

The earlier full-vector calibration contract remains in the compatibility lifecycle. The corrected `HorizonSequentialOOF` releases each horizon independently; late H3 does not block mature H1/H2. The archived sixteen counterexample cases/four prior interval/fallback differences and common raw-validity remediation are preserved in historical mapping, not relabeled as the same original method.

## Full-vector Joint scenarios

Joint still requires all three targets and timestamps to mature: o+3≤t−1. Use the most recent60complete, source/fit/issuance-verified vectors per model, at least24. One draw samples one past origin and uses its entire h1/h2/h3 ratio vector:

```math
P^*_{t,h}=\hat P_{t,h}\frac{P_{o+h}}{\hat P_{o,h}},\qquad h=1,2,3.
```

Generate128equally weighted paths. An additive version using the same draws is diagnostic only. Positive actual/point requirements are checked; invalid values cause failure without clipping or resampling. Quantile triples alone are not event probabilities or a joint distribution.

Planning seed2026102901 and evaluation seed2026102902 derive local RNG seeds by origin/model/purpose SHA. Explicit fresh RNGs and fixed external worlds prevent policy call order from consuming different paths. Scenario IDs carry purpose/model/origin/draw. Within-vector dependence is preserved; temporal dependence across sampled origins or consecutive decision months is not guaranteed. Different seeds sampling the same pool are not independent market/OOS evaluations.

RN and RA for the same model consume identical immutable Planning sets. Policies reject Evaluation-purpose, wrong-origin/model and unavailable pools. No future realized path is passed through a scenario adapter.

## Legacy restoration and current Native transition

Restore exactly192Legacy batches from an external archive digest before session clock advancement; validate the entire archive before mutation. The first2024-09 decision can logically mature all saved seed targets under the publication assumption. Do not fill the2024-06..08 issuance gap. New issuance must come from the current Native publisher and successful fit events; original Legacy hashes/values/grade remain unchanged.

Historical synthetic qualification checked44fresh Native batches/286fit events,132calibration rows and44×128=5632Joint paths. Revised lineage changes pool/planning digests but not sampled origins, seeds, ratios or prices; these distinctions were explicitly verified. It did not qualify actual World Bank Runtime.

## Observed coverage limitations

Nominal80% intervals undercovered on Validation: SARIMAX raw48.15%/width60.9970, calibrated61.11%/84.4602; LGB raw58.33%/164.6295, calibrated65.74%/193.9608 USD/t. No window, model or risk coefficient was tuned to hide this. Overlapping targets, expanding fits and time dependence prevent an exchangeability guarantee. Current interval invalidity, fit failure, Joint unavailability and source provenance failure remain distinct states.
