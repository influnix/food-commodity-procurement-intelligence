# Migration and evidence integrity

Baseline: commit `874da83178ab15bc7f2a661fbba2b38b4875ab88`,210tracked files,PRIVATE main,330clean-checkout CI cases. Product consolidation uses normal history-preserving moves/commits, no force push, no source access, no new estimator/experiment.

## Structure decisions

| Before | Product role / after |
|---|---|
| flat numbered TOMLs | named data/forecasting/scenarios/procurement/evaluation specs |
| numbered evaluation modules | scenario_diagnostics, deterministic_backtest, scenario_backtest, historical_backtest, sensitivity_runner, preflight_runner, native_integration |
| numbered test modules | unit/integration/regression/safety functional names; all original cases retained |
| flat/numbered verifiers | scripts/validation functional independent verifiers |
| multiple historical audit/freeze/replay tools | scripts/compatibility, distinct evidence contracts retained rather than merged |
| chronological state/spec documents | nine conceptual product guides plus this mapping and the Public checklist |

No model, LP or inventory algorithm is rewritten. Domain packages already fit the architecture and are retained. The repeated audit/freeze wrappers are not merged because their Candidate schemas, numerical lifecycle and evidence grades differ. Compatibility routines may legitimately reject moved/current files against historical pins. They require original code revision and excluded evidence, not just a renamed file.

For49AST-identical source files, original bytes are restored as well, avoiding an unnecessary line-ending-only diff. Immutable identifiers such as `synthetic_day12_not_world_bank` and historical artifact paths remain protocol/provenance identities. They are not user-facing stage-based commands; renaming them would alter saved evidence or source/seed matching. Current file/config/API navigation uses functional names.

The configuration split is intentionally conservative: Joint/scenario and operating tables remain one shared original schema under `scenarios/joint_and_operations.toml`, since both original consumers use it. Model features and model fitting remain separate. Validation36/38and final locked22/24calendars remain distinct. An unused proposal is explicitly placed under configs/compatibility and never silently overrides final assumptions.

## Full file and test correspondence

[migration_matrix.json](../evidence/migration_matrix.json) maps **every one of the210baseline files**, category A..G, action, destination, before/after hash and rationale. It records original locations rather than pretending old hashes identify new bytes. Categories are core implementation, method/configuration, tests, evaluator documentation, historical development record, archive-only evidence and unresolved removal candidate. No file is deleted on an unverified assumption of non-use.

[test_migration.json](../evidence/test_migration.json) records old/new parametrized node IDs for the330CI cases. Changes to file roots, configuration fixture parents and descriptive test names preserve input values/assertion meaning. No arbitrary skip/xfail, deleted important case or reduced CI selection is used. Additional archive-dependent modules remain under functional regression/safety/integration paths; their historical613passed record is not asserted as a fresh full-suite pass.

[document_sources.json](../evidence/document_sources.json) maps every original tracked document and its sections/hash to the conceptual guides. Progress-only status dates, historical execution commands and old environment installation incidents remain historical records rather than duplicated current instructions. Important source/availability assumptions, model/LP/CVaR equations, counterexamples, failure states, coverage and adverse cost results are incorporated into the product guides.

## Preserve original evidence, not authority

Original tracked bytes are retained in Git history and an ignored local baseline snapshot. Existing raw/processed/approved data and all original large artifacts are untouched and excluded. Original untracked historical documents also remain local; they are not newly uploaded.

Historical Candidate files are not edited. The recorded Candidate SHA `8074d87ea324bb6d6ea6e4995f481a29317f4f9ba766f89ee132d7f1945c4f11` is preserved as past synthetic/saved-evidence qualification. The prior release already had a declared README pin change; original pin checks therefore require the appropriate pre-change source records as well as evidence. Moved paths and hashes are not silently substituted into that Candidate.

A product release manifest is a separate tree-integrity inventory with code/config/document hashes, baseline/test mappings and explicit actual-execution=false. It is not a new historical issuance proof or Holdout permission. Source metadata hashes, current config path pins, archived model/run hashes and new release hashes have different meanings.

## Verification scope

Compare330collected cases one-to-one; run the complete selected suite in an export containing only the release allowlist; run the six-case documented synthetic entrypoint; import the product modules; inspect config semantic values and algorithm ASTs; validate all local Markdown links; scan exact tracked content and reachable Git history. Remote CI must succeed on the same main SHA before closure. Detailed local migration QA remains excluded execution metadata; the published mappings contain only code/config/aggregate provenance, not market-price rows.
