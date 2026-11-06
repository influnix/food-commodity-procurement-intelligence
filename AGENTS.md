# Repository instructions

## Scope and changes

Perform only the user's authorized work. Use this root and pathlib/project-relative paths. Preserve existing results and normal Git history. No force push, public transition, repository deletion, source downloads, large dependency installation or global environment changes without explicit authorization. This product consolidation authorizes normal commits/push to the existing PRIVATE repository; it does not authorize actual source/Bridge/Holdout access, fit, evaluation or unlock.

Do not add models, tuning, scenarios, UI or frameworks during consolidation. Algorithm and test behavior must be preserved; record path/symbol/config/document mappings. Keep old Candidate bytes and old records unchanged in Git history/local ignored archives. Never reuse an old path-based Candidate as current execution approval. Exact historical verification needs the recorded code/paths and evidence; do not weaken assertions to accept migrated files.

## Data and as-of information

Follow docs/DATA_AND_ASOF_CONTRACT.md and configs/evaluation/splits.toml. At month-end t, require observation_month<=t-1 AND available_at<=decision_at. Preserve observation_month, available_at, availability_basis and vintage_id. Latest revised snapshots are not historical first-release vintages; absent evidence stays NOT_VERIFIED. The2020-07 grade boundary is metadata, not a proven structural break.

Use guarded as-of stores. Never pass evaluator price readers or future actual market prices, weather, demand or delays to feature/model/policy functions. Historical-origin lag/rolling features use that origin's available history. Any future scaler/imputer/feature selection must fit within the fold TrainingBatch of mature targets and past-origin features. Complete H1/H2/H3 labels require origin+3<=evaluation_origin-1 plus all publication timestamps. No random split, full-sample preprocessing or unissued forecast backfill.

Validation labels belong to the evaluator after forecasts are generated. Fold MASE scales use available history. Development API keeps Bridge/Holdout locked. Source/Seed Runtime remains NOT_VERIFIED and ACCESS_APPROVAL_REQUIRED. Current real SessionPermit and actual execution capability remain disabled. Clock maturity or synthetic readiness is not permission. Final real evaluation would require separately qualified source/adapter, new eligible freeze and explicit digest/role/calendar-bound single-run approval.

## Frozen models, uncertainty and optimization

Preserve configs/forecasting/models.toml and features.toml, H1/H2/H3, model steps2/3/4, no tuning/early stopping/hidden model fallback. Calibration uses per-model/horizon/method mature scores, recent60/min24 and fixed finite rank. Keep corrected HorizonSequentialOOF and older full-vector calibration compatibility distinct. Crossing/nonfinite invalidity and statistical nonpositive bounds retain explicit states; do not sort, clip or mislabel expanded bounds as q10/q90.

Joint needs all three published targets, recent60/min24 complete OOF ratio vectors,128joint paths, fixed per-origin/model/purpose seeds. Evaluation scenarios are forbidden to policies. Same-pool resampling is not independent OOS. Separate Legacy RECONSTRUCTED_ASOF and current-run NATIVE_ISSUED; do not fabricate missing history/session/live proof.

Preserve GLOP formulations, alpha.90/lambda0,.50, all current/future orders and physical flows shared across price scenarios, current q only and receding reoptimization. Existing pipeline is constant, receipt-month prices apply once, planning W=0 is conservative. Require OPTIMAL plus VerifySolution, physical/greedy/scenario-cost/CVaR/objective checks; FEASIBLE is not optimal and there is no hidden policy fallback. Discrete CVaR includes fractional boundary mass; lambda0 raw epigraph is distinct from independently computed CVaR.

## Simulation and evaluation

Keep seven policies, common external paths, independent states, I200/empty comparison pipeline, original suppliers/costs. Validation36decisions/38ledger months/Active35/Runoff3 differs from locked final22/24/21/3. No new q/provider calls in Runoff; terminal cost once at global end and final pipeline empty. Do not accumulate monthly planning terminal charges. Toy-only opening pipeline remains separate. Failed policies/cells must not be ranked using favorable partial successes or fabricated ledgers.

Synthetic fixtures are explicitly toy, never fabricated actual prices. Keep seed/config/version/units; pass RNGs explicitly and fix external paths before policies. Raw data stays immutable and untracked; all data/artifacts remain excluded from Git. Selected aggregates may be published only after content/rights review. Do not describe simulated outcomes as company savings or causal effects.

## Verification and release

Python3.11+, src layout, type hints, explicit settings and short functions. No assertion weakening, arbitrary skip/xfail or CI scope reduction. configs/evaluation/ci.toml preserves330original contract cases and a six-case synthetic subset. Historical613passed needs excluded archive; do not claim it as clean CI. Run appropriate tests and report actual counts/failures. Core invariants include future-data blocking, split boundaries, inventory conservation, lead times, costs/units, solver status and shared external paths.

Use explicit configs/evaluation/release_allowlist.toml; never git add . . Scan tracked content and all reachable history, no secrets/personal paths/source prices. Keep repository PRIVATE and license owner-selected. See docs/REPRODUCIBILITY.md, docs/MIGRATION_AND_EVIDENCE.md and docs/PUBLIC_RELEASE_CHECKLIST.md. scripts/compatibility retains historical evidence-specific contracts; missing archive or stale pins fail rather than silently succeed.
