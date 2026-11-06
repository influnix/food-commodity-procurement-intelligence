# Data and as-of contract

## Official source and schema

The recorded source is [World Bank Commodity Markets](https://www.worldbank.org/en/research/commodity-markets), Pink Sheet Monthly Historical Commodity Prices. The recorded download was [CMO-Historical-Data-Monthly.xlsx](https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx), retrieved 2026-10-24T01:29:17.500704Z,586,099bytes; snapshot `20261024T012917500704Z_ea1c35082787`, SHA-256 `ea1c350827878ea3bbe30e3cda16a13fd3bd5b409b8458940dc94a36b5a33154`. These are historical metadata; this consolidation does not reopen or rehash source prices.

Workbook sheets are Mismatch Details(hidden), Monthly Prices, Monthly Indices, Description and Index Weights. Prices have headers in row5, units in row6, data rows7..807; dates are text such as `1960M01`, not Excel serial dates. The checked schema has71series. HRW is a US Gulf export reference, nominal USD/metric tonne; its801monthly observations span1960-01..2026-09 with no missing/duplicate/gap, according to the original audit. US SRW is separate,573valid observations from1979-01 and228initial missing months; Canada CWRS has a description but no price column. No series were averaged or filled.

The parser preserves `…`, `...`, `..` and empty values as explicit missing tokens and rejects unknown text/formulas/schema drift. The source header `($/mt)` is normalized to `USD_per_metric_tonne` without inflation or currency conversion. Monthly labels do not imply tradable month-start prices.

| Field | Meaning |
|---|---|
| `date` / `observation_month` | canonical first-of-month label of a monthly average |
| `price` | nullable numeric price in development extraction; actual/scenario prices must be finite and positive |
| `commodity`, `unit`, `source_series`, `source_unit` | normalized commodity/unit with the exact source identity retained |
| `raw_price`, `source_sheet`, `source_cell`, `is_missing` | original token/cell and missingness; no silent zero or interpolation |
| `available_at`, `availability_basis` | actual evidence if present, otherwise explicitly assumed next-month-end UTC |
| `vintage_id` | retrieved revised snapshot identity, not an invented historical first-release vintage |

## Source revision and definition risk

The recorded workbook update is October02,2026; HTTP Last-Modified, internal modified time, collection time and page first-publish date differ and do not establish each historical observation's first release. Workbook notes report2023/2024 SRW/phosphate revisions and grain formatting corrections. A current snapshot cannot reconstruct historical vintages.

HRW changes from no.1 through2020-06 to no.2 from2020-07. Retain all observations and the definition-boundary metadata. The audit does not prove a structural break or causal quality effect. Optional pre/post or boundary-crossing sensitivity remains separate; it was not used to remove price spikes. Seven development months crossed the predeclared20% absolute-change flag; values were preserved. Boundary crossing for a complete vector is `o−1 < 2020-07 ≤ o+3`, covering four origins2020-04..07, not an arbitrary wide embargo.

## Calendar and maturity

| Contract | Calendar |
|---|---|
| Train target labels |1960-01..2021-06; first Validation fit sees only through2021-05 |
| Validation origins |2021-06..2024-05,36origins×3horizons |
| Validation targets / procurement ledger |2021-07..2024-08,38unique months; Active35/Runoff3 |
| Bridge |2024-09, excluded from selection/scoring |
| Final planned origins |2024-09..2026-06,22origins |
| Final locked ledger |2024-10..2026-09,24months; Active21/Runoff3 |

At month-end decision `d_t`, the information set contains only `m≤t−1` and `available_at(m)≤d_t`. Delivery horizon `h=1,2,3` targets `t+h`, or model steps2,3,4 from latest observation. Complete-vector training requires:

```math
o<t,\qquad o+3\le t-1,\qquad \max_h available\_at(P_{o+h})\le d_t.
```

Thus `o≤t−4` is necessary but a late publication can require more exclusion. Static partition target sets must not overlap; fold training must not overlap the current fold's targets. Past validation labels may enter later expanding folds only after maturity under frozen specifications. No random split, full-sample preprocessing or unnecessary symmetric embargo is used. Validation horizons intentionally share target months and are dependent.

## Legacy and current-run evidence

The saved archive has192model-origin batches/576forecast records: Historical60(2016-04..2021-03)+Validation36 per model.558saved residuals and18already-issued forecast/target joins were audited previously. Unissued2024-06..08 forecasts must not be backfilled.

`LegacyReconstructedForecast` remains RECONSTRUCTED_ASOF, preserving original IDs/row/file/manifest/model/snapshot hashes. Historical live issuance, original native input-byte proof and session proof remain absent. `NativeIssuedForecast` requires actual current-run publisher registration and successful fit evidence. Native history hashes describe current in-memory inputs, not historical World Bank source bytes. Synthetic Legacy/Native qualification cannot be promoted into actual source verification.

## Actual access gate and distribution

The required separately supplied historical export is1960-01..2024-08,776months, exactly observation_month/price/unit/source_series/available_at/availability_basis/vintage_id. Proposed path: `data/approved_exports/final/wheat_history_through_202408.csv`. It needs explicit path/purpose/scope approval, CSV byte hash, original generation-manifest byte hash, canonical manifest content hash and independently supported creation/source linkage. The pure validator checks these contracts only on supplied bytes; it grants no access. Missing provenance is PROVENANCE_INCOMPLETE; missing approval is ACCESS_APPROVAL_REQUIRED. Do not read/filter/rehash the mixed801-month file to create it without separate authority.

Bridge/Holdout and actual fit/evaluation remain forbidden. Assumed maturity threshold2026-10-31T23:59:59Z is separate from actual historical release evidence and user permission. Source Export and real Seed Runtime remain NOT_VERIFIED.

The historical source record cited [World Bank terms](https://data.worldbank.org/summary-terms-of-use) and [licensing guidance](https://datacatalog.worldbank.org/public-licenses): CC BY4.0/default terms may have additional or third-party exceptions. This repository distributes code and selected aggregates, not source/derived price rows. No code license is chosen on the owner's behalf; no endorsement by World Bank is implied.
