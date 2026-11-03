"""Day17 metadata/evidence utilities; never opens a real source price file."""
from pathlib import Path
import sys
import csv
import io
import hashlib
import json
from datetime import date

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/day16'))
from support import cfg,read,save,zipped,sha,no_data_access,D12,load_saved_batches,archived_day13_release
from food_procurement_intelligence.data.restricted_source import RestrictedSourceContract,COLUMNS,BASIS
from food_procurement_intelligence.evaluation.splits import months_between,add_months,decision_at


def source_contract():
    p=ROOT/cfg(2)['day1_manifest'];m=read(p)
    if sha(p)!=cfg(2)['day1_manifest_sha256']:raise ValueError('Day1 extraction metadata pin mismatch')
    return RestrictedSourceContract(ROOT,cfg(17)['proposed_export'],m['raw_snapshot_id'],m['raw_sha256'],
        p.relative_to(ROOT).as_posix(),sha(p),m['raw_manifest'])


def validator_fixture():
    """776-month schema fixture only, never used as a procurement experiment world."""
    c=source_contract();s=io.StringIO(newline='');w=csv.DictWriter(s,fieldnames=COLUMNS);w.writeheader()
    for i,m in enumerate(months_between(date(1960,1,1),date(2024,8,1))):
        w.writerow({'observation_month':f'{m:%Y-%m}','price':100+i/100,'unit':c.unit,'source_series':c.source_series,
            'available_at':decision_at(add_months(m,1)).isoformat(),'availability_basis':BASIS,'vintage_id':c.snapshot_identity})
    payload=s.getvalue().encode();manifest={'source_identity':c.source_identity,'snapshot_identity':c.snapshot_identity,
        'source_reference':{'extraction_manifest_path':c.extraction_manifest_path,'extraction_manifest_sha256':c.extraction_manifest_sha256,
            'raw_manifest_reference':c.raw_manifest_reference,'raw_sha256':c.documented_raw_sha256,'snapshot_identity':c.snapshot_identity},
        'unit':c.unit,'source_series':c.source_series,'columns':list(COLUMNS),'start':'1960-01','end':'2024-08','rows':776,
        'generation_method':'separate_nonholdout_export_no_mixed_load','generation_basis':'SYNTHETIC SCHEMA FIXTURE; no real file export; never an authorization',
        'generator_identity':'day17_validator_fixture_v1','bridge_holdout_included':False,'knowledge_type':'synthetic_validator_fixture',
        'generated_at_utc':'2026-11-01T00:00:00+00:00','export_sha256':hashlib.sha256(payload).hexdigest()}
    return c,payload,manifest


def manifest_hash(m):return hashlib.sha256(json.dumps(m,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def access_specification():
    c=source_contract();request=c.access_request()
    seed=read(ROOT/'artifacts/day16/seed_audit_canonical.json')
    request.update({'original_mixed_source_path':seed['source']['processed_source']['path'],
        'recorded_mixed_csv_sha256_not_rehashed':seed['source']['processed_source']['sha256'],
        'source_creation_method_required':'owner-supplied separately authorized restricted export with generation manifest; this stage does not read/filter the mixed801 file',
        'export_expected_sha256':None,'export_manifest_expected_sha256':None,
        'missing_hash_policy':'must be supplied/pinned under separate approval; no invented hashes',
        'actual_source_status':'REAL_SOURCE_NOT_VERIFIED'})
    return request


def preservation():
    b=read(ROOT/'artifacts/day17/preservation_before.json');changed=[]
    for name,h in b['files'].items():
        p=ROOT/name
        if not p.is_file() or sha(p)!=h:changed.append(name)
    for name,s in b['data_stat_only'].items():
        p=ROOT/name
        if not p.is_file() or p.stat().st_size!=s['size'] or p.stat().st_mtime_ns!=s['mtime_ns']:changed.append(name)
    return {'passed':not changed,'prior_file_hashes_checked':len(b['files']),'data_metadata_only':len(b['data_stat_only']),
        'changed_existing_files':changed,'real_source_bytes_opened_or_rehashed':False}
