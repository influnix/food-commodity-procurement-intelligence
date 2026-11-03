"""Independent saved-seed and synthetic accounting verification; no evaluation execution."""
import argparse
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

from support import ROOT,D12,read,sha,save,no_data_access,preservation
sys.path.insert(0,str(ROOT/'scripts'))
from verify_day12_results import verify_calendar


def rows(p):
    with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def idx(m):y,n=map(int,m.split('-'));return y*12+n-1


def verify(bundle:Path,repeat:Path,seed_path:Path) -> dict:
    with no_data_access(ROOT) as access:
        a=read(bundle/'run_manifest.json');b=read(repeat/'run_manifest.json');assert a==b and a['complete']
        equal=0
        for name,h in a['outputs'].items():
            assert sha(bundle/name)==h and (bundle/name).read_bytes()==(repeat/name).read_bytes();equal+=1
        assert (bundle/'run_manifest.json').read_bytes()==(repeat/'run_manifest.json').read_bytes();equal+=1
        for name,h in a['code_at_start'].items():assert sha(ROOT/name)==h
        wiring=read(bundle/'final_wiring.json')
        assert wiring['calibration_adapter']=='HorizonSequentialOOF' and wiring['joint_release']=='full_vector'
        observations=read(bundle/'synthetic_observations.json');assert all(v['knowledge_type']=='synthetic_day12_not_world_bank' for v in observations)
        prices={v['observation_month']:v['price'] for v in observations}
        pools=read(bundle/'pool_audit.json.gz');lookup={(p['origin'],p['model']):p for p in pools}
        result=verify_calendar(bundle,bundle,prices,lookup,'final_shape',(22,24,21,132))
        assert result=={'policies':7,'decisions':154,'ledger_rows':168,'plans':132}
        d15=ROOT/'artifacts/day15/evidence_a'
        for name in ('calibrated','calibration_audit','pool_audit','oof_released'):
            assert read(bundle/(name+'.json.gz'))==read(d15/(name+'.json.gz'))
        mutation=read(bundle/'future_mutation_prefix.json');assert mutation['passed'] and all(p['same_first_orders'] for p in mutation['policies'])
        seed=read(seed_path);assert seed['source_seed_status']=='ACCESS_APPROVAL_REQUIRED' and seed['actual_live_issuance']=='NOT_VERIFIED'
        assert seed['source']['raw_current_bytes']=='NOT_VERIFIED' and seed['source']['raw_hash_evidence_level']=='DOCUMENTED_PREVIOUS_HASH'
        d5=ROOT/'artifacts/day5/20261029T004616487272Z';manifest=read(d5/'manifest.json')
        raw_path=d5/'all_oof_forecasts.csv';assert sha(raw_path)==manifest['output_sha256']['all_oof_forecasts.csv']
        forecasts=rows(raw_path);assert len(forecasts)==576
        evidence={(r['model'],r['origin'],r['horizon']):r for r in seed['records']}
        keys=set();groups={}
        for r in forecasts:
            m,o,h=r['model_name'],r['forecast_origin'],int(r['horizon']);key=m,o,h
            assert key not in keys and 'actual_price' not in r and r['target_month']<='2024-08'
            assert idx(r['target_month'])==idx(o)+h and idx(r['information_cutoff'])==idx(o)-1
            assert idx(r['fit_information_end'])<=idx(o)-1
            expected=hashlib.sha256(json.dumps(r,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            assert evidence[key]['raw_row_sha256_derived_today']==expected
            assert not evidence[key]['contemporaneous_live_issuance_verified']
            assert evidence[key]['original_per_origin_live_issuance_digest']=='NOT_AVAILABLE'
            # First eligibility under the recorded month-plus-one publication assumption.
            assert idx(evidence[key]['calibration_earliest_eligible_origin'])==idx(r['target_month'])+1
            keys.add(key);groups.setdefault((m,r['phase']),set()).add(o)
        assert len(keys)==576 and sorted(len(v) for v in groups.values())==[36,36,60,60]
        assert all(not '2024-06'<=o<='2024-08' for _,o,_ in keys)
        assert len(seed['batches'])==192 and all(v['full_vector_mature_by_first_final_origin'] for v in seed['batches'])
        assert all(idx(v['joint_earliest_eligible_origin'])==idx(v['origin'])+4 for v in seed['batches'])
        residuals=rows(d5/'historical_oof_calibration.csv')+rows(d5/'validation_oof_calibration.csv')
        assert len(residuals)==558 and seed['existing_forecasts_with_newly_joined_saved_actual_evidence']==18
        by_key={(r['model_name'],r['forecast_origin'],int(r['horizon'])):r for r in forecasts}
        actuals={r['observation_month']:(float(r['price']),r['available_at']) for r in rows(ROOT/'artifacts/day9/20261030T090528446877Z/evaluation_prices.csv')}
        for r in residuals:
            f=by_key[r['source_model'],r['residual_forecast_origin'],int(r['residual_horizon'])]
            y=float(r['actual_price']);p=float(f['point_prediction'])
            assert abs((y-p)-float(r['residual_value']))<=1e-8
            assert abs(max(float(f['lower_bound'])-y,y-float(f['upper_bound']),0.)-float(r['calibration_score']))<=1e-8
            actuals[r['residual_target_month']]=y,r['residual_actual_available_at']
        for key,f in by_key.items():
            y,stamp=actuals[f['target_month']];p=float(f['point_prediction'])
            body={'actual':y,'point':p,'residual':y-p,'score':max(float(f['lower_bound'])-y,y-float(f['upper_bound']),0.),'available_at_assumed':stamp}
            assert hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False).encode()).hexdigest()==evidence[key]['reconstructed_oof_sha256_derived_today']
        p=preservation();assert p['passed']
        return {'passed':True,'independent_of_runner_and_seed_audit_calculations':True,'synthetic_accounting':result,
            'saved_nonholdout_forecasts_checked':576,'saved_residuals_checked':558,'reconstructed_oof_evidence_hashes_checked':576,'seed_batches_checked':192,
            'source_grade_not_promoted':True,'deterministic_files_equal':equal,'run_manifest_sha256':sha(bundle/'run_manifest.json'),
            'source_access':access,'actual_holdout_execution_allowed':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path);p.add_argument('--repeat',type=Path,required=True)
    p.add_argument('--seed-audit',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    v=verify(a.bundle.resolve(),a.repeat.resolve(),a.seed_audit.resolve());save(a.output,v);print(json.dumps(v))
