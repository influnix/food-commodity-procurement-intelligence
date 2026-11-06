"""Synthetic hand accounts and overrides; no real market prices or network."""

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
import tomllib

import pytest

from food_procurement_intelligence.data.availability import VisiblePrice
from food_procurement_intelligence.data.world_bank import assumed_available_at
from food_procurement_intelligence.evaluation.historical_prices import HistoricalEvaluationWorld
from food_procurement_intelligence.evaluation.policy_backtest import run_historical_policy,paired_comparison
from food_procurement_intelligence.evaluation.sensitivity import cell_overrides,rank_policies,SETTING_AXES,failure_status,save_gzip,read_gzip,validate_grid,stability_analysis,baseline_gate
from food_procurement_intelligence.evaluation.splits import add_months,months_between,LeakageError,HoldoutLockedError
from food_procurement_intelligence.optimization.order_calendar import calendar_planners
from food_procurement_intelligence.optimization.scenario_lp import solve_risk_plan
from food_procurement_intelligence.optimization.toy_cvar import synthetic_bundle
from food_procurement_intelligence.forecasting.common import ModelPrediction
from food_procurement_intelligence.policies.fixed import FixedProcurement
from food_procurement_intelligence.policies.forecast_aware import ForecastAware
from food_procurement_intelligence.policies.risk_aware import RiskAware
from food_procurement_intelligence.simulation.contracts import Supplier,SimulationSettings,DecisionContext

ROOT=next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
LP=tomllib.loads((ROOT/'configs/procurement/deterministic.toml').read_text())['lp']
RISK=tomllib.loads((ROOT/'configs/procurement/risk.toml').read_text())['risk']


@pytest.fixture
def toy():
    months=months_between(date(2022,1,1),date(2022,6,1))
    prices=tuple(VisiblePrice(m,100.,'USD_per_metric_tonne',datetime.fromisoformat(assumed_available_at(m))) for m in months)
    world=HistoricalEvaluationWorld('TOY_NOT_REAL',months[0],months[-1],prices,tuple((m,100.) for m in months))
    settings=SimulationSettings(100.,200.,400.,3.,1500.,1.,200.,9.)
    suppliers=(Supplier('A',.02,2,80.),Supplier('B',.08,1,100.))
    return settings,suppliers,world


def run(toy,cell,policy=None):
    settings,suppliers,world=cell_overrides(cell,*toy)
    return run_historical_policy(world,settings,suppliers,policy or FixedProcurement(),date(2021,12,1),date(2022,3,1),lambda o:())


@pytest.mark.parametrize('axis,value,expected',[
    ('baseline',0,44820.),('holding_cost',6.,46560.),('terminal_weight',0.,43020.),('terminal_weight',30.,49020.),
    ('initial_inventory',100.,193320.),('initial_inventory',300.,45720.),('supplier_b_capacity',60.,44820.)])
def test_override_fixed_independent_hand_accounts(toy,axis,value,expected):
    result=run(toy,{'id':'toy','axis':axis,'value':value})
    assert result['complete'] and result['summary']['total_cost']==expected
    assert all(r['new_order_quantity']==0 for r in result['ledger'] if r['period']=='runoff')
    assert result['summary']['terminal_outstanding_tonnes']==0


@pytest.mark.parametrize('penalty,expected',[(750.,302100.),(3000.,1202100.)])
def test_shortage_penalty_engine_hand_arithmetic(toy,penalty,expected):
    result=run(toy,{'id':'toy','axis':'unmet_penalty','value':penalty},lambda _:())
    assert result['complete'] and result['summary']['total_cost']==expected
    assert result['summary']['unmet_demand']==400.


@pytest.mark.parametrize('kind',['fa','rn','ra'])
def test_capacity_override_reaches_solver_context_and_engine(toy,kind):
    cell={'id':'cap','axis':'supplier_b_capacity','value':60.}
    settings,suppliers,world=cell_overrides(cell,*toy)
    settings=replace(settings,initial_inventory_tonnes=0.)
    point,risk=calendar_planners(date(2022,3,1))
    def points(o):return tuple(ModelPrediction(o,add_months(o,-1),add_months(o,h),h,100.,'TOY') for h in (1,2,3))
    policy=ForecastAware(points,settings,LP,point) if kind=='fa' else RiskAware(lambda o:synthetic_bundle(o,[(100.,100.,100.)]*128),settings,LP,
        {**RISK,'risk_weight':0. if kind=='rn' else .5},risk)
    result=run_historical_policy(world,settings,suppliers,policy,date(2021,12,1),date(2022,3,1),lambda _:())
    assert result['complete']
    assert result['decision_audit'][0]['context']['suppliers'][1]['monthly_capacity_tonnes']==60.
    assert policy.solutions[0].variables['q']['B|2021-12']==pytest.approx(60.)
    assert all(o['quantity_tonnes']<=60.+1e-7 for o in result['orders'] if o['supplier_id']=='B')


@pytest.mark.parametrize('axis,value,component,coefficient',[
    ('holding_cost',6.,'holding',6.),('unmet_penalty',750.,'unmet',750.),('terminal_weight',30.,'planning_terminal',30.)])
def test_cost_override_solver_components_use_same_coefficients(toy,axis,value,component,coefficient):
    settings,suppliers,world=cell_overrides({'id':'cost','axis':axis,'value':value},*toy)
    origin=date(2021,12,1);ctx=DecisionContext(origin,world.end,200.,100.,suppliers,(),())
    bundle=synthetic_bundle(origin,[(100.,100.,100.)]*128)
    result=solve_risk_plan(ctx,bundle,settings,LP,RISK)
    assert result.accepted
    variable={'holding':'I','unmet':'U','planning_terminal':'deviation'}[component]
    assert result.components[component]==pytest.approx(coefficient*sum(result.variables[variable].values()))


@pytest.mark.parametrize('axis,value',[('demand_stress',120.),('delay_stress',1)])
def test_stress_keeps_plans_public_and_cohort_keys_fixed(toy,axis,value):
    settings,suppliers,world=cell_overrides({'id':'stress','axis':axis,'value':value},*toy)
    assert settings.planned_demand_tonnes==100.
    if axis=='demand_stress':assert [d for _,d in world.realized_demands]==[120,120,120,100,100,100]
    else:assert world.delays==tuple(('A',date(2022,m,1),1) for m in (1,2,3))
    seen=[]
    def spy(ctx):
        assert ctx.planned_demand_tonnes==100.
        assert not any(hasattr(ctx,k) for k in ('realized_demands','delays','actual_arrival'))
        assert all(not hasattr(o,'actual_arrival') for o in ctx.outstanding_orders)
        seen.append(ctx)
        return FixedProcurement()(ctx)
    result=run(toy,{'id':'stress','axis':axis,'value':value},spy)
    assert result['complete'] and len(seen)==4
    assert run(toy,{'id':'stress','axis':axis,'value':value})['receipts']==result['receipts']


def test_demand_stress_inventory_lost_sales_and_delay_receipt_month(toy):
    demand=run(toy,{'id':'demand','axis':'demand_stress','value':120.})
    assert demand['summary']['unmet_demand']==60.
    delay=run(toy,{'id':'delay','axis':'delay_stress','value':1})
    assert delay['complete']
    receipt=next(r for r in delay['receipts'] if r['supplier_id']=='A' and r['order_month']==date(2022,1,1))
    assert receipt['receipt_month']==date(2022,4,1) and receipt['procurement_cost']==8160.
    for result in (demand,delay):
        for r in result['ledger']:
            assert r['beginning_inventory']+r['received_quantity']==pytest.approx(r['fulfilled_demand']+r['disposed_quantity']+r['ending_inventory'])


def test_ranks_ties_service_and_incomplete_prohibition():
    rows=[{'policy':'A','total_cost':100.,'fill_rate':.9},{'policy':'B','total_cost':100.,'fill_rate':1.},
          {'policy':'C','total_cost':110.,'fill_rate':1.}]
    ranked=rank_policies(rows,True)
    assert [r['rank'] for r in ranked]==[1,1,3]
    assert ranked[0]['cost_service_dominated'] and not ranked[1]['cost_service_dominated']
    assert rank_policies(rows,False)==[]


def test_failure_categories_and_unsupported_contract_remain_explicit(toy):
    result=run(toy,{'id':'too_small','axis':'supplier_b_capacity','value':10.})
    assert not result['complete'] and failure_status(result,FixedProcurement())=='UNSUPPORTED_CONTRACT'
    with pytest.raises(ValueError):paired_comparison({'bad':result},(('bad','bad','bad'),))
    with pytest.raises(ValueError):cell_overrides({'id':'bad','axis':'new_unknown'},*toy)


@pytest.mark.parametrize('horizon',[2,6])
def test_native_horizon_guard_is_audited_not_silently_relabeled(toy,horizon):
    settings,suppliers,world=toy;origin=date(2021,12,1)
    result=solve_risk_plan(DecisionContext(origin,world.end,200.,100.,suppliers,(),()),
        synthetic_bundle(origin,[(100.,100.,100.)]*128),settings,{**LP,'horizon_months':horizon},RISK)
    assert result.status=='INVALID_INPUT' and not result.accepted


def test_lag_two_cannot_relabel_stored_lag_one_forecast():
    o=date(2021,12,1)
    with pytest.raises(ValueError):ModelPrediction(o,add_months(o,-2),add_months(o,1),1,100.,'TOY')


def test_compressed_diagnostics_are_deterministic(tmp_path):
    a,b=tmp_path/'a.gz',tmp_path/'b.gz'
    save_gzip(a,{'price':'SYNTHETIC','values':[1,2,3]});save_gzip(b,{'price':'SYNTHETIC','values':[1,2,3]})
    assert a.read_bytes()==b.read_bytes() and read_gzip(a)==read_gzip(b)


def test_grid_oat_exactly_one_operational_change_and_ids(toy):
    from dataclasses import asdict
    config=tomllib.loads((ROOT/'configs/evaluation/sensitivity.toml').read_text())
    validate_grid(config)
    for cell in config['cells']:
        if cell['kind']!='oat':continue
        settings,suppliers,world=cell_overrides(cell,*toy)
        changes=sum(asdict(settings)[k]!=asdict(toy[0])[k] for k in asdict(settings))
        changes+=sum(asdict(s)[k]!=asdict(original)[k] for s,original in zip(suppliers,toy[1]) for k in asdict(s))
        assert changes==1 and world.prices==toy[2].prices and world.realized_demands==toy[2].realized_demands and world.delays==toy[2].delays
    bad={**config,'cells':[config['cells'][0]]*14}
    with pytest.raises(ValueError):validate_grid(bad)


def test_rank_reversal_and_near_tie_calculation():
    from food_procurement_intelligence.evaluation.historical_backtest import POLICIES
    def cell(name,reverse=False):
        metrics=[{'policy':p,'total_cost':1000.+(6-i if reverse else i),'fill_rate':1.} for i,p in enumerate(POLICIES)]
        return {'id':name,'status':'COMPLETE','ranks':rank_policies(metrics,True)}
    result=stability_analysis([cell('baseline'),cell('reversed',True)])
    assert result['cells'][0]['winners']==['fixed'] and result['cells'][1]['winners']==['ra_lightgbm']
    assert len([r for r in result['pair_order_changes'] if r['strict_reversal']])==21


def test_baseline_gate_rejects_any_changed_flow_or_metric(tmp_path):
    import json
    from food_procurement_intelligence.evaluation.historical_backtest import POLICIES
    from food_procurement_intelligence.evaluation.policy_backtest import COST_KEYS
    a,b=tmp_path/'new',tmp_path/'reference';a.mkdir();b.mkdir()
    metrics=[]
    for policy in POLICIES:
        for kind in ('orders','receipts','ledger'):
            for p in (a,b):(p/(policy+'_'+kind+'.csv')).write_text('TOY_NOT_REAL\n')
        for period in ('full','active','runoff'):
            metrics.append({'policy':policy,'period':period,**{k:0. for k in (*COST_KEYS,'realized_demand','fulfilled_demand','unmet_demand','fill_rate','stockout_months','average_inventory','ending_inventory')}})
    (a/'metrics.json').write_text(json.dumps(metrics));(b/'policy_metrics.json').write_text(json.dumps(metrics));(b/'manifest.json').write_text('{}')
    assert baseline_gate(a,b)['passed']
    (a/'fixed_orders.csv').write_text('CHANGED_TOY\n')
    with pytest.raises(ArithmeticError):baseline_gate(a,b)
    (a/'fixed_orders.csv').write_text('TOY_NOT_REAL\n')
    metrics[0]['total_cost']=1.;(a/'metrics.json').write_text(json.dumps(metrics))
    with pytest.raises(ArithmeticError):baseline_gate(a,b)


def test_future_stress_does_not_change_pre_shock_optimized_decision(toy):
    settings,suppliers,world=toy;first=date(2021,12,1);last=date(2022,3,1)
    point,risk=calendar_planners(last)
    for kind in ('fa','rn','ra'):
        audits=[]
        for cell in ({'id':'baseline','axis':'baseline'},{'id':'stress','axis':'delay_stress','value':1.},{'id':'stressD','axis':'demand_stress','value':120.}):
            s,sp,w=cell_overrides(cell,*toy)
            points=lambda o:tuple(ModelPrediction(o,add_months(o,-1),add_months(o,h),h,100.,'TOY') for h in (1,2,3))
            policy=ForecastAware(points,s,LP,point) if kind=='fa' else RiskAware(lambda o:synthetic_bundle(o,[(100.,100.,100.)]*128),s,LP,{**RISK,'risk_weight':0. if kind=='rn' else .5},risk)
            result=run_historical_policy(w,s,sp,policy,first,last,lambda o:())
            assert result['complete'];audits.append(result['decision_audit'][0])
        assert audits[0]==audits[1]==audits[2]


def test_all_supported_cell_worlds_ignore_changed_holdout_values():
    from types import SimpleNamespace
    from food_procurement_intelligence.data.availability import DevelopmentPriceStore
    from food_procurement_intelligence.evaluation.historical_prices import GuardedValidationPrices
    from food_procurement_intelligence.evaluation.splits import load_split_plans
    plan,_=load_split_plans(ROOT/'configs/evaluation/splits.toml')
    months=months_between(add_months(plan.validation_origin_start,-1),plan.holdout_target_start)
    settings=SimulationSettings(100.,200.,400.,3.,1500.,1.,200.,9.)
    suppliers=(Supplier('A',.02,2,80.),Supplier('B',.08,1,100.))
    all_results=[]
    for poison in (100.,1e90):
        records=[SimpleNamespace(date=m,price=poison if m>=plan.holdout_target_start else 100.,unit='USD_per_metric_tonne',available_at=assumed_available_at(m)) for m in months]
        store=DevelopmentPriceStore(records,plan)
        prices=GuardedValidationPrices(store.validation_actuals_reader(),plan).frozen_path()
        base=HistoricalEvaluationWorld('TOY_NOT_REAL',plan.validation_target_start,plan.validation_target_end,prices,tuple((p.month,100.) for p in prices))
        results=[]
        for cell in tomllib.loads((ROOT/'configs/evaluation/sensitivity.toml').read_text())['cells']:
            if cell['kind']=='unsupported':continue
            s,sp,w=cell_overrides(cell,settings,suppliers,base)
            result=run_historical_policy(w,s,sp,FixedProcurement(),plan.validation_origin_start,plan.validation_origin_end,store.history_as_of)
            assert result['complete'];results.append(result)
        all_results.append(results)
    assert all_results[0]==all_results[1]
