"""Independent Day14 arithmetic verifier; no model, calibration, scenario or policy calls."""
import argparse
from calendar import monthrange
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
from random import Random
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from build_day13_evidence import no_data_access


def load(path):return json.loads(path.read_text(encoding='utf-8'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def idx(m):y,n=map(int,m.split('-'));return y*12+n-1
def month(i):return f'{i//12:04d}-{i%12+1:02d}'
def stamp(m):
    y,n=map(int,m.split('-'));return datetime(y,n,monthrange(y,n)[1],23,59,59,tzinfo=timezone.utc)


def verify(bundle: Path, repeat: Path | None = None) -> dict:
    with no_data_access(ROOT) as access:
        manifest=load(bundle/'audit_manifest.json')
        assert manifest['kind']=='DAY14_READ_ONLY_METHODOLOGY_AUDIT_NOT_EVALUATION_FREEZE'
        assert manifest['actual_holdout_execution_allowed'] is False and manifest['holdout_locked']
        for name,h in manifest['outputs'].items():assert digest(bundle/name)==h
        for name,h in manifest['references'].items():
            p=(ROOT/name).resolve()
            assert p.is_relative_to(ROOT) and not p.is_relative_to(ROOT/'data') and digest(p)==h
        cases=load(bundle/'synthetic_maturity_counterexamples.json');checked=0;different=0;paths=0
        for case in cases:
            t=idx(case['evaluation']);o_last=case['origins'][-1] if case['origins'] else None
            raw_invalid=case['case']=='crossing_excluded_from_scores_not_joint'
            def available(o,h):
                target=month(idx(o)+h);public=stamp(month(idx(o)+h+1))
                if o_last and case['delayed_horizon'] and target==month(idx(o_last)+case['delayed_horizon']):
                    public=stamp(case['evaluation'])+timedelta(seconds=case['delay_seconds'])
                return idx(target)<=t-1 and public<=stamp(case['evaluation'])
            full=[o for o in case['origins'] if all(available(o,h) for h in (1,2,3))][-60:]
            assert len(full)==case['joint']['day6_vector_count']==case['joint']['day12_vector_count']
            assert case['joint']['origins_equal'] and case['joint']['ratios_equal']
            for row in case['horizons']:
                h=row['horizon'];old=[o for o in case['origins'] if available(o,h) and not(raw_invalid and h==1)][-60:]
                new=[o for o in case['origins'] if all(available(o,j) for j in (1,2,3)) and not(raw_invalid and h==1)][-60:]
                for label,selected in [('day5',old),('day12',new)]:
                    scores=[10+idx(o)+h-idx('2015-01') for o in selected]
                    assert row[label+'_selected_origins']==selected and row[label+'_scores']==scores
                    n=len(scores);rank=math.ceil((n+1)*.8);adjustment=sorted(scores)[rank-1] if n>=24 and rank<=n else None
                    assert row[label+'_count']==n and row[label+'_rank']==rank and row[label+'_adjustment']==adjustment
                    assert row[label+'_status']==('calibrated' if adjustment is not None else 'insufficient_raw_fallback')
                    assert row[label+'_bounds']==([90-adjustment,110+adjustment] if adjustment is not None else [90,110])
                assert row['point_unchanged'];checked+=1
                different+=row['day5_bounds']!=row['day12_bounds'] or row['day5_status']!=row['day12_status']
            if case['joint']['paths_compared']:
                assert case['joint']['prices_equal'] and case['joint']['sampled_origins_equal']
                seed=int.from_bytes(hashlib.sha256(f"2026102901|{case['evaluation']}|sarimax_110_10012|planning".encode()).digest()[:16],'big')
                assert str(seed)==case['joint']['planning_seed']
                rng=Random(seed)
                assert len(case['joint']['path_pairs'])==128
                for pair in case['joint']['path_pairs']:
                    o=full[rng.randrange(len(full))]
                    expected=[120+idx(o)+h-idx('2015-01') for h in (1,2,3)]
                    assert pair['source_origin']==o
                    assert all(math.isclose(x,y,rel_tol=0,abs_tol=1e-12) for x,y in zip(pair['day6_prices'],expected))
                    assert pair['day6_prices']==pair['day12_prices']
                    paths+=1
        # Recount crossings from saved SYNTHETIC raw JSON, not generator aggregate.
        directory=ROOT/'artifacts/day12/run_20261030T152324128300Z_6ef590c2'
        found={};point={};batches={}
        for p in sorted((directory/'issuances').glob('*.json')):
            value=load(p);batches[value['label'],value['origin']]=value
            pinned=value['issued_sha256'];body={k:v for k,v in value.items() if k!='issued_sha256'}
            assert hashlib.sha256(json.dumps(body,sort_keys=True,default=str,allow_nan=False).encode()).hexdigest()==pinned
            assert value['knowledge_type']=='synthetic_day12_not_world_bank'
            proof=value['proof'];o=value['origin']
            assert proof['target_unobserved_at_issue'] and idx(proof['training_origin_end'])<=idx(o)-4
            assert idx(proof['last_complete_training_target'])<=idx(o)-1
            assert datetime.fromisoformat(proof['max_training_available_at'])<=stamp(o)
            for row in value['raw']:
                k=(row['model_name'],row['forecast_origin'],row['horizon']);point[k]=row['point_prediction']
                assert all(math.isfinite(row[n]) for n in ['point_prediction','q10','q50','q90','lower_bound','upper_bound'])
                if not row['q10']<=row['q50']<=row['q90']:found[k]=row
        audit=load(bundle/'quantile_crossing_fallback_audit.json')
        assert len(found)==14==audit['crossing_rows']
        assert set(found)=={(r['model'],r['origin'],r['horizon']) for r in audit['crossings']}
        calibrated=json.loads(gzip.decompress((directory/'calibrated.json.gz').read_bytes()))
        invalid=0
        for row in calibrated:
            k=(row['model_name'],row['forecast_origin'],row['horizon'])
            assert row['point_prediction']==point[k]
            if k in found:
                invalid+=1
                assert row['calibration_status']=='raw_invalid_uncalibrated' and row['lower_bound'] is None and row['upper_bound'] is None
        assert len(calibrated)==348 and invalid==13
        vectors=json.loads(gzip.decompress((directory/'oof_released.json.gz').read_bytes()))
        for r in vectors:
            assert idx(r['source_origin'])+3<=idx(r['first_released_at_origin'])-1
            assert all(datetime.fromisoformat(s)<=stamp(r['first_released_at_origin']) for s in r['actual_available_at'])
            for i in range(3):
                k=(r['model'],r['source_origin'],i+1)
                if k in found:assert r['scores'][i] is None
                assert math.isclose(r['ratios'][i],r['actual_prices'][i]/r['points'][i],rel_tol=0,abs_tol=1e-14)
        states={r['state']:r['status'] for r in load(bundle/'readiness_matrix.json')}
        assert states=={'MVP_COMPLETE':'PASS','TECHNICAL_READY':'PASS','METHODOLOGY_CONSISTENT':'ACTION_REQUIRED',
            'SOURCE_PROVENANCE_VERIFIED':'NOT_VERIFIED','PUBLICATION_MATURE':'NOT_VERIFIED','USER_AUTHORIZED':'false','HOLDOUT_EXECUTION_ALLOWED':'false'}
        mdr=load(bundle/'methodological_decision_record.json')
        assert mdr['status']=='PROPOSED_NOT_IMPLEMENTED' and not mdr['production_code_changed'] and not mdr['approval_requested_or_granted_today']
        preserved=load(bundle/'preservation.json');assert preserved['passed'] and not preserved['data_bytes_opened_or_rehashed']
        # Verify preservation again, independently (metadata only under data).
        before=load(ROOT/'artifacts/day14/preservation_before.json')
        for name,h in before['files'].items():assert digest(ROOT/name)==h
        for name,s in before['data_stat_only'].items():
            p=ROOT/name;assert p.stat().st_size==s['size'] and p.stat().st_mtime_ns==s['mtime_ns']
        equal=0
        if repeat:
            assert load(repeat/'audit_manifest.json')==manifest
            for name in [*manifest['outputs'],'audit_manifest.json']:
                assert (bundle/name).read_bytes()==(repeat/name).read_bytes();equal+=1
        return {'passed':True,'independent_of_audit_calculations':True,'synthetic_cases':len(cases),'horizon_comparisons':checked,
            'different_interval_or_fallback_rows':different,'toy_path_pairs_independently_checked':paths,
            'saved_synthetic_crossings_recounted':14,'calibrated_point_invariants_checked':348,'oof_vectors_checked':len(vectors),
            'references_checked':len(manifest['references']),'deterministic_files_equal':equal,
            'prior_file_hashes_checked':len(before['files']),'data_metadata_only_checked':len(before['data_stat_only']),
            'source_access':access,'actual_holdout_execution_allowed':False,'manifest_sha256':digest(bundle/'audit_manifest.json')}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path);p.add_argument('--repeat',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();v=verify(a.bundle.resolve(),a.repeat.resolve() if a.repeat else None)
    with a.output.open('x',encoding='utf-8') as f:json.dump(v,f,sort_keys=True,indent=2);f.write('\n')
    print(json.dumps(v))
