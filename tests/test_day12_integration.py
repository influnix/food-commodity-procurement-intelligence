"""Explicit synthetic fixtures; genuine installed backends, no World Bank source reads."""

from dataclasses import replace
from datetime import date,datetime,timezone
from pathlib import Path
import json
import tomllib

import pytest

from food_procurement_intelligence.data.sequential import (
    Observation,SessionPermit,SequentialObservationStore,integration_source_guard,canonical_hash,
)
from food_procurement_intelligence.data.availability import DevelopmentPriceStore
from food_procurement_intelligence.evaluation.splits import (
    add_months,decision_at,months_between,ForecastSample,LeakageError,HoldoutLockedError,load_split_plans,
)
from food_procurement_intelligence.evaluation.sequential_runner import (
    synthetic_observations,release_publications,prepare_native_stream,EvaluationCalendar,run_policy_calendar,
)
from food_procurement_intelligence.forecasting.publisher import NativeForecastPublisher,IssuedForecast
from food_procurement_intelligence.uncertainty.sequential import SequentialOOF
from food_procurement_intelligence.policies.forecast_aware import ForecastAware
from food_procurement_intelligence.policies.risk_aware import RiskAware
from food_procurement_intelligence.optimization.order_calendar import calendar_planners
from food_procurement_intelligence.simulation.contracts import DecisionContext,SimulationSettings,Supplier
from food_procurement_intelligence.evaluation.readiness import execution_boundary,verify_candidate
from food_procurement_intelligence.evaluation.release_gate import REQUIRED_CHECKS,release_status,file_digest

ROOT=Path(__file__).resolve().parents[1]
def cfg(n):return tomllib.loads((ROOT/f'configs/day{n}.toml').read_text(encoding='utf-8'))
PLAN=load_split_plans(ROOT/'configs/splits.toml')[0]


@pytest.fixture(scope='module')
def stream():
    with integration_source_guard(ROOT) as access:
        value=prepare_native_stream(cfg(12),cfg(4),cfg(5),cfg(6),PLAN)
        assert access=={'blocked_attempts':[],'actual_source_opens':0}
        return value


def new_store():return SequentialObservationStore(SessionPermit('DAY12_NATIVE_STREAM_V1','DAY12_AR_INCREMENTS_SEED20261030'))


@pytest.mark.parametrize('kind',['real_authority','real_type','no_permit'])
def test_real_capability_disabled(kind):
    with pytest.raises(HoldoutLockedError):
        if kind=='real_authority':SessionPermit('x','x',real_data_authorized=True)
        elif kind=='real_type':SessionPermit('x','x',knowledge_type='actual_world_bank')
        else:SequentialObservationStore(None)


@pytest.mark.parametrize('method',['path','open'])
def test_source_access_guard_before_open(method):
    with integration_source_guard(ROOT) as audit:
        with pytest.raises(HoldoutLockedError):
            p=ROOT/'data/raw/DAY12_POISON_NEVER_OPEN'
            p.read_bytes() if method=='path' else p.open('rb')
    assert len(audit['blocked_attempts'])==1 and audit['actual_source_opens']==0


def test_bridge_publication_and_future_label_boundaries():
    s=new_store();values=synthetic_observations(cfg(12));release_publications(s,values,date(2024,9,1))
    with pytest.raises(LeakageError):s.feature(date(2024,9,1),date(2024,9,1))
    bridge=next(p for p in values if p.observation_month==date(2024,9,1))
    late=replace(bridge,actual_available_at=decision_at(date(2024,11,1)))
    s.advance(date(2024,10,1))
    with pytest.raises(LeakageError):s.publish(late)
    s.advance(date(2024,11,1));s.publish(late)
    assert s.feature(date(2024,9,1),date(2024,11,1))==late.price
    with pytest.raises(LeakageError):s.feature(date(2024,9,1),date(2024,10,1))
    with pytest.raises(LeakageError):s.feature(date(2025,1,1),date(2024,11,1))
    with pytest.raises(LeakageError):s.history_as_of(date(2024,12,1))


@pytest.mark.parametrize('failure',['duplicate_clock','backwards_clock','duplicate_record','backwards_publication','wrong_source'])
def test_session_rejects_invalid_release(failure):
    values=synthetic_observations(cfg(12));s=new_store();s.advance(date(2024,9,1));s.publish(values[10])
    with pytest.raises((LeakageError,HoldoutLockedError)):
        if failure=='duplicate_clock':s.advance(date(2024,9,1))
        elif failure=='backwards_clock':s.advance(date(2024,8,1))
        elif failure=='duplicate_record':s.publish(values[10])
        elif failure=='backwards_publication':s.publish(values[9])
        else:s.publish(replace(values[11],source_id='wrong'))


def test_existing_development_lock_unchanged():
    with pytest.raises(HoldoutLockedError):DevelopmentPriceStore((),PLAN).history_as_of(date(2024,9,1))


def test_native_backends_and_complete_original_seed_calendar(stream):
    assert len(stream['issued'])==236
    events=stream['events'];assert len(events)==1534 and all(e['status']=='success' for e in events)
    assert sum(e['model']=='sarimax' and e['converged'] for e in events)==118
    assert sum(e['model']=='lightgbm' and e['quantile'] is None for e in events)==354
    assert sum(e['model']=='lightgbm' and e['quantile'] in (.1,.5,.9) for e in events)==1062
    assert all(o.strftime('%Y-%m') not in cfg(12)['unissued_origins'] for _,o in stream['issued'])


def test_native_forecast_contract_and_training_proofs(stream):
    for batch in stream['issued'].values():
        assert batch.backend_kind=='native_statsmodels_lightgbm'
        proof=json.loads(batch.proof_json);o=batch.origin
        assert proof['training_origin_end']<=add_months(o,-4).strftime('%Y-%m')
        assert proof['max_training_available_at']<=decision_at(o).isoformat()
        for h,p in enumerate(batch.raw,1):
            assert p.horizon==h and p.target_month==add_months(o,h)
            assert p.record()['steps_from_latest_observation']==h+1 and p.point_prediction>0
            assert p.fit_max_label_available_at<=decision_at(o)
            assert p.record()['forecast_asof_at']==decision_at(o).isoformat()
            assert p.unit=='USD_per_metric_tonne'


def test_lgb_quantile_objectives_and_native_interval_api(stream):
    events=stream['events']
    assert all(e['objective']=='regression_l2' if e['quantile'] is None else e['objective']=='quantile' and e['alpha']==e['quantile'] for e in events if e['model']=='lightgbm')
    assert all('get_forecast(steps=4' in e['api'] for e in events if e['model']=='sarimax')


def test_complete_vector_release_timestamp_and_no_retroactive_join(stream):
    original={key:batch.digest for key,batch in stream['issued'].items()}
    for r in stream['oof_released']:
        assert add_months(r['source_origin'],3)<=add_months(r['first_released_at_origin'],-1)
        assert max(r['actual_available_at'])<=decision_at(r['first_released_at_origin'])
        label=next(k for k in ('sarimax','lightgbm') if cfg(4)[k]['model_name']==r['model'])
        assert original[(label,r['source_origin'])]==r['issuance_sha256']
    assert original=={key:batch.digest for key,batch in stream['issued'].items()}


def test_calibration_recent60_minimum24_and_separation(stream):
    for r in stream['calibration_audit']:
        assert r['count']<=60
        if r['status']=='calibrated':assert r['count']>=24
        assert max(r['selected_source_origins'],default=date.min)<=add_months(r['origin'],-4)
    for p in stream['calibrated']:
        assert p['q10'] is p['q50'] is p['q90'] is None
        assert p['base_q10'] is not None and p['base_q90'] is not None


def test_joint_128_purpose_probability_and_latest_window(stream):
    for row in stream['pool_audit']:
        assert 24<=row['pool_n']<=60 and row['evaluation_rejected']
        assert row['planning_seed']!=row['evaluation_seed']
        assert sum(r['probability'] for r in row['planning_records'] if r['horizon']==1)==1
        assert len(row['planning_records'])==384
        assert all(max(v['targets'])<=add_months(row['origin'],-1) for v in row['vectors'])


def test_pinned_seed_restore_retains96_and_rejects_changed_digest(stream):
    batches=tuple(b for (_,o),b in stream['issued'].items() if o<date(2024,9,1))
    pool=SequentialOOF(stream['store'].permit,cfg(5),cfg(6)['scenarios'],PLAN)
    with pytest.raises(LeakageError):pool.restore_seed_archive(batches,'bad')
    pool.restore_seed_archive(batches,canonical_hash([b.record() for b in batches]))
    assert len(pool.pending)==192
    s=new_store();release_publications(s,stream['observations'],date(2024,9,1));pool.tick(s,date(2024,9,1))
    assert len(pool.released)==192 and len(pool.vectors(cfg(4)['sarimax']['model_name'],date(2024,9,1)))==60
    with pytest.raises(LeakageError):pool.restore_seed_archive(batches,canonical_hash([b.record() for b in batches]))


def test_no_backfilled_forecast_or_duplicate_issue(stream):
    s=stream['store'];pool=SequentialOOF(s.permit,cfg(5),cfg(6)['scenarios'],PLAN);pool.tick(s,s.clock)
    with pytest.raises(LeakageError):pool.issue(stream['issued'][('sarimax',date(2024,9,1))],'sequential_synthetic')
    batch=stream['issued'][('sarimax',s.clock)];pool.issue(batch,'sequential_synthetic')
    with pytest.raises(LeakageError):pool.issue(batch,'sequential_synthetic')
    with pytest.raises(ValueError):pool.issue(replace(stream['issued'][('lightgbm',s.clock)],backend_kind='fake_backend'),'sequential_synthetic')


@pytest.mark.parametrize('label,expected', [('final', (22,24,21,3,132)),('validation',(36,38,35,3,216))])
def test_full_native_calendar_runner_and_accounting(stream,label,expected):
    calendar=EvaluationCalendar(date(2024,9,1),date(2026,6,1),date(2026,9,1)) if label=='final' else EvaluationCalendar(PLAN.validation_origin_start,PLAN.validation_origin_end,PLAN.validation_target_end)
    result=run_policy_calendar(stream,calendar,cfg(4),cfg(6),cfg(7),cfg(8));o,n,a,r,solves=expected
    assert result['complete'] and result['optimal_solves']==solves and len(result['results'])==7
    assert result['calendar']['origins']==o and result['calendar']['ledger_months']==n
    assert result['calendar']['active_months']==a and result['calendar']['runoff_months']==r
    for row in result['results'].values():
        assert len(row['decision_audit'])==o and len(row['ledger'])==n
        assert all(x['new_order_quantity']==0 for x in row['ledger'][-3:])
        assert row['ledger'][-1]['outstanding_quantity']==0 and all(x['terminal_cost']==0 for x in row['ledger'][:-1])
        assert len(row['orders'])==len(row['receipts'])
    for model in ('sarimax','lightgbm'):
        assert [p['planning_scenarios'] for p in result['plans']['rn_'+model]]==[p['planning_scenarios'] for p in result['plans']['ra_'+model]]


def test_native_forecasts_and_orders_ignore_unpublished_future(stream):
    origin=date(2024,9,1);values=stream['observations'];changed=tuple(replace(p,price=p.price*10) if p.observation_month>=origin else p for p in values)
    candidates=tuple(ForecastSample(o,(1,2,3),tuple(add_months(o,h) for h in (1,2,3))) for o in months_between(date(2001,2,1),origin))
    outputs=[]
    for records in (values,changed):
        s=new_store();release_publications(s,records,origin);publisher=NativeForecastPublisher(cfg(4),candidates)
        batches=publisher.publish(s,origin);out={b.label:b.record() for b in batches};orders=[]
        seed=tuple(b for (_,o),b in stream['issued'].items() if o<origin)
        pool=SequentialOOF(s.permit,cfg(5),cfg(6)['scenarios'],PLAN)
        pool.restore_seed_archive(seed,canonical_hash([b.record() for b in seed]));pool.tick(s,origin)
        d6=cfg(6);settings=SimulationSettings(**{k:d6['simulation'][k] for k in SimulationSettings.__dataclass_fields__});suppliers=tuple(Supplier(**r) for r in d6['suppliers'])
        context=DecisionContext(origin,date(2026,9,1),200.,100.,suppliers,(),s.history_as_of(origin));point,risk=calendar_planners(date(2026,6,1))
        for b in batches:
            orders.append(ForecastAware(lambda _,b=b:b.points(),settings,cfg(7)['lp'],point)(context))
            for weight in (0.,.5):
                bundle,_=pool.scenarios(b,'planning')
                orders.append(RiskAware(lambda _:bundle,settings,cfg(7)['lp'],{**cfg(8)['risk'],'risk_weight':weight},risk)(context))
        outputs.append((out,orders))
    assert outputs[0]==outputs[1]


def test_native_failure_is_not_a_success_or_fallback(monkeypatch):
    import food_procurement_intelligence.forecasting.publisher as module
    monkeypatch.setattr(module,'sarimax_intervals',lambda *a:((),[{'status':'failed','failure_reason':'forced_nonconvergence'}]))
    s=new_store();release_publications(s,synthetic_observations(cfg(12)),date(2024,9,1))
    candidates=(ForecastSample(date(2024,5,1),(1,2,3),(date(2024,6,1),date(2024,7,1),date(2024,8,1))),)
    with pytest.raises(RuntimeError,match='Native fit failed'):NativeForecastPublisher(cfg(4),candidates).publish(s,s.clock)


def test_incomplete_issuance_is_rejected(stream):
    batch=next(iter(stream['issued'].values()))
    with pytest.raises(ValueError):replace(batch,raw=batch.raw[:2])


def test_training_unreleased_vector_fails():
    s=new_store();release_publications(s,synthetic_observations(cfg(12)),date(2024,9,1))
    future=ForecastSample(date(2024,6,1),(1,2,3),(date(2024,7,1),date(2024,8,1),date(2024,9,1)))
    with pytest.raises(LeakageError):s.training_targets(future,s.clock)


@pytest.mark.parametrize('now,mature',[('2026-10-30T14:00:00+00:00',False),('2026-10-31T23:59:58+00:00',False),('2026-10-31T23:59:59+00:00',True)])
def test_technical_ready_never_implies_real_authorization(now,mature):
    value=execution_boundary({k:'PASS' for k in REQUIRED_CHECKS},datetime.fromisoformat(now),datetime.fromisoformat(cfg(12)['publication_maturity_utc']))
    assert value['technical_readiness']=='READY' and value['target_publication_maturity']==mature
    assert not value['explicit_user_authorization'] and not value['actual_holdout_execution_allowed'] and value['holdout_locked']


@pytest.mark.parametrize('status',['READY','NOT_READY','BLOCKED'])
def test_release_states_preserve_original_meanings(status):
    checks={k:'PASS' for k in REQUIRED_CHECKS}
    if status=='NOT_READY':checks['production_new_origin_backend_integration']='NOT_VERIFIED'
    value=release_status(checks,['integrity'] if status=='BLOCKED' else [])
    assert value['status']==status and not value['actual_holdout_execution_allowed']


@pytest.mark.parametrize('tamper',['none','config','old_digest','manifest'])
def test_candidate_hash_and_old_approval_boundary(tmp_path,tamper):
    p=tmp_path/'config.txt';p.write_text('fixed',encoding='utf-8')
    pinned={'config.txt':file_digest(p)};m={'contract_files':pinned,'code_files':pinned,'metadata_files':pinned,
        'day11_baseline_sha256':'baseline','release_gate':release_status({k:'PASS' for k in REQUIRED_CHECKS}),
        'readiness':{'actual_holdout_execution_allowed':False,'holdout_locked':True}}
    path=tmp_path/'candidate.json';path.write_text(json.dumps(m),encoding='utf-8');digest=file_digest(path)
    if tamper=='config':p.write_text('changed',encoding='utf-8')
    elif tamper=='old_digest':digest='163a74d3387743b882651e98fa434d1cc4113d3e5eac98e3fde08e53e24b78be'
    elif tamper=='manifest':path.write_text(path.read_text()+' ',encoding='utf-8')
    gate=verify_candidate(path,digest,tmp_path)
    assert gate['status']==('READY' if tamper=='none' else 'BLOCKED') and gate['holdout_locked']


def test_missing_pool_explicit_failure(stream):
    s=stream['store'];pool=SequentialOOF(s.permit,cfg(5),cfg(6)['scenarios'],PLAN);pool.tick(s,s.clock)
    with pytest.raises(ValueError,match='Insufficient'):pool.scenarios(stream['issued'][('sarimax',s.clock)],'planning')


def test_saved_issuance_reload_is_immutable_and_hash_checked(stream,tmp_path):
    from food_procurement_intelligence.forecasting.publisher import load_issued_forecast
    batch=stream['issued'][('sarimax',date(2024,9,1))];p=tmp_path/'issued.json'
    record=batch.record();p.write_text(json.dumps({'issued_sha256':batch.digest,**record}),encoding='utf-8')
    assert load_issued_forecast(p,batch.digest)==batch
    record['raw'][0]['point_prediction']=1.
    assert batch.raw[0].point_prediction!=1.
    p.write_text(json.dumps({'issued_sha256':batch.digest,**record}),encoding='utf-8')
    with pytest.raises(LeakageError):load_issued_forecast(p,batch.digest)


def test_partial_policy_failure_cannot_be_full_comparison(stream,monkeypatch):
    import food_procurement_intelligence.evaluation.sequential_runner as module
    original=module.make_policy
    def maker(name,*args):
        if name=='rn_sarimax':
            def fail(context):raise RuntimeError('forced planner failure')
            return fail
        return original(name,*args)
    monkeypatch.setattr(module,'make_policy',maker)
    result=run_policy_calendar(stream,EvaluationCalendar(date(2024,9,1),date(2026,6,1),date(2026,9,1)),cfg(4),cfg(6),cfg(7),cfg(8))
    assert not result['complete'] and result['metrics']==result['paired']==[]
    assert not result['results']['rn_sarimax']['complete'] and result['fallback_count']==0


def test_delayed_third_target_blocks_entire_seed_vector_until_published(stream):
    values=tuple(replace(p,actual_available_at=decision_at(date(2024,10,1))) if p.observation_month==date(2024,8,1) else p for p in stream['observations'])
    s=new_store();release_publications(s,values,date(2024,9,1))
    seed=tuple(b for (_,o),b in stream['issued'].items() if o<date(2024,9,1))
    pool=SequentialOOF(s.permit,cfg(5),cfg(6)['scenarios'],PLAN)
    pool.restore_seed_archive(seed,canonical_hash([b.record() for b in seed]));pool.tick(s,date(2024,9,1))
    model=cfg(4)['sarimax']['model_name'];key=model,date(2024,5,1)
    assert key in pool.pending and key not in pool.released
    release_publications(s,values,date(2024,10,1));pool.tick(s,date(2024,10,1))
    assert key in pool.released and key not in pool.pending
    assert pool.released[key]['first_released_at_origin']==date(2024,10,1)


@pytest.mark.parametrize('mutation',['knowledge_type','source_id','fake_backend','session_id'])
def test_current_calibration_and_scenario_batches_cannot_cross_session(stream,mutation):
    s=stream['store'];pool=SequentialOOF(s.permit,cfg(5),cfg(6)['scenarios'],PLAN);pool.tick(s,s.clock)
    batch=stream['issued'][('sarimax',s.clock)]
    if mutation=='knowledge_type':batch=replace(batch,knowledge_type='real_world_bank')
    elif mutation=='fake_backend':batch=replace(batch,backend_kind='fake_backend')
    else:
        proof=json.loads(batch.proof_json);proof['source_session' if mutation=='session_id' else 'source_id']='wrong';batch=replace(batch,proof_json=json.dumps(proof,sort_keys=True))
    with pytest.raises(LeakageError):pool.calibrate(batch)
    with pytest.raises(LeakageError):pool.scenarios(batch,'planning')
