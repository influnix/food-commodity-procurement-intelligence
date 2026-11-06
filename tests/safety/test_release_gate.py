"""Day11 tagged fixtures and access probes. No World Bank prices or real model training."""

import builtins
from copy import deepcopy
from dataclasses import replace
from datetime import date
import io
import json
import os
from pathlib import Path
import tomllib

import pytest

from food_procurement_intelligence.evaluation.preflight_runner import validate_contract
from food_procurement_intelligence.evaluation.scenario_diagnostics import _serializable
from food_procurement_intelligence.evaluation.pre_holdout_audit import final_calendar,pipeline_audit,baseline_evidence
from food_procurement_intelligence.evaluation.release_gate import (
    REQUIRED_CHECKS,source_read_guard,release_status,deny_real_execution,file_digest,verify_frozen_manifest,preservation_check,
)
from food_procurement_intelligence.evaluation.synthetic_preflight import (
    SyntheticAsOfStore,fixture_observations,run_synthetic_preflight,FakeSARIMAX,stub_points,synthetic_pool,
)
from food_procurement_intelligence.evaluation.splits import (
    ForecastSample,HoldoutLockedError,LeakageError,add_months,decision_at,months_between,
)
from food_procurement_intelligence.forecasting.sarimax import fit_predict
from food_procurement_intelligence.features.price import build_features,FeatureSpec
from food_procurement_intelligence.evaluation.policy_backtest import run_historical_policy,paired_comparison
from food_procurement_intelligence.forecasting.common import ModelPrediction
from food_procurement_intelligence.optimization.deterministic import PlanResult
from food_procurement_intelligence.optimization.order_calendar import calendar_planners
from food_procurement_intelligence.policies.forecast_aware import ForecastAware
from food_procurement_intelligence.simulation.contracts import DecisionContext,ToyWorld
from food_procurement_intelligence.data.availability import VisiblePrice

ROOT=next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
def config(name):return tomllib.loads((ROOT/'configs'/name).read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def preflight():
    with source_read_guard(ROOT) as guard:
        result=run_synthetic_preflight(config('evaluation/final.toml'),config('forecasting/models.toml'),config('scenarios/joint_and_operations.toml'),config('procurement/deterministic.toml'),config('procurement/risk.toml'))
        assert guard=={'blocked_attempts':[],'actual_source_opens':0}
        return result


@pytest.mark.parametrize('status',['READY','NOT_READY','BLOCKED'])
def test_gate_status_never_grants_access(status):
    checks={k:'PASS' for k in REQUIRED_CHECKS}
    if status=='NOT_READY':checks['tests_all_pass']='NOT_VERIFIED'
    gate=release_status(checks,['tamper'] if status=='BLOCKED' else [])
    assert gate['status']==status and gate['holdout_locked'] and not gate['actual_holdout_execution_allowed']
    with pytest.raises(HoldoutLockedError):deny_real_execution()


def test_missing_or_invalid_gate_evidence_fails_closed():
    assert release_status({})['status']=='NOT_READY'
    assert release_status({'tests_all_pass':'INVALID'})['status']=='BLOCKED'


@pytest.mark.parametrize('method',['builtin','path','io','os'])
def test_source_access_probe_is_denied_before_reader(method):
    path=ROOT/'data/raw/DAY11_POISON_DO_NOT_OPEN'
    with source_read_guard(ROOT) as audit:
        with pytest.raises(HoldoutLockedError):
            if method=='builtin':builtins.open(path,'rb')
            elif method=='path':path.read_bytes()
            elif method=='io':io.open(path,'rb')
            else:os.open(path,os.O_RDONLY)
    assert audit['actual_source_opens']==0 and len(audit['blocked_attempts'])==1


def test_poison_reader_is_not_a_fixture():
    class PoisonReader:
        def __getattr__(self,name):raise AssertionError('Real reader must not be inspected')
    with pytest.raises(ValueError,match='Synthetic'):SyntheticAsOfStore((PoisonReader(),))


def test_calendar_date_only_and_last_targets():
    c=final_calendar(config('evaluation/final.toml'),ROOT)
    assert len(c['origins'])==22 and len(c['ledger_months'])==24
    assert c['last_origin_targets']==['2026-07','2026-08','2026-09'] and not c['values_read']
    assert c['first_price_cutoff']=='2024-08' and c['runoff_months']==['2026-07','2026-08','2026-09']


@pytest.mark.parametrize('field,value',[('decision_count',23),('last_origin','2026-07'),('bridge_month','2024-08')])
def test_calendar_rejects_split_or_count_changes(field,value):
    c=config('evaluation/final.toml');c['calendar'][field]=value
    with pytest.raises(ValueError):final_calendar(c,ROOT)


@pytest.mark.parametrize('section,field,value',[(None,'holdout_locked',False),('rolling','ra_lambda',.8),('metrics','choose_single_winner',True)])
def test_final_contract_rejects_new_selection(section,field,value):
    c=config('evaluation/final.toml');target=c if section is None else c[section];target[field]=value
    with pytest.raises(ValueError):validate_contract(c)


def test_bridge_and_delayed_publication():
    data=fixture_observations(date(2024,8,1),date(2024,10,1));store=SyntheticAsOfStore(data)
    assert max(p.month for p in store.history_as_of(date(2024,9,1)))==date(2024,8,1)
    assert max(p.month for p in store.history_as_of(date(2024,10,1)))==date(2024,9,1)
    store=SyntheticAsOfStore(tuple(replace(p,available_at=decision_at(date(2024,11,1))) if p.observation_month==date(2024,9,1) else p for p in data))
    with pytest.raises(LeakageError):store.feature(date(2024,9,1),date(2024,10,1))


def test_training_boundary_rejects_unmature_vector():
    store=SyntheticAsOfStore(fixture_observations(date(2023,1,1),date(2025,1,1)))
    def sample(o):return ForecastSample(o,(1,2,3),tuple(add_months(o,h) for h in (1,2,3)))
    store.assert_training_samples_available((sample(date(2024,5,1)),),date(2024,9,1))
    with pytest.raises(LeakageError):store.assert_training_samples_available((sample(date(2024,6,1)),),date(2024,9,1))


def test_sarimax_step_234_with_distinct_fake_outputs():
    class Distinct(FakeSARIMAX):
        def forecast(self,steps):assert steps==4;return [10.,20.,30.,40.]
    store=SyntheticAsOfStore(fixture_observations(date(2000,1,1),date(2026,9,1)))
    sample=ForecastSample(date(2024,9,1),(1,2,3),(date(2024,10,1),date(2024,11,1),date(2024,12,1)))
    fold=fit_predict(store,sample,config('forecasting/models.toml')['sarimax'],Distinct)
    assert [p.predicted_price for p in fold.predictions]==[20.,30.,40.]


def test_future_fixture_mutation_keeps_features_forecast_and_current_order():
    origin=date(2024,9,1);observations=fixture_observations(date(2000,1,1),date(2026,9,1))
    modified=tuple(replace(p,price=p.price*100) if p.observation_month>=origin else p for p in observations)
    stores=[SyntheticAsOfStore(v) for v in (observations,modified)]
    sample=ForecastSample(origin,(1,2,3),tuple(add_months(origin,h) for h in (1,2,3)))
    from food_procurement_intelligence.simulation.contracts import SimulationSettings,Supplier
    d6=config('scenarios/joint_and_operations.toml');settings=SimulationSettings(**{k:d6['simulation'][k] for k in SimulationSettings.__dataclass_fields__})
    suppliers=tuple(Supplier(**s) for s in d6['suppliers']);planner,_=calendar_planners(date(2026,6,1));out=[]
    for store in stores:
        points=fit_predict(store,sample,config('forecasting/models.toml')['sarimax'],FakeSARIMAX).predictions
        features=build_features(store,sample,FeatureSpec())
        context=DecisionContext(origin,date(2026,9,1),200.,100.,suppliers,(),store.history_as_of(origin))
        policy=ForecastAware(lambda _:points,settings,config('procurement/deterministic.toml')['lp'],planner)
        out.append((features,points,policy(context)))
    assert out[0]==out[1]


def test_synthetic_rolling_refit_maturity(preflight):
    assert len(preflight['fit_audit'])==44
    for r in preflight['fit_audit']:
        assert r['history_end']==r['feature_cutoff']==add_months(r['origin'],-1)
        assert r['latest_training_origin']==add_months(r['origin'],-4)
        assert r['max_training_available_at']<=decision_at(r['origin'])
        assert r['backend']=='injected_fake_no_parameter_training'


def test_synthetic_joint_pool_and_purpose(preflight):
    for r in preflight['pool_audit']:
        assert 24<=r['joint_pool_count']<=60
        for v in r['vector_proofs']:
            assert max(v['targets'])<=add_months(r['origin'],-1)
            assert max(v['available_at'])<=decision_at(r['origin']) and v['fit_cutoff']<min(v['targets'])
    assert all(r['evaluation_rejected'] and r['probability_sum']==1 for r in preflight['purpose_checks'])


def test_delayed_third_target_excludes_joint_vector():
    origin=date(2024,9,1);past=date(2024,5,1);c=config('evaluation/final.toml');c['rolling']['minimum_joint_vectors']=1
    store=SyntheticAsOfStore(fixture_observations(date(2023,1,1),date(2024,12,1)))
    points=stub_points(store,past,'fixture',False);current=stub_points(store,origin,'fixture',False)
    issued={('fixture',past):points}
    assert synthetic_pool(store,issued,origin,current,'fixture',c)[1]['joint_pool_count']==1
    data=tuple(replace(p,available_at=decision_at(date(2024,10,1))) if p.observation_month==date(2024,8,1) else p for p in store._values.values())
    with pytest.raises(ValueError,match='Insufficient'):synthetic_pool(SyntheticAsOfStore(data),issued,origin,current,'fixture',c)


def test_seven_policies_runoff_terminal_and_accounting(preflight):
    assert len(preflight['results'])==7 and preflight['summary']['optimal_solves']==132
    for result in preflight['results'].values():
        assert result['complete'] and len(result['ledger'])==24 and len(result['decision_audit'])==22
        assert sum(r['period']=='active' for r in result['ledger'])==21
        assert all(r['new_order_quantity']==0 for r in result['ledger'][-3:])
        assert all(r['terminal_cost']==0 for r in result['ledger'][:-1])
        assert result['ledger'][-1]['outstanding_quantity']==0
        assert len(result['orders'])==len(result['receipts'])


def test_rn_ra_share_exact_planning_inputs(preflight):
    for model in ('sarimax','lightgbm'):
        assert [r['planning_scenarios'] for r in preflight['plans']['rn_'+model]]==[r['planning_scenarios'] for r in preflight['plans']['ra_'+model]]


@pytest.mark.parametrize('kind',['rn','ra'])
def test_future_mutation_keeps_joint_scenarios_and_risk_order(preflight,kind):
    from food_procurement_intelligence.policies.risk_aware import RiskAware
    origin=date(2024,9,1);original=preflight['observations'];c=config('evaluation/final.toml')
    changed=tuple(replace(p,price=p.price*100) if p.observation_month>=origin else p for p in original)
    _,planner=calendar_planners(date(2026,6,1));out=[]
    for values in (original,changed):
        store=SyntheticAsOfStore(values)
        issued={('fixture',past):stub_points(store,past,'fixture',False) for past in months_between(add_months(origin,-63),add_months(origin,-1))}
        current=stub_points(store,origin,'fixture',False)
        bundles,_=synthetic_pool(store,issued,origin,current,'fixture',c)
        context=DecisionContext(origin,date(2026,9,1),200.,100.,preflight['suppliers'],(),store.history_as_of(origin))
        risk={**config('procurement/risk.toml')['risk'],'risk_weight':0. if kind=='rn' else .5}
        policy=RiskAware(lambda _:bundles['planning'],preflight['settings'],config('procurement/deterministic.toml')['lp'],risk,planner)
        out.append((bundles['planning'].records(),policy(context)))
    assert out[0]==out[1]


def test_existing_development_store_stays_locked():
    from food_procurement_intelligence.data.availability import DevelopmentPriceStore
    from food_procurement_intelligence.evaluation.splits import load_split_plans
    plan,_=load_split_plans(ROOT/'configs/evaluation/splits.toml');store=DevelopmentPriceStore((),plan)
    with pytest.raises(HoldoutLockedError):store.history_as_of(date(2024,9,1))


def test_solver_failure_not_hidden_or_compared(preflight):
    r=preflight;first=date(2024,9,1);start=date(2024,10,1);end=date(2026,9,1)
    prices=tuple(VisiblePrice(p.observation_month,p.price,'USD_per_metric_tonne',p.available_at) for p in r['observations'] if p.observation_month>=start)
    world=ToyWorld('DAY11_FAILURE_FIXTURE',start,end,prices,tuple((m,100.) for m in months_between(start,end)))
    policy=ForecastAware(lambda o:(),r['settings'],config('procurement/deterministic.toml')['lp'],lambda *a:PlanResult('INFEASIBLE'))
    result=run_historical_policy(world,r['settings'],r['suppliers'],policy,first,date(2026,6,1),lambda o:())
    assert not result['complete'] and result['ledger']==[] and result['failure']['fallback'] is None
    assert result['failure']['first_failure_origin']==first
    with pytest.raises(ValueError):paired_comparison({'broken':result},())


@pytest.fixture
def frozen(tmp_path):
    p=tmp_path/'config.txt';p.write_text('frozen',encoding='utf-8')
    manifest={'schema_version':1,'contract_files':{'config.txt':file_digest(p)},'code_files':{'config.txt':file_digest(p)},
        'metadata_files':{'config.txt':file_digest(p)},'contract':{'holdout_locked':True},'calendar':{'count':22},
        'source_metadata':{'reused':True},'environment':{'solver':'fixture'},'test_status':{'passed':True},
        'failure_policy':'abort','release_gate':release_status({k:'PASS' for k in REQUIRED_CHECKS}),'approval_binding':'external digest'}
    path=tmp_path/'manifest.json';path.write_text(json.dumps(manifest),encoding='utf-8')
    return tmp_path,path,manifest


def test_freeze_config_change_is_blocked(frozen):
    root,path,_=frozen;pinned=file_digest(path)
    assert verify_frozen_manifest(path,pinned,root)['status']=='READY'
    (root/'config.txt').write_text('changed',encoding='utf-8')
    assert verify_frozen_manifest(path,pinned,root)['status']=='BLOCKED'


def test_freeze_manifest_digest_change_requires_new_approval(frozen):
    root,path,_=frozen;pinned=file_digest(path);path.write_text(path.read_text()+' ',encoding='utf-8')
    assert verify_frozen_manifest(path,pinned,root)['status']=='BLOCKED'


def test_incomplete_manifest_is_blocked(frozen):
    root,path,m=frozen;del m['source_metadata'];path.write_text(json.dumps(m),encoding='utf-8')
    assert verify_frozen_manifest(path,file_digest(path),root)['status']=='BLOCKED'


def test_manifest_cannot_request_source_bytes(frozen):
    root,path,m=frozen;m['metadata_files']={'data/raw/DO_NOT_OPEN':'poison'};path.write_text(json.dumps(m),encoding='utf-8')
    with source_read_guard(root) as guard:
        assert verify_frozen_manifest(path,file_digest(path),root)['status']=='BLOCKED'
        assert guard['blocked_attempts']==[]


def test_production_gaps_and_prior_baseline_evidence():
    audit=pipeline_audit(ROOT)
    assert not audit['production_ready'] and len(audit['production_findings'])==9
    assert baseline_evidence(ROOT)['flow_files_rechecked_without_source_prices']==21


def test_existing_files_preserved_without_raw_hashing():
    snapshot=json.loads((ROOT/'artifacts/day11/preservation_before.json').read_text(encoding='utf-8'))
    # Day15 explicitly authorizes CR-02 code remediation, never old artifact edits.
    import sys
    sys.path.insert(0,str(ROOT/'scripts/compatibility'))
    from scripts.compatibility.replay_support import scoped_legacy_snapshot
    scoped,changed=scoped_legacy_snapshot(snapshot)
    with source_read_guard(ROOT) as guard:result=preservation_check(ROOT,scoped)
    assert len(snapshot['sha256'])==3411 and result['hash_verified_files']+len(changed)==3411
    assert result['metadata_only_files']==58
    assert changed==['src/food_procurement_intelligence/uncertainty/contracts.py']
    assert guard['blocked_attempts']==[] and not result['raw_price_bytes_rehashed']
