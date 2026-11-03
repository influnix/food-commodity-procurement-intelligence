"""Legacy format construction from authorized artifacts and an explicit synthetic fixture."""
import csv
import json
from datetime import date

from helpers import ROOT,D12,cfg,read,sha,no_data_access,load_saved_batches,source_contract
from seed_audit import audit as day16_seed_audit
from food_procurement_intelligence.data.sequential import canonical_hash
from food_procurement_intelligence.evaluation.splits import load_split_plans
from food_procurement_intelligence.forecasting.legacy import LegacyReconstructedForecast,legacy_from_saved_rows,validate_legacy_archive,planning_points


def models():return {k:cfg(4)[k]['model_name'] for k in ('sarimax','lightgbm')}
def model_hashes():return {k:canonical_hash(cfg(4)[k]) for k in ('sarimax','lightgbm')}


def actual_legacy_evidence():
    """Saved non-Holdout evidence only. No actual observation store, fit or scenarios."""
    with no_data_access(ROOT) as access:
        audited=day16_seed_audit();previous=read(ROOT/'artifacts/day16/seed_audit_canonical.json')
        if audited!=previous:raise ValueError('Day16 saved evidence audit changed')
        directory=ROOT/cfg(5)['report_root']/'20261029T004616487272Z'
        manifest=read(directory/'manifest.json');path=directory/'all_oof_forecasts.csv'
        if sha(path)!=manifest['output_sha256'][path.name]:raise ValueError('Saved forecast byte hash changed')
        with path.open(encoding='utf-8',newline='') as f:rows=list(csv.DictReader(f))
        contract=source_contract()
        batches=legacy_from_saved_rows(rows,source_file_sha256=sha(path),manifest_sha256=sha(directory/'manifest.json'),
            model_specs=model_hashes(),models=models(),snapshot_identity=contract.snapshot_identity,source_identity=contract.source_identity,
            source_kind='world_bank_saved_reconstructed',source_file_path=path.relative_to(ROOT).as_posix(),manifest_path=(directory/'manifest.json').relative_to(ROOT).as_posix())
        digest=canonical_hash([b.record() for b in batches]);proof=validate_legacy_archive(batches,cfg(5),load_split_plans(ROOT/'configs/splits.toml')[0],models(),digest)
        assert all(len(planning_points(b))==3 for b in batches)
        return batches,{'contract':proof,'archive_sha256_derived_today':digest,'saved_residuals_verified':558,
            'already_issued_forecasts_joined_to_saved_actuals':18,'real_source_export_verified':False,
            'real_seed_runtime_verified':'NOT_VERIFIED','actual_source_open_or_fit':False,'source_access':access,
            'evidence_level':'RECONSTRUCTED_ASOF','historical_live_issuance':'NOT_VERIFIED','native_envelope_fabricated':False}


def synthetic_legacy_archive():
    """Project existing synthetic raw forecasts into the Legacy schema as a format fixture.

    No new warmup predictions or missing calendar origins are generated. The
    original synthetic native envelope stays in its immutable Day12 artifact;
    this lower-evidence fixture explicitly carries no native session/input proof.
    """
    batches=load_saved_batches();result=[];manifest_path=D12/'run_manifest.json'
    for (label,o),b in sorted(batches.items()):
        if o>=date(2024,9,1):continue
        path=D12/'issuances'/f'{o:%Y-%m}_{label}.json'
        result.append(LegacyReconstructedForecast(o,label,b.raw,tuple(p.record()['record_id'] for p in b.raw),
            tuple(canonical_hash(p.record()) for p in b.raw),sha(path),sha(manifest_path),model_hashes()[label],
            'SYNTHETIC_DAY12_V1','DAY12_AR_INCREMENTS_SEED20261030','synthetic_legacy_fixture',
            path.relative_to(ROOT).as_posix(),manifest_path.relative_to(ROOT).as_posix()))
    result=tuple(result);digest=canonical_hash([b.record() for b in result])
    validate_legacy_archive(result,cfg(5),load_split_plans(ROOT/'configs/splits.toml')[0],models(),digest)
    return result,digest
