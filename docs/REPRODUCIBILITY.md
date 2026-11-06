# Reproducibility and safe entrypoints

## Environment and installation

Use Python3.11 and an activated virtual environment. Existing versions are preserved in [runtime-lock.txt](../requirements/runtime-lock.txt); the narrower [forecasting lock](../requirements/forecasting-lock.txt) is retained for provenance. Python patch/OS timings differ; model/solver/package pins are unchanged. No local dependencies are installed during consolidation.

```sh
python -m venv .venv
# Activate the generated environment using your shell's standard activation command.
python -m pip install -r requirements/runtime-lock.txt
python -m pip install pytest==8.3.5
python -m pip install --no-deps -e .
python scripts/ci/run_contract_tests.py
python scripts/validation/run_synthetic_checks.py
python scripts/release/audit.py
```

CI verifies the installation in a clean Ubuntu22.04/Python3.11 checkout. Local clean-export checks use the existing environment and the exported source, without reading excluded market data or evidence. Installation downloads dependencies only, never World Bank/NASA inputs. The owner has not selected a code license; installation commands do not grant data rights or source access.

## Reproduction levels

| Level | Reproducible from checkout? | Meaning |
|---|---|---|
| A: Offline contract tests |Yes| the full previous330case CI scope, including parameterized cases, preserved under functional paths |
| B: Synthetic integration |Yes| six existing cases covering real seven-policy toy engine/LP execution, shared RN/RA scenarios, future price/demand/delay mutation, λ0/1 and non-anticipativity; a subset of A, not six new independent market experiments |
| C: Actual price analysis |No automatic execution| requires approved source-only export, provenance/manifest/hashes and explicit access/training scope |
| D: Full historical archive verification |No| original source/large artifacts are excluded; historical613passed is a past execution record, not current clean-checkout coverage |

The synthetic entrypoint calls existing regression tests and engine/solver implementations; it adds no estimator, world generator or experimental policy. It does not claim to repeat the historical22/24 Native fit qualification. Full-vector calibration compatibility and corrected horizon calibration remain separate contracts.

The runner explicitly lists cases in `configs/evaluation/ci.toml`, disables unrelated plugin autoload, blocks Python opens to checkout `data/` and `artifacts/`, and blocks socket connections. Temporary toy fixtures are permitted. Some negative tests intercept prohibited requests in an inner guard. This is a Python/API boundary, not OS/FD/C-extension isolation. No test is skipped or xfailed to pass CI.

The workflow uses `contents:read`, pinned official Actions commits and no persisted checkout credentials, project secrets, source downloads or artifact uploads. Its330case result must not be presented as the historical613case archive suite. The synthetic six are rerun to verify that the second documented command works.

## Named configurations and preserved contracts

`configuration.load_spec(name, root)` resolves source/quality/restricted_export, features/models, calibration/joint_and_operations/lifecycle, deterministic/risk, splits/validation/sensitivity/final/native_synthetic/handoff. Numeric hyperparameters, horizons, seeds, supplier/costs and calendars remain unchanged. Current config path pins are recalculated; original config bytes/hashes are recorded separately in the migration matrix. The combined Joint+operations file is retained because both original callers share it; separating its tables would add a new schema rather than clarify a name.

`configs/compatibility/initial_proposal.toml` is an explicitly unused initial proposal. Its old probability/risk assumptions do not replace the final fixed operating/risk contract. Compatibility utilities resolve historical identities through a small mapping; external users need no development-stage number.

## Historical evidence and Candidates

All210baseline tracked files are mapped from commit `874da83178ab15bc7f2a661fbba2b38b4875ab88`. Original documents/scripts/configs/tests remain in ordinary Git history and a local ignored snapshot; no force push or history rewrite. The previous path/hash Candidates are historical records requiring their original paths, archive and recorded code revisions. In particular the preceding release had already changed README relative to the older Candidate. Do not claim that the baseline commit alone supplies all candidate-pinned original bytes.

Current paths/hashes are separate evidence in [migration_matrix.json](../evidence/migration_matrix.json). The product release inventory, if present, is a new tree-integrity manifest, **not actual Holdout authorization**. `scripts/compatibility/` retains distinct old audit/freeze/replay contracts; use original revision plus its evidence for historical exact-pin validation. Running them against migrated source can correctly fail old pins; no assertions are weakened to turn that into success.

## Actual data and release gates

The official source and restricted776month export requirements are in [Data/as-of](DATA_AND_ASOF_CONTRACT.md). No approved Export is supplied and the mixed801month file must not be read to manufacture one. Actual Source/Seed Runtime remains NOT_VERIFIED and ACCESS_APPROVAL_REQUIRED. Real session issuance and actual evaluator capability remain disabled; no unlock CLI is supplied.

Future real execution requires separate source/adapter qualification, full regression, new eligible execution Candidate and explicit digest-bound single-evaluation permission, plus fresh actual-UTC maturity checking. Historical vintage and first release timestamps remain unverified even after an assumed calendar threshold. See [limitations](LIMITATIONS_AND_FUTURE_WORK.md) and the [Public checklist](PUBLIC_RELEASE_CHECKLIST.md).
