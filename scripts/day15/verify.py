"""Independent Day15 arithmetic; never invokes publisher, pool, policies, or solver."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from random import Random
import sys

from common import ROOT,D12,read,sha,no_data_access,save,cfg
sys.path.insert(0,str(ROOT/'scripts'))
from verify_day12_results import verify_calendar


def idx(m):y,n=map(int,m.split('-'));return y*12+n-1
def month(i):return f'{i//12:04d}-{i%12+1:02d}'
def stamp(m):
    from calendar import monthrange
    y,n=map(int,m.split('-'));return f'{m}-{monthrange(y,n)[1]:02d}T23:59:59+00:00'


def verify(bundle: Path,repeat: Path|None=None) -> dict:
    with no_data_access(ROOT) as access:
        manifest=read(bundle/'run_manifest.json');assert manifest['complete'] and manifest['new_fits']==0
        for name,h in manifest['outputs'].items():assert sha(bundle/name)==h
        for name,h in manifest['code_at_start'].items():assert sha(ROOT/name)==h
        values=read(bundle/'synthetic_observations.json');actual={r['observation_month']:r for r in values}
        assert all(r['knowledge_type']=='synthetic_day12_not_world_bank' and r['price']>0 for r in values)
        # Check the fixed Day12 synthetic input against its immutable history proof.
        batches=[read(p) for p in sorted((D12/'issuances').glob('*.json'))]
        raw={(r['model_name'],r['forecast_origin'],r['horizon']):r for b in batches for r in b['raw']}
        assert len(batches)==236 and len(raw)==708
        for b in batches:
            body={k:v for k,v in b.items() if k!='issued_sha256'}
            assert hashlib.sha256(json.dumps(body,sort_keys=True,default=str,allow_nan=False).encode()).hexdigest()==b['issued_sha256']
            assert b['knowledge_type']=='synthetic_day12_not_world_bank'
            assert b['proof']['target_unobserved_at_issue']
            assert idx(b['proof']['training_origin_end'])<=idx(b['origin'])-4
            assert datetime.fromisoformat(b['proof']['max_training_available_at'])<=datetime.fromisoformat(stamp(b['origin']))
            # Original publisher hashes the released VisiblePrice representation.
            history=[{'month':r['observation_month']+'-01','price':r['price'],'unit':r['unit'],'available_at':r['actual_available_at']}
                for r in values if idx(r['observation_month'])<=idx(b['origin'])-1 and r['actual_available_at']<=stamp(b['origin'])]
            # datetime/date canonical_hash uses str, not artifact month labels.
            history=[{**r,'available_at':str(datetime.fromisoformat(r['available_at']))} for r in history]
            assert len(history)==b['proof']['history_n']
            assert hashlib.sha256(json.dumps(history,sort_keys=True,default=str,allow_nan=False).encode()).hexdigest()==b['proof']['history_sha256']
        def valid(r):
            return all(isinstance(r[k],(int,float)) and not isinstance(r[k],bool) and math.isfinite(r[k]) for k in
                ('point_prediction','q10','q50','q90','lower_bound','upper_bound')) and r['point_prediction']>0 and r['q10']<=r['q50']<=r['q90'] and r['lower_bound']==r['q10'] and r['upper_bound']==r['q90']
        corrected=read(bundle/'calibrated.json.gz');audits=read(bundle/'calibration_audit.json.gz');checked=0
        for out,audit in zip(corrected,audits):
            m,o,h=out['model_name'],out['forecast_origin'],out['horizon'];current=raw[m,o,h]
            selected=[]
            for (model,past,j),r in raw.items():
                if model!=m or j!=h or past>=o or idx(r['target_month'])>idx(o)-1 or not valid(r):continue
                obs=actual[r['target_month']]
                if obs['actual_available_at']>stamp(o):continue
                selected.append((r['target_month'],past,max(r['lower_bound']-obs['price'],obs['price']-r['upper_bound'],0.)))
            selected=sorted(selected)[-60:];n=len(selected);rank=math.ceil((n+1)*.8)
            adjustment=sorted(r[2] for r in selected)[rank-1] if n>=24 and rank<=n else None
            status='calibrated' if adjustment is not None else 'insufficient_raw_fallback'
            if not valid(current):status='raw_invalid_uncalibrated';adjustment=None
            assert audit['count']==n and audit['rank']==rank and audit['status']==status
            assert audit['selected_source_origins']==[r[1] for r in selected]
            assert audit['selected_scores']==[r[2] for r in selected]
            assert out['calibration_status']==status and out['calibration_adjustment']==adjustment
            assert out['point_prediction']==current['point_prediction']
            if status=='raw_invalid_uncalibrated':assert out['lower_bound'] is None and out['upper_bound'] is None
            else:
                assert out['lower_bound']==current['lower_bound']-(adjustment or 0)
                assert out['upper_bound']==current['upper_bound']+(adjustment or 0)
            checked+=1
        assert checked==348
        pools=read(bundle/'pool_audit.json.gz');assert pools==read(D12/'pool_audit.json.gz');path_rows=0
        for p in pools:
            o,m=p['origin'],p['model'];seed=int.from_bytes(hashlib.sha256(f"2026102901|{o}|{m}|planning".encode()).digest()[:16],'big')
            assert str(seed)==p['planning_seed'] and p['planning_seed']!=p['evaluation_seed']
            rng=Random(seed);vectors=p['vectors'];assert 24<=len(vectors)<=60
            for i in range(128):
                v=vectors[rng.randrange(len(vectors))]
                assert idx(v['source_origin'])+3<=idx(o)-1 and max(v['actual_available_at'])<=stamp(o)
                for h in (1,2,3):
                    row=p['planning_records'][i*3+h-1]
                    ratio=actual[v['targets'][h-1]]['price']/raw[m,v['source_origin'],h]['point_prediction']
                    assert ratio==v['ratios'][h-1]
                    expected=raw[m,o,h]['point_prediction']*ratio
                    assert row['source_oof_origin']==v['source_origin'] and row['price']==expected and row['probability']==1/128
                    path_rows+=1
        assert len(read(bundle/'oof_released.json.gz'))==228
        lookup={(p['origin'],p['model']):p for p in pools};prices={m:v['price'] for m,v in actual.items()}
        solved=0
        for label,counts in [('final_shape',(22,24,21,132)),('validation_shape',(36,38,35,216))]:
            result=verify_calendar(bundle,bundle,prices,lookup,label,counts);solved+=result['plans']
        cases=read(bundle/'counterexample_regression.json')
        assert cases['case_count']==16 and cases['changed_vs_day14_interval_or_fallback_rows']==4
        for c in cases['cases']:
            for h in c['horizons']:
                assert all(h['day5_'+k]==h['day12_'+k] for k in ('count','rank','status','bounds','adjustment','scores','selected_origins'))
        equal=0
        if repeat:
            other=read(repeat/'run_manifest.json');assert other==manifest
            for name in [*manifest['outputs'],'run_manifest.json']:
                assert (bundle/name).read_bytes()==(repeat/name).read_bytes();equal+=1
        return {'passed':True,'calibration_rows_independently_checked':checked,'synthetic_raw_records_checked':len(raw),
            'synthetic_batches_checked':len(batches),'joint_pool_pairs_checked':len(pools),'joint_price_rows_checked':path_rows,
            'oof_vectors_checked':228,'policy_plans_independently_verified':solved,'toy_counterexamples':16,
            'deterministic_files_equal':equal,'source_access':access,'actual_holdout_execution_allowed':False,
            'run_manifest_sha256':sha(bundle/'run_manifest.json')}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path);p.add_argument('--repeat',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();v=verify(a.bundle.resolve(),a.repeat.resolve() if a.repeat else None)
    if a.output.exists():raise FileExistsError('Do not overwrite verification evidence')
    save(a.output,v);print(json.dumps(v))
