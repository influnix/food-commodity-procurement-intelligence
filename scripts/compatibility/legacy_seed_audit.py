"""Read only pinned saved non-Holdout evidence. Never opens World Bank data files."""

import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_bootstrap_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
_bootstrap_sys.path.insert(0, str(_bootstrap_root))
import csv
from datetime import date,datetime
import hashlib
import json
import math

from scripts.compatibility.handoff_support import ROOT,cfg,read,save,sha,no_data_access
from food_procurement_intelligence.evaluation.splits import add_months,decision_at,months_between,parse_month_label

D5=ROOT/'artifacts/day5/20261029T004616487272Z'
D9=ROOT/'artifacts/day9/20261030T090528446877Z'


def row_hash(row:dict) -> str:
    return hashlib.sha256(json.dumps(row,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def earliest_release(targets,available):
    t=add_months(max(targets),1)
    while max(available)>decision_at(t):t=add_months(t,1)
    return t


def saved_rows(path,expected_sha):
    if not path.resolve().is_relative_to(ROOT/'artifacts') or sha(path)!=expected_sha:
        raise ValueError('Unpinned/non-artifact saved evidence')
    with path.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))


def validate_forecast_keys(rows,d4,d5):
    historical=set(months_between(parse_month_label(d5['historical_origin_start']),parse_month_label(d5['historical_origin_end'])))
    validation=set(months_between(date(2021,6,1),date(2024,5,1)))
    models={d4[label]['model_name']:label for label in ('sarimax','lightgbm')}
    keys=set()
    for r in rows:
        o=parse_month_label(r['forecast_origin']);h=int(r['horizon']);t=parse_month_label(r['target_month'])
        if ('actual_price' in r or r['model_name'] not in models or h not in (1,2,3) or t!=add_months(o,h)
            or o not in historical|validation or r['phase']!=('historical_train' if o in historical else 'validation')
            or t>date(2024,8,1)):
            raise ValueError('Saved forecast escaped verified Train/Validation scope')
        key=r['model_name'],o,h
        if key in keys:raise ValueError('Duplicate saved forecast key')
        keys.add(key)
    expected={(m,o,h) for m in models for o in historical|validation for h in (1,2,3)}
    if keys!=expected:raise ValueError('Missing saved Historical60/Validation36 forecast')
    return models,historical,validation


def audit() -> dict:
    """A+B audit, with separate current-byte and assumed/historical source grades."""
    with no_data_access(ROOT) as access:
        m=read(D5/'manifest.json');expected=cfg(6)['day5_manifest_sha256']
        if sha(D5/'manifest.json')!=expected:raise ValueError('Day5 Manifest differs from pre-existing Day6 pin')
        d4,d5=cfg(4),cfg(5)
        if sha(ROOT/'configs/forecasting/models.toml')!=m['model_config_sha256'] or sha(ROOT/'configs/scenarios/calibration.toml')!=m['config_sha256']:
            raise ValueError('Original model/uncertainty specs changed')
        forecasts=saved_rows(D5/'all_oof_forecasts.csv',m['output_sha256']['all_oof_forecasts.csv'])
        models,historical,validation=validate_forecast_keys(forecasts,d4,d5)
        # Numeric decoding starts only after all saved keys have passed scope checks.
        indexed={(r['model_name'],r['forecast_origin'],int(r['horizon'])):r for r in forecasts}
        refs=read(ROOT/'artifacts/day13/evidence_a/evidence_release_manifest.json')['references']
        d9price_ref=next(r for r in refs if r['path']==(D9/'evaluation_prices.csv').relative_to(ROOT).as_posix())
        prices=saved_rows(D9/'evaluation_prices.csv',d9price_ref['sha256'])
        if len(prices)!=38 or {r['observation_month'] for r in prices}!={f'{o:%Y-%m}' for o in months_between(date(2021,7,1),date(2024,8,1))}:
            raise ValueError('Saved Validation price evidence has unexpected scope')
        if any(r['unit']!='USD_per_metric_tonne' or not r['availability_basis'].startswith('assumed_') for r in prices):
            raise ValueError('Saved actual unit/publication basis mismatch')
        actuals={r['observation_month']:(float(r['price']),datetime.fromisoformat(r['available_at'])) for r in prices}
        residuals=[]
        for name,phase in [('historical_oof_calibration.csv','historical_train'),('validation_oof_calibration.csv','validation')]:
            rows=saved_rows(D5/name,m['output_sha256'][name])
            for r in rows:
                o=parse_month_label(r['residual_forecast_origin']);t=parse_month_label(r['residual_target_month']);h=int(r['residual_horizon'])
                if (r['phase']!=phase or o not in (historical if phase=='historical_train' else validation)
                    or t!=add_months(o,h) or t>date(2024,8,1) or (r['source_model'],r['residual_forecast_origin'],h) not in indexed):
                    raise ValueError('Saved OOF actual escaped approved phase/calendar')
            residuals.extend(rows)
        for r in residuals:
            key=r['source_model'],r['residual_forecast_origin'],int(r['residual_horizon']);f=indexed[key]
            y=float(r['actual_price']);point=float(f['point_prediction']);stamp=datetime.fromisoformat(r['residual_actual_available_at'])
            if not math.isclose(y-point,float(r['residual_value']),rel_tol=0,abs_tol=1e-8):raise ValueError('Saved residual/point mismatch')
            score=max(float(f['lower_bound'])-y,y-float(f['upper_bound']),0.)
            if not math.isclose(score,float(r['calibration_score']),rel_tol=0,abs_tol=1e-8):raise ValueError('Saved calibration score mismatch')
            if r['residual_target_month'] in actuals and actuals[r['residual_target_month']]!=(y,stamp):
                raise ValueError('Different saved actual/publication evidence for same month')
            actuals[r['residual_target_month']]=y,stamp
        fits=read(D5/'fit_log.json')
        if sha(D5/'fit_log.json')!=m['output_sha256']['fit_log.json']:raise ValueError('Fit log changed')
        fit_index={}
        for e in fits:fit_index.setdefault((e['model'],e['forecast_origin']),[]).append(e)
        saved_residual_keys={(r['source_model'],r['residual_forecast_origin'],int(r['residual_horizon'])) for r in residuals}
        records=[];batches=[];forecasts_by_origin={}
        for r in forecasts:
            model,o,h=r['model_name'],parse_month_label(r['forecast_origin']),int(r['horizon']);target=parse_month_label(r['target_month'])
            label=models[model];events=fit_index[label,r['forecast_origin']]
            if r['information_cutoff']!=f'{add_months(o,-1):%Y-%m}' or r['forecast_asof_at']!=decision_at(o).isoformat() or int(r['steps_from_latest_observation'])!=h+1:
                raise ValueError('Forecast origin/cutoff/step proof mismatch')
            if (parse_month_label(r['fit_information_end'])>add_months(o,-1)
                or datetime.fromisoformat(r['fit_max_label_available_at'])>decision_at(o)
                or r['calibration_status']!='raw_not_requested' or r['unit']!='USD_per_metric_tonne'):
                raise ValueError('Invalid original raw fit proof')
            if not events or any(e['status']!='success' for e in events):raise ValueError('Missing/successful fit evidence')
            relevant=[e for e in events if label=='sarimax' or e['horizon']==h]
            if label=='sarimax':
                if len(relevant)!=1 or date.fromisoformat(relevant[0]['train_end'])>add_months(o,-1) or not relevant[0]['converged']:
                    raise ValueError('SAR historical logical fit evidence mismatch')
            else:
                if (len(relevant)!=4 or {e['quantile'] for e in relevant}!={None,.1,.5,.9}
                    or any(date.fromisoformat(e['feature_origin_end'])>add_months(o,-4)
                        or date.fromisoformat(e['train_end'])>add_months(o,-1)
                        or datetime.fromisoformat(e['max_label_available_at'])>decision_at(o)
                        or len(e['feature_names'])!=15 for e in relevant)):
                    raise ValueError('LGB historical logical mature-feature/fit proof mismatch')
            y,available=actuals[f'{target:%Y-%m}'];point=float(r['point_prediction'])
            q=[float(r[k]) for k in ('q10','q50','q90')]
            if not all(math.isfinite(v) for v in [y,point,*q]) or y<=0 or point<=0:raise ValueError('Bad saved price/point evidence')
            release=earliest_release((target,),(available,))
            key=model,r['forecast_origin'],h
            records.append({'forecast_id':r['record_id'],'model':model,'origin':r['forecast_origin'],'horizon':h,'target':f'{target:%Y-%m}',
                'phase':r['phase'],'information_cutoff':r['information_cutoff'],'fit_information_end':r['fit_information_end'],
                'fit_max_label_available_at':r['fit_max_label_available_at'],'target_available_at_assumed':available.isoformat(),
                'calibration_earliest_eligible_origin':f'{release:%Y-%m}',
                'raw_row_sha256_derived_today':row_hash(r),'original_file_sha256':m['output_sha256']['all_oof_forecasts.csv'],
                'original_per_origin_live_issuance_digest':'NOT_AVAILABLE','knowledge_type':'reconstructed_asof_world_bank_snapshot',
                'contemporaneous_live_issuance_verified':False,'stored_residual_already_present':key in saved_residual_keys,
                'residual_verified_against_saved_evidence':True,'actual_evidence_kind':'B_saved_nonholdout_only',
                'residual_verification_kind':'saved_residual_arithmetic' if key in saved_residual_keys else 'existing_forecast_joined_saved_validation_actual',
                'reconstructed_oof_sha256_derived_today':row_hash({'actual':y,'point':point,'residual':y-point,
                    'score':max(float(r['lower_bound'])-y,y-float(r['upper_bound']),0.),'available_at_assumed':available.isoformat()}),
                'raw_crossing':not q[0]<=q[1]<=q[2]})
            forecasts_by_origin.setdefault((model,o),[]).append(records[-1])
        for (model,o),group in sorted(forecasts_by_origin.items()):
            if sorted(r['horizon'] for r in group)!=[1,2,3]:raise ValueError('Incomplete seed vector')
            joint_release=earliest_release(tuple(parse_month_label(r['target']) for r in group),
                tuple(datetime.fromisoformat(r['target_available_at_assumed']) for r in group))
            batches.append({'model':model,'origin':f'{o:%Y-%m}','phase':group[0]['phase'],'horizons':[1,2,3],
                'joint_earliest_eligible_origin':f'{joint_release:%Y-%m}',
                'full_vector_mature_by_first_final_origin':joint_release<=date(2024,9,1),
                'evidence_batch_sha256_derived_today':row_hash({'records':group}),
                'native_issued_forecast_restore_compatible':False})
        if len(records)!=576 or len(batches)!=192 or not all(b['full_vector_mature_by_first_final_origin'] for b in batches):
            raise ValueError('Incomplete/as-of immature source seed evidence')
        d9=read(D9/'manifest.json')
        if d9['source_data']!=m['source_data'] or d9['raw_sha256']!=m['raw_sha256']:raise ValueError('Different saved source snapshot identities')
        source={'source_identity':'World Bank Pink Sheet Wheat US HRW','raw_current_bytes':'NOT_VERIFIED',
            'raw_hash_evidence_level':'DOCUMENTED_PREVIOUS_HASH','raw_sha256_recorded':m['raw_sha256'],
            'processed_source':m['source_data'],'saved_evidence_bytes':'VERIFIED_CURRENT_BYTES',
            'forecast_cutoff_and_fit_log_logic':'VERIFIED_RECONSTRUCTED_ASOF',
            'reconstructed_asof_scope':'stored output metadata and logical arithmetic only; original training prices not reopened',
            'historical_vintage':'NOT_VERIFIED','historical_vintage_requested_grade':'VERIFIED_HISTORICAL_VINTAGE not attained',
            'publication_time':'ASSUMED_PUBLICATION_TIME','actual_historical_release_timestamp':'NOT_VERIFIED',
            'source_provenance_verified':False,
            'limitation':'이 평가는 공식 World Bank 가격의 수정된 단일 Snapshot과 사전 정의된 공표 지연 가정을 사용하는 pseudo-real-time historical simulation이다. 실제 당시 발표 Vintage와 최초 공표 Timestamp를 완전히 복원한 평가가 아니다.'}
        return {'saved_seed_audit':'PASS_WITH_LIMITATIONS','source_seed_status':'ACCESS_APPROVAL_REQUIRED',
            'forecast_records':len(records),'origin_model_batches':len(batches),'historical_origins_per_model':60,'validation_origins_per_model':36,
            'existing_saved_residuals_verified':len(residuals),'existing_forecasts_with_newly_joined_saved_actual_evidence':576-len(residuals),
            'saved_validation_price_months_read':38,'new_forecasts_or_fits':0,'unissued_2024_06_08_backfilled':False,
            'read_only_evidence_archive_reconstruction':'VERIFIED_RECONSTRUCTED_ASOF',
            'runtime_restore':'BLOCKED_NOT_A_NATIVE_SYNTHETIC_ISSUANCE_ARCHIVE',
            'first_runtime_blocker':'SessionPermit accepts synthetic knowledge only; legacy Day5 records lack native per-origin history/model/session issuance envelope; do not fabricate those fields',
            'actual_live_issuance':'NOT_VERIFIED','source':source,'records':records,'batches':batches,
            'manifest_links':{'day5_manifest_sha256':sha(D5/'manifest.json'),'day9_manifest_sha256':sha(D9/'manifest.json'),
                'day5_raw_forecasts_sha256':m['output_sha256']['all_oof_forecasts.csv'],'day9_saved_prices_sha256':d9price_ref['sha256']},
            'additional_access_request':{'status':'ACCESS_APPROVAL_REQUIRED','original_mixed_file':m['source_data']['path'],
                'safe_separate_export_requested':'Train/Validation-only 1960-01..2024-08, 776 rows; excludes Bridge2024-09 and all Holdout targets',
                'columns':['observation_month','price','unit','source_series','available_at','availability_basis','vintage_id'],
                'purpose':'independently verify original fit history/source identity and future first-origin input; not restore unavailable historical vintages',
                'whole_original_file_loading_or_rehash_authorized':False,'bridge_or_holdout_access_requested_for_this_audit':False},
            'source_access':access}


if __name__=='__main__':
    import argparse
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not a.output.resolve().is_relative_to(ROOT/'artifacts/day16') or a.output.exists():raise ValueError('New Day16 output required')
    result=audit();save(a.output,result)
    print(json.dumps({k:result[k] for k in ('saved_seed_audit','source_seed_status','forecast_records','origin_model_batches','runtime_restore')}))
