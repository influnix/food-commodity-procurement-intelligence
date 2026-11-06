"""Independent Legacy/Native provenance, as-of arithmetic and synthetic accounting."""

import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_bootstrap_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
_bootstrap_sys.path.insert(0, str(_bootstrap_root))
import argparse
import csv
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from random import Random
import sys

from scripts.compatibility.legacy_support import ROOT,D12,read,save,sha,no_data_access,preservation
sys.path.insert(0,str(ROOT/'scripts'))
from scripts.validation.verify_native_integration import verify_calendar


def idx(m):y,n=map(int,m.split('-'));return y*12+n-1
def month(i):return f'{i//12:04d}-{i%12+1:02d}'
def stamp(m):
    from calendar import monthrange
    y,n=map(int,m.split('-'));return f'{m}-{monthrange(y,n)[1]:02d}T23:59:59+00:00'
def digest_body(v):return hashlib.sha256(json.dumps(v,sort_keys=True,default=str,allow_nan=False).encode()).hexdigest()
def raw_valid(p):return p['point_prediction']>0 and p['q10']<=p['q50']<=p['q90'] and p['lower_bound']==p['q10'] and p['upper_bound']==p['q90']


def verify(bundle:Path,repeat:Path|None=None):
    with no_data_access(ROOT) as access:
        manifest=read(bundle/'run_manifest.json');assert manifest['complete']
        for name,h in manifest['outputs'].items():assert sha(bundle/name)==h
        for name,h in manifest['code_at_start'].items():assert sha(ROOT/name)==h
        actual=read(bundle/'saved_legacy_archive.json.gz');legacy=read(bundle/'synthetic_legacy_archive.json.gz')
        assert len(actual)==len(legacy)==192
        for archive in (actual,legacy):
            assert sum(len(b['raw']) for b in archive)==576
            assert {b['knowledge_type'] for b in archive}=={'RECONSTRUCTED_ASOF'}
            assert all(b['historical_issuance_evidence_level']=='NOT_VERIFIED' and b['native_session_proof'] is None and b['original_input_byte_proof'] is None for b in archive)
            for b in archive:
                assert [p['horizon'] for p in b['raw']]==[1,2,3]
                assert b['origin']<'2024-06' and all(p['point_prediction']>0 and math.isfinite(p['point_prediction']) for p in b['raw'])
        # Original actual saved forecast values/IDs are preserved without source-price reads.
        d5=ROOT/'artifacts/day5/20261029T004616487272Z';m=read(d5/'manifest.json')
        assert sha(d5/'all_oof_forecasts.csv')==m['output_sha256']['all_oof_forecasts.csv']
        with (d5/'all_oof_forecasts.csv').open(encoding='utf-8',newline='') as f:rows=list(csv.DictReader(f))
        originals={(r['model_name'],r['forecast_origin'],int(r['horizon'])):r for r in rows};assert len(originals)==576
        for b in actual:
            assert b['source_kind']=='world_bank_saved_reconstructed' and b['source_file_sha256']==m['output_sha256']['all_oof_forecasts.csv']
            for i,p in enumerate(b['raw']):
                r=originals[p['model_name'],p['forecast_origin'],p['horizon']]
                assert b['original_record_ids'][i]==r['record_id']
                assert b['original_row_hashes'][i]==digest_body(r)
                for field in ('point_prediction','q10','q50','q90','lower_bound','upper_bound'):assert p[field]==float(r[field])
        observations=read(bundle/'synthetic_observations.json');prices={r['observation_month']:r['price'] for r in observations}
        assert all(r['knowledge_type']=='synthetic_day12_not_world_bank' for r in observations)
        raw={};provenance={}
        for b in legacy:
            key=b['raw'][0]['model_name'],b['origin'];provenance[key]='RECONSTRUCTED_ASOF'
            for p in b['raw']:raw[p['model_name'],p['forecast_origin'],p['horizon']]=p
        events=[];native=[]
        for path in sorted((bundle/'native_issuances').glob('*.json')):
            b=read(path);body={k:v for k,v in b.items() if k!='issued_sha256'}
            assert digest_body(body)==b['issued_sha256']
            assert b['knowledge_type']=='synthetic_day12_not_world_bank' and b['backend_kind']=='native_statsmodels_lightgbm'
            assert '2024-09'<=b['origin']<='2026-06'
            proof=b['proof'];assert proof['source_session']=='DAY17_SYNTHETIC_NATIVE_TRANSITION_V1'
            assert idx(proof['training_origin_end'])<=idx(b['origin'])-4 and idx(proof['last_complete_training_target'])<=idx(b['origin'])-1
            assert proof['max_training_available_at']<=stamp(b['origin']) and proof['target_unobserved_at_issue']
            assert len(b['events'])==(1 if b['label']=='sarimax' else 12) and all(e['status']=='success' for e in b['events'])
            events.extend(b['events']);native.append(b);provenance[b['raw'][0]['model_name'],b['origin']]='NATIVE_ISSUED'
            for p in b['raw']:raw[p['model_name'],p['forecast_origin'],p['horizon']]=p
        assert len(native)==44 and len(events)==286 and len(raw)==708
        lineage=read(bundle/'lineage.json.gz');assert len(lineage)==236
        assert all(r['evidence_level']==provenance[r['model'],r['origin']] for r in lineage)
        assert all(r['native_session'] is None for r in lineage if r['evidence_level']=='RECONSTRUCTED_ASOF')
        corrected=read(bundle/'calibrated.json.gz');audits=read(bundle/'calibration_audit.json.gz');assert len(corrected)==len(audits)==132
        for out,a in zip(corrected,audits):
            o,m,h=out['forecast_origin'],out['model_name'],out['horizon'];selected=[]
            for (model,past,j),p in raw.items():
                if model!=m or j!=h or past>=o or idx(p['target_month'])>idx(o)-1 or not raw_valid(p):continue
                target=p['target_month'];available=stamp(month(idx(target)+1))
                if available>stamp(o):continue
                selected.append((target,past,max(p['lower_bound']-prices[target],prices[target]-p['upper_bound'],0.)))
            selected=sorted(selected)[-60:];n=len(selected);rank=math.ceil((n+1)*.8)
            adjustment=sorted(v[2] for v in selected)[rank-1] if n>=24 and rank<=n else None
            current=raw[m,o,h];status='calibrated' if adjustment is not None else 'insufficient_raw_fallback'
            if not raw_valid(current):status='raw_invalid_uncalibrated';adjustment=None
            assert a['count']==n and a['rank']==rank and a['selected_source_origins']==[v[1] for v in selected]
            assert a['selected_scores']==[v[2] for v in selected] and a['status']==status
            assert out['calibration_status']==status and out['calibration_adjustment']==adjustment
            assert out['point_prediction']==current['point_prediction']
            if status=='raw_invalid_uncalibrated':assert out['lower_bound'] is None and out['upper_bound'] is None
            else:assert out['lower_bound']==current['lower_bound']-(adjustment or 0) and out['upper_bound']==current['upper_bound']+(adjustment or 0)
        pools=read(bundle/'pool_audit.json.gz');assert len(pools)==44;paths=0
        for p in pools:
            o,m=p['origin'],p['model'];expected=sorted({past for (model,past,h) in raw if model==m and idx(past)+3<=idx(o)-1})[-60:]
            assert [v['source_origin'] for v in p['vectors']]==expected and 24<=len(expected)<=60
            seed=int.from_bytes(hashlib.sha256(f'2026102901|{o}|{m}|planning'.encode()).digest()[:16],'big')
            assert str(seed)==p['planning_seed'];rng=Random(seed)
            for i in range(128):
                past=expected[rng.randrange(len(expected))]
                for h in (1,2,3):
                    row=p['planning_records'][i*3+h-1];r=raw[m,past,h];ratio=prices[r['target_month']]/r['point_prediction']
                    assert row['source_oof_origin']==past and row['price']==raw[m,o,h]['point_prediction']*ratio and row['probability']==1/128
                paths+=1
        accounting=verify_calendar(bundle,bundle,prices,{(p['origin'],p['model']):p for p in pools},'final_shape',(22,24,21,132))
        report=read(bundle/'restricted_validator_synthetic.json');request=read(bundle/'access_approval_request.json')
        assert report['structural_validation']=='PASS' and report['real_source_verification']=='REAL_SOURCE_NOT_VERIFIED'
        assert request['status']=='ACCESS_APPROVAL_REQUIRED' and not request['bridge_holdout_access']
        assert preservation()['passed']
        equal=0
        if repeat:
            assert read(repeat/'run_manifest.json')==manifest
            for name in [*manifest['outputs'],'run_manifest.json']:
                assert (bundle/name).read_bytes()==(repeat/name).read_bytes();equal+=1
        return {'passed':True,'independent_of_adapter_and_lifecycle_computation':True,'saved_legacy_batches':192,'saved_forecast_values_checked':576,
            'synthetic_legacy_batches':192,'fresh_native_batches':44,'fresh_native_fit_events':286,'calibration_rows_checked':132,
            'joint_paths_checked':paths,'synthetic_accounting':accounting,'deterministic_files_equal':equal,
            'real_source_export_verified':False,'real_seed_runtime_verified':'NOT_VERIFIED','source_access':access,
            'run_manifest_sha256':sha(bundle/'run_manifest.json'),'actual_holdout_execution_allowed':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path);p.add_argument('--repeat',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    v=verify(a.bundle.resolve(),a.repeat.resolve() if a.repeat else None);save(a.output,v);print(json.dumps(v))
