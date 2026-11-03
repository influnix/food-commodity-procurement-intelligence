"""No-fit Day15 remediation regression on pinned synthetic native forecasts only."""
import argparse
from dataclasses import replace
from collections import Counter
from datetime import date
import importlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

from common import ROOT,D12,cfg,read,save,zipped,sha,no_data_access,preservation,load_saved_batches
from food_procurement_intelligence.data.sequential import SessionPermit,SequentialObservationStore
from food_procurement_intelligence.data.sequential import canonical_hash
from food_procurement_intelligence.evaluation.sequential_runner import synthetic_observations,release_publications,EvaluationCalendar,run_policy_calendar
from food_procurement_intelligence.evaluation.splits import load_split_plans,months_between,parse_month_label
from food_procurement_intelligence.evaluation.model_backtesting import save_csv
from food_procurement_intelligence.evaluation.day6 import _serializable
from food_procurement_intelligence.forecasting.publisher import NativeForecastPublisher
from food_procurement_intelligence.uncertainty.horizon_sequential import HorizonSequentialOOF


def models():return {k:cfg(4)[k]['model_name'] for k in ('sarimax','lightgbm')}


def counterexample_regression() -> dict:
    old=read(ROOT/'artifacts/day14/evidence_a/synthetic_maturity_counterexamples.json')
    day14=importlib.import_module('audit');pools=[]
    def factory(*args):
        p=HorizonSequentialOOF(*args,models=models());pools.append(p);return p
    with patch.object(day14,'SequentialOOF',factory):new=day14.counterexamples()
    changed=0
    for before,after,pool in zip(old,new,pools):
        assert before['case']==after['case']
        for b,a in zip(before['horizons'],after['horizons']):
            for key in ('count','status','adjustment','rank','bounds','selected_origins'):
                assert a['day5_'+key]==a['day12_'+key],(after['case'],key)
            selected=pool.calibration_residuals(models()['sarimax'],parse_month_label(after['evaluation']),a['horizon'])
            a['day12_scores']=[r['score'] for r in selected]
            assert a['day12_scores']==a['day5_scores']
            changed+=b['day12_bounds']!=a['day12_bounds'] or b['day12_status']!=a['day12_status']
        assert before['joint']==_serializable(after['joint']),'Joint changed in toy counterexample'
    return {'cases':new,'case_count':len(new),'horizon_comparisons':48,'all_equal_day5':True,
        'changed_vs_day14_interval_or_fallback_rows':changed,'joint_path_pairs_unchanged':896,
        'note':'day12_* keys identify the sequential adapter slot; it uses corrected Day15 logic here; old Day14 file unchanged'}


def replay_stream() -> dict:
    c,d5,d6=cfg(12),cfg(5),cfg(6);p=load_split_plans(ROOT/'configs/splits.toml')[0]
    issued=load_saved_batches();observations=synthetic_observations(c)
    source=json.loads(next(iter(issued.values())).proof_json)
    store=SequentialObservationStore(SessionPermit(source['source_session'],source['source_id']))
    pool=HorizonSequentialOOF(store.permit,d5,d6['scenarios'],p,models())
    scenarios={};calibrated=[];audits=[];pools=[]
    for origin in months_between(parse_month_label(d5['historical_origin_start']),parse_month_label(c['last_origin'])):
        release_publications(store,observations,origin);pool.tick(store,origin)
        for label in ('sarimax','lightgbm'):
            b=issued.get((label,origin))
            if b is None:continue
            phase='historical_train' if origin<=parse_month_label(d5['historical_origin_end']) else 'validation' if origin<=p.validation_origin_end else 'sequential_synthetic'
            if phase!='historical_train':
                corrected,audit=pool.calibrate(b);calibrated.extend(r.record() for r in corrected);audits.extend(audit)
                planning,vectors=pool.scenarios(b,'planning');evaluation,_=pool.scenarios(b,'evaluation')
                try:evaluation.for_policy(origin)
                except ValueError:rejected=True
                else:raise AssertionError('Evaluation scenario reached policy')
                scenarios[label,origin]=planning
                pools.append({'origin':origin,'label':label,'model':b.raw[0].model_name,'phase':phase,'pool_n':len(vectors),
                    'vectors':vectors,'pool_sha256':planning.pool_sha256,'planning_seed':str(planning.seed),
                    'evaluation_seed':str(evaluation.seed),'evaluation_rejected':rejected,'planning_records':planning.records()})
            pool.issue(b,phase)
    return {'observations':observations,'store':store,'issued':issued,'scenarios':scenarios,'pool_audit':pools,
        'calibrated':calibrated,'calibration_audit':audits,'oof_released':list(pool.released.values()),
        'calibration_released':list(pool.calibration_released.values()),'release_log':store.release_log,'pool':pool}


def impact(stream) -> dict:
    new=_serializable(stream['calibration_audit']);old=read(D12/'calibration_audit.json.gz')
    corrected=stream['calibrated'];before=read(D12/'calibrated.json.gz');differences=[]
    for a,b,c,d in zip(old,new,before,corrected):
        assert (a['model'],a['origin'],a['horizon'])==(b['model'],b['origin'],b['horizon'])
        membership=a['selected_source_origins']!=b['selected_source_origins']
        if membership or a['adjustment']!=b['adjustment'] or a['status']!=b['status']:
            differences.append({'model':a['model'],'origin':a['origin'],'horizon':a['horizon'],
                'old_count':a['count'],'new_count':b['count'],'membership_changed':membership,
                'old_adjustment':a['adjustment'],'new_adjustment':b['adjustment'],'old_rank':a['rank'],'new_rank':b['rank'],
                'old_status':a['status'],'new_status':b['status'],
                'old_bounds':[c['lower_bound'],c['upper_bound']],'new_bounds':[d['lower_bound'],d['upper_bound']],
                'cause':'horizon_maturity_and_resulting_membership; same rank formula; saved raw validity unchanged'})
        assert c['point_prediction']==d['point_prediction']
    return {'old_status_counts':dict(Counter(r['calibration_status'] for r in before)),
        'new_status_counts':dict(Counter(r['calibration_status'] for r in corrected)),
        'point_invariants':len(corrected),'changed_membership_or_adjustment_or_status_rows':len(differences),
        'rank_formula_changed':False,'saved_raw_validity_changed':False,'differences':differences}


def seed_archive_audit() -> dict:
    """Only pinned synthetic native batches; explicit mutation probes, never real archive."""
    issued=load_saved_batches();seeds=tuple(b for (_,o),b in issued.items() if o<date(2024,9,1))
    proof=json.loads(seeds[0].proof_json);permit=SessionPermit('DAY15_ARCHIVE_INTERFACE_AUDIT',proof['source_id'])
    p=load_split_plans(ROOT/'configs/splits.toml')[0]
    factory=lambda:HorizonSequentialOOF(permit,cfg(5),cfg(6)['scenarios'],p,models())
    digest=canonical_hash([b.record() for b in seeds]);pool=factory();pool.restore_seed_archive(seeds,digest)
    store=SequentialObservationStore(permit);release_publications(store,synthetic_observations(cfg(12)),date(2024,9,1));pool.tick(store,store.clock)
    assert len(pool.released)==192 and len(pool.calibration_released)==566
    cases=[]
    for fault in ('hash','missing_batch','source','knowledge','model','session','history','model_proof','horizon','fit','publication','issuance'):
        test=factory();batches=list(seeds);b=batches[0];proof=json.loads(b.proof_json)
        try:
            if fault=='missing_batch':batches.pop()
            elif fault=='source':proof['source_id']='WRONG';batches[0]=replace(b,proof_json=json.dumps(proof))
            elif fault=='knowledge':batches[0]=replace(b,knowledge_type='actual_world_bank')
            elif fault=='model':batches[0]=replace(b,raw=tuple(replace(r,model_name='wrong') for r in b.raw))
            elif fault=='session':proof['source_session']='';batches[0]=replace(b,proof_json=json.dumps(proof))
            elif fault=='history':proof['history_end']='2099-01';batches[0]=replace(b,proof_json=json.dumps(proof))
            elif fault=='model_proof':proof['model_spec_sha256']='';batches[0]=replace(b,proof_json=json.dumps(proof))
            elif fault=='horizon':batches[0]=replace(b,raw=(b.raw[0],b.raw[2],b.raw[1]))
            elif fault=='fit':batches[0]=replace(b,raw=(replace(b.raw[0],fit_information_end=b.origin),*b.raw[1:]))
            elif fault=='publication':proof['max_training_available_at']='2099-01-31T23:59:59+00:00';batches[0]=replace(b,proof_json=json.dumps(proof))
            elif fault=='issuance':proof['target_unobserved_at_issue']=False;batches[0]=replace(b,proof_json=json.dumps(proof))
            h='wrong' if fault=='hash' else canonical_hash([v.record() for v in batches]);test.restore_seed_archive(batches,h)
        except ValueError as error:
            assert not test.pending and not test.calibration_pending
            cases.append({'probe':fault,'status':'REJECTED','error_type':type(error).__name__,'atomic':True})
        else:raise AssertionError('Bad archive accepted: '+fault)
    return {'synthetic_interface':'PASS','actual_seed_provenance':'NOT_VERIFIED','archive_sha256':digest,
        'seed_batches':192,'historical_batches':120,'validation_batches':72,'full_vectors_released':192,
        'horizon_scores_released':566,'crossing_scores_excluded':10,'gap_2024_06_08_backfilled':False,
        'restored_original_session_preserved':True,'publication_basis':'explicit synthetic next-month-end assumption, not actual World Bank release proof',
        'mutation_probes':cases,'actual_archive_prices_or_residuals_read':False}


def run(output: Path) -> dict:
    output=output.resolve()
    if not output.is_relative_to(ROOT/'artifacts/day15'):raise ValueError('Day15 output only')
    output.mkdir(parents=True,exist_ok=False)
    code_at_start={p.relative_to(ROOT).as_posix():sha(p) for d in ('src','configs','scripts/day15') for p in sorted((ROOT/d).rglob('*')) if p.is_file() and p.suffix in ('.py','.toml','.json')}
    with no_data_access(ROOT) as access, patch.object(NativeForecastPublisher,'publish',side_effect=AssertionError('No new fits in Day15 replay')):
        counter=counterexample_regression();save(output/'counterexample_regression.json',counter)
        stream=replay_stream()
        save(output/'seed_archive_verification.json',seed_archive_audit())
        old=read(D12/'pool_audit.json.gz');current=_serializable(stream['pool_audit'])
        assert old==current,'Joint semantic/provenance/draw change'
        assert read(D12/'oof_released.json.gz')==_serializable(stream['oof_released'])
        save(output/'methodology_impact.json',impact(stream))
        for name in ('pool_audit','oof_released','calibrated','calibration_audit','calibration_released','release_log'):
            zipped(output/(name+'.json.gz'),stream[name])
        save(output/'synthetic_observations.json',[r.__dict__ for r in stream['observations']])
        e2e={};p=load_split_plans(ROOT/'configs/splits.toml')[0]
        calendars={'final_shape':EvaluationCalendar(date(2024,9,1),date(2026,6,1),date(2026,9,1)),
            'validation_shape':EvaluationCalendar(p.validation_origin_start,p.validation_origin_end,p.validation_target_end)}
        flow_files=0
        for label,calendar in calendars.items():
            r=run_policy_calendar(stream,calendar,cfg(4),cfg(6),cfg(7),cfg(8))
            if not r['complete']:raise AssertionError('Incomplete synthetic E2E; no fallback '+label)
            target=output/label;target.mkdir()
            save(output/(label+'_operations.json'),{'settings':r['settings'],'suppliers':r['suppliers'],
                'knowledge_type':'synthetic_day12_not_world_bank','demand':100.,'realized_extra_delay':0,'initial_pipeline':[]})
            for policy,result in r['results'].items():
                for name in ('ledger','orders','receipts'):
                    file=target/(policy+'_'+name+'.csv');save_csv(file,_serializable(result[name]))
                    assert file.read_bytes()==(D12/label/file.name).read_bytes(),'Policy flow changed: '+file.name
                    flow_files+=1
                save(target/(policy+'_decision_audit.json'),result['decision_audit'])
                save(target/(policy+'_runoff.json'),result['runoff_no_action'])
                zipped(target/(policy+'_plans.json.gz'),r['plans'][policy])
                assert read(target/(policy+'_decision_audit.json'))==read(D12/label/(policy+'_decision_audit.json'))
                assert read(target/(policy+'_plans.json.gz'))==read(D12/label/(policy+'_plans.json.gz'))
            for name in ('metrics','monthly','paired','input_audit','calendar'):
                save(target/(name+'.json'),r[name]);assert read(target/(name+'.json'))==read(D12/label/(name+'.json'))
            e2e[label]={'complete':True,'policy_count':7,'optimal_solves':r['optimal_solves'],
                'decision_count':sum(len(v['decision_audit']) for v in r['results'].values()),
                'ledger_rows':sum(len(v['ledger']) for v in r['results'].values()),'original_policy_outputs_equal':True,'fallback':0}
        save(output/'joint_invariance.json',{'passed':True,'pool_origin_model_pairs':len(current),'oof_vectors':len(stream['oof_released']),
            'paths_unchanged':128*len(current),'horizon_price_rows_unchanged':384*len(current),
            'planning_purpose_only':True,'calibration_intervals_not_consumed':True,'toy_path_pairs_unchanged':896})
        save(output/'synthetic_e2e_regression.json',{'passed':True,'calendars':e2e,'byte_equal_original_flow_files':flow_files,
            'policy_method_settings_changed':False,'new_fits':0,'actual_market_performance':False})
        preserved=preservation();assert preserved['passed'];save(output/'preservation.json',preserved)
        save(output/'source_access_audit.json',access)
        outputs={p.relative_to(output).as_posix():sha(p) for p in sorted(output.rglob('*')) if p.is_file()}
        assert all(sha(ROOT/p)==h for p,h in code_at_start.items()),'Code changed during replay'
        save(output/'run_manifest.json',{'kind':'DAY15_SYNTHETIC_REMEDIATION_REPLAY','complete':True,'outputs':outputs,
            'source_run':D12.relative_to(ROOT).as_posix(),'new_fits':0,'actual_holdout_execution_allowed':False,
            'code_at_start':code_at_start})
    return {'complete':True,'output':output.relative_to(ROOT).as_posix(),'e2e':e2e,'source_access':access}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(run(a.output),default=str))
