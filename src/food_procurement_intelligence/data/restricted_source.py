"""Pure restricted-export validation. No real source loader or permission issuer."""
from dataclasses import dataclass
from datetime import date,datetime
import csv
import hashlib
import io
import json
import math
from pathlib import Path

from food_procurement_intelligence.evaluation.splits import months_between,parse_month_label,decision_at,add_months

COLUMNS=('observation_month','price','unit','source_series','available_at','availability_basis','vintage_id')
BASIS='assumed_observation_month_plus_one_month_end'


class SourceAccessApprovalRequired(PermissionError):
    pass


@dataclass(frozen=True)
class RestrictedSourceContract:
    project_root: Path
    export_relative_path: str
    snapshot_identity: str
    documented_raw_sha256: str
    extraction_manifest_path: str
    extraction_manifest_sha256: str
    raw_manifest_reference: str
    source_identity: str = 'WorldBank_PinkSheet_Wheat_US_HRW'
    source_series: str = 'Wheat, US HRW'
    unit: str = 'USD_per_metric_tonne'

    def __post_init__(self):
        if (self.source_identity!='WorldBank_PinkSheet_Wheat_US_HRW' or self.source_series!='Wheat, US HRW'
            or self.unit!='USD_per_metric_tonne' or not self.snapshot_identity
            or any(len(h)!=64 or any(c not in '0123456789abcdef' for c in h) for h in (self.documented_raw_sha256,self.extraction_manifest_sha256))
            or not self.extraction_manifest_path.startswith('artifacts/day1/')
            or self.raw_manifest_reference!=f'data/raw/world_bank/{self.snapshot_identity}/manifest.json'):
            raise ValueError('Frozen World Bank HRW source reference required')
        self.permitted_path

    @property
    def permitted_path(self) -> Path:
        expected=(self.project_root/'data/approved_exports/final/wheat_history_through_202408.csv').resolve()
        p=(self.project_root/self.export_relative_path).resolve()
        if p!=expected:raise ValueError('Only the exact proposed restricted-export path is valid')
        return p

    def access_request(self) -> dict:
        return {'status':'ACCESS_APPROVAL_REQUIRED','proposed_path':str(self.permitted_path),
            'months':'1960-01..2024-08','unique_months':776,'columns':list(COLUMNS),
            'creation_method':'separately authorized non-Holdout-only export; no mixed801 file loading/rehash in this stage',
            'hashes_to_check':['restricted export SHA-256','export-generation manifest SHA-256','pinned Day1 extraction manifest SHA-256'],
            'documented_original_raw_sha256':self.documented_raw_sha256,'raw_hash_evidence':'DOCUMENTED_PREVIOUS_HASH',
            'bridge_holdout_access':False,'actual_source_authorized':False}


def require_real_source_verification(contract:RestrictedSourceContract) -> None:
    """Always deny before exists/open/hash; Day17 has no real access grant API."""
    raise SourceAccessApprovalRequired(json.dumps(contract.access_request(),ensure_ascii=False))


def validate_export_bytes(payload:bytes,manifest:dict,path:Path,contract:RestrictedSourceContract,*,expected_manifest_sha256:str) -> dict:
    """Validate supplied bytes only. The caller must obtain bytes under a separate authority.

    Day17 supplies synthetic fixtures only. Passing structural validation cannot
    assert historical vintage, actual release timestamps or real source access.
    """
    if path.resolve()!=contract.permitted_path:raise ValueError('Export path outside frozen scope')
    if hashlib.sha256(json.dumps(manifest,sort_keys=True,ensure_ascii=False).encode()).hexdigest()!=expected_manifest_sha256:
        raise ValueError('Unpinned export-generation manifest')
    reference={'extraction_manifest_path':contract.extraction_manifest_path,'extraction_manifest_sha256':contract.extraction_manifest_sha256,
        'raw_manifest_reference':contract.raw_manifest_reference,'raw_sha256':contract.documented_raw_sha256,'snapshot_identity':contract.snapshot_identity}
    if (manifest.get('source_identity')!=contract.source_identity or manifest.get('snapshot_identity')!=contract.snapshot_identity
        or manifest.get('source_reference')!=reference or manifest.get('unit')!=contract.unit
        or manifest.get('source_series')!=contract.source_series or manifest.get('columns')!=list(COLUMNS)
        or manifest.get('start')!='1960-01' or manifest.get('end')!='2024-08' or manifest.get('rows')!=776
        or manifest.get('generation_method')!='separate_nonholdout_export_no_mixed_load'
        or not manifest.get('generation_basis') or not manifest.get('generator_identity')
        or manifest.get('bridge_holdout_included') is not False
        or manifest.get('knowledge_type') not in ('synthetic_validator_fixture','restricted_official_snapshot_export')):
        raise ValueError('Export identity/provenance/column/calendar contract changed')
    stamp=datetime.fromisoformat(manifest['generated_at_utc'])
    if stamp.tzinfo is None or stamp.utcoffset() is None:raise ValueError('Generation timestamp must be aware')
    digest=hashlib.sha256(payload).hexdigest()
    if digest!=manifest.get('export_sha256'):raise ValueError('Export byte hash mismatch')
    reader=csv.DictReader(io.StringIO(payload.decode('utf-8')))
    if reader.fieldnames!=list(COLUMNS):raise ValueError('Unexpected/missing/duplicate/export columns')
    records=list(reader)
    expected=months_between(date(1960,1,1),date(2024,8,1))
    if len(records)!=776 or any(set(r)!=set(COLUMNS) or None in r.values() for r in records):raise ValueError('Expected exactly776 complete records')
    # Scope is validated before decoding a single numeric price.
    months=tuple(parse_month_label(r['observation_month']) for r in records)
    if len(set(months))!=776 or months!=expected:raise ValueError('Duplicate/missing/unsorted/out-of-scope month; no Bridge/Holdout')
    for r,m in zip(records,months):
        if (r['unit']!=contract.unit or r['source_series']!=contract.source_series or r['vintage_id']!=contract.snapshot_identity
            or r['availability_basis']!=BASIS):raise ValueError('Unit/series/vintage/availability identity mismatch')
        try:price=float(r['price'])
        except (ValueError,TypeError) as e:raise ValueError('Price must be numeric') from e
        if not math.isfinite(price) or price<=0:raise ValueError('Positive finite price required')
        available=datetime.fromisoformat(r['available_at'])
        if available.tzinfo is None or available.utcoffset() is None or available!=decision_at(add_months(m,1)):
            raise ValueError('Available-at deviates from frozen publication assumption')
    return {'structural_validation':'PASS','scope_months':776,'start':'1960-01','end':'2024-08','export_sha256':digest,
        'source_evidence_kind':manifest['knowledge_type'],'real_source_verification':'REAL_SOURCE_NOT_VERIFIED',
        'publication_evidence':'ASSUMED_PUBLICATION_TIME','historical_vintage':'NOT_VERIFIED',
        'actual_historical_release_timestamp':'NOT_VERIFIED','actual_access_granted':False,'source_files_opened':0}
