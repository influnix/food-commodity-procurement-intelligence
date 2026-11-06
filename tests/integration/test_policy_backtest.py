"""Synthetic calendars/labels only; verify boundaries before historical execution."""

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
import math
import tomllib

import pytest

from food_procurement_intelligence.data.availability import DevelopmentPriceStore, VisiblePrice
from food_procurement_intelligence.data.world_bank import assumed_available_at
from food_procurement_intelligence.evaluation.historical_prices import GuardedValidationPrices, HistoricalEvaluationWorld
from food_procurement_intelligence.evaluation.policy_backtest import run_historical_policy, paired_comparison, period_metrics
from food_procurement_intelligence.evaluation.splits import add_months, decision_at, months_between, load_split_plans, HoldoutLockedError, LeakageError
from food_procurement_intelligence.forecasting.common import ModelPrediction
from food_procurement_intelligence.optimization.order_calendar import calendar_planners
from food_procurement_intelligence.optimization.scenario_lp import RiskPlanResult
from food_procurement_intelligence.optimization.toy_cvar import synthetic_bundle
from food_procurement_intelligence.policies.fixed import FixedProcurement
from food_procurement_intelligence.policies.forecast_aware import ForecastAware, PlanningFailure
from food_procurement_intelligence.policies.risk_aware import RiskAware
from food_procurement_intelligence.simulation.contracts import SimulationSettings, Supplier, DecisionContext

ROOT=next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
LP=tomllib.loads((ROOT/'configs/procurement/deterministic.toml').read_text())["lp"]
RISK=tomllib.loads((ROOT/'configs/procurement/risk.toml').read_text())["risk"]


@pytest.fixture
def toy():
    first,last=date(2000,6,1),date(2000,9,1)
    months=months_between(date(2000,7,1),date(2000,12,1))
    prices=tuple(VisiblePrice(m,100.,'USD_per_metric_tonne',datetime.fromisoformat(assumed_available_at(m))) for m in months)
    world=HistoricalEvaluationWorld('TOY_NOT_REAL',months[0],months[-1],prices,tuple((m,100.) for m in months))
    suppliers=(Supplier('A',.02,2,80.),Supplier('B',.08,1,100.))
    settings=SimulationSettings(100.,200.,400.,3.,1500.,1.,200.,9.)
    history=lambda origin: tuple(p for p in prices if p.month<=add_months(origin,-1) and p.available_at<=decision_at(origin))
    return first,last,world,settings,suppliers,history


def execute(toy,policy):
    first,last,world,settings,suppliers,history=toy
    return run_historical_policy(world,settings,suppliers,policy,first,last,history)


def test_initial_month_is_decision_only_fixed_hand_ledger(toy):
    result=execute(toy,FixedProcurement())
    assert result['complete'] and len(result['decision_audit'])==4 and len(result['ledger'])==6
    assert result['summary']['initial_pipeline_tonnes']==0
    assert result['summary']['engine_opening_after_first_decision_tonnes']==100
    assert result['summary']['total_cost']==44820
    assert [r['ending_inventory'] for r in result['ledger']]==[120,120,120,120,100,0]
    assert result['summary']['terminal_outstanding_tonnes']==0
    assert [r['month'] for r in result['ledger']]==list(months_between(date(2000,7,1),date(2000,12,1)))
    assert not any(o['initial_pipeline'] for o in result['orders'])
    assert len([o for o in result['orders'] if o['engine_opening_from_first_decision']])==2


def test_no_order_hand_case_lost_sales_and_runoff_separation(toy):
    result=execute(toy,lambda ctx:())
    assert result['complete'] and result['summary']['total_cost']==602100
    assert result['summary']['unmet_demand']==400
    assert [r['unmet_demand'] for r in result['ledger']]==[0,0,100,100,100,100]
    full,active,runoff=(period_metrics(result,p,toy[4]) for p in ('full','active','runoff'))
    assert full['fill_rate']==pytest.approx(1/3)
    assert active['ledger_months']==3 and runoff['ledger_months']==3
    assert full['total_cost']==active['total_cost']+runoff['total_cost']
    assert runoff['unmet_demand']==300 and runoff['terminal_cost']==1800
    assert sum(r['terminal_cost']>0 for r in result['ledger'])==1


@pytest.mark.parametrize('kind',['fa','rn','ra'])
def test_existing_solver_policy_calendar_and_shared_current_execution(toy,kind):
    first,last,world,settings,suppliers,_=toy
    point,risk=calendar_planners(last)
    def forecast(o): return tuple(ModelPrediction(o,add_months(o,-1),add_months(o,h),h,100.,'TOY') for h in (1,2,3))
    def scenario(o): return synthetic_bundle(o,[(100.,100.,100.)]*128)
    policy=ForecastAware(forecast,settings,LP,point) if kind=='fa' else RiskAware(scenario,settings,LP,
        {**RISK,'risk_weight':0. if kind=='rn' else .5},risk)
    result=execute(toy,policy)
    assert result['complete'] and len(policy.history)==4
    assert all(s.accepted and s.status=='OPTIMAL' for s in policy.solutions)
    assert policy.solutions[-1].diagnostics['calendar_bounds_closed']
    for row in policy.history:
        assert row['plan']['diagnostics']['calendar_passed']
        assert all(q==0 for q in row['plan']['diagnostics']['calendar_future_q'].values())
        orders=[o for o in result['orders'] if o['order_month'].strftime('%Y-%m')==row['origin']]
        assert sum(o['quantity_tonnes'] for o in orders)==pytest.approx(sum(o['quantity_tonnes'] for o in row['executed_orders']))
    assert all(o['order_month']<=last for o in result['orders'])
    assert result['runoff_no_action']==['2000-10','2000-11','2000-12']


def test_guarded_reader_38_unique_targets_clock_and_holdout_block():
    plan,_=load_split_plans(ROOT/'configs/evaluation/splits.toml')
    calls=[]
    class FakeReader:
        def actuals_for(self,sample,clock):
            calls.append((sample,clock))
            return tuple(VisiblePrice(m,100.,'USD_per_metric_tonne',datetime.fromisoformat(assumed_available_at(m))) for m in sample.targets)
    reader=GuardedValidationPrices(FakeReader(),plan)
    path=reader.frozen_path()
    assert len(path)==len(calls)==len(set(reader.requests))==38
    assert all(clock==decision_at(plan.selection_freeze_origin) for _,clock in calls)
    assert reader.month(plan.validation_target_start)==path[0] and len(calls)==38
    for m in (plan.train_target_end,plan.bridge_start,plan.holdout_target_start):
        with pytest.raises(HoldoutLockedError): reader.month(m)
    assert len(calls)==38


@pytest.mark.parametrize('problem',['missing','wrong_month','wrong_unit','future_publication','nonpositive'])
def test_evaluator_capability_checks_observation(problem):
    plan,_=load_split_plans(ROOT/'configs/evaluation/splits.toml')
    class Fake:
        def actuals_for(self,sample,clock):
            if problem=='missing': raise LookupError('toy missing')
            m=sample.targets[0]
            value=VisiblePrice(m,100.,'USD_per_metric_tonne',datetime.fromisoformat(assumed_available_at(m)))
            if problem=='wrong_month': value=replace(value,month=add_months(m,1))
            if problem=='wrong_unit': value=replace(value,unit='EUR/t')
            if problem=='future_publication': value=replace(value,available_at=decision_at(date(2099,1,1)))
            if problem=='nonpositive': value=replace(value,price=0.)
            return (value,)
    with pytest.raises((ValueError,LookupError)): GuardedValidationPrices(Fake(),plan).frozen_path()


def test_spy_policy_never_gets_evaluator_current_prices_or_world(toy):
    observed=[]
    def spy(context):
        assert isinstance(context,DecisionContext)
        assert not any(hasattr(context,key) for key in ('world','reader','actuals_for','realized_demands','delays','procurement_cost'))
        assert all(p.month<=add_months(context.origin,-1) and p.available_at<=decision_at(context.origin) for p in context.published_prices)
        observed.append(context)
        return FixedProcurement()(context)
    result=execute(toy,spy)
    assert result['complete'] and len(observed)==4


def test_future_actual_price_demand_delay_leave_prior_orders_unchanged(toy):
    first,last,world,settings,suppliers,history=toy
    changed=replace(world,prices=tuple(replace(p,price=900.) if p.month>=date(2000,9,1) else p for p in world.prices),
        realized_demands=tuple((m,300. if m==date(2000,9,1) else d) for m,d in world.realized_demands),
        delays=(('A',date(2000,8,1),1),))
    original=execute(toy,FixedProcurement())
    updated=run_historical_policy(changed,settings,suppliers,FixedProcurement(),first,last,history)
    assert original['complete'] and updated['complete']
    assert original['decision_audit'][:3]==updated['decision_audit'][:3]


def test_holdout_value_change_leaves_38_month_backtest_unchanged():
    plan,_=load_split_plans(ROOT/'configs/evaluation/splits.toml')
    months=months_between(add_months(plan.validation_origin_start,-1),plan.holdout_target_start)
    results=[]
    for poison in (100.,1e90):
        records=[SimpleNamespace(date=m,price=poison if m>=plan.holdout_target_start else 100.,unit='USD_per_metric_tonne',available_at=assumed_available_at(m)) for m in months]
        store=DevelopmentPriceStore(records,plan)
        path=GuardedValidationPrices(store.validation_actuals_reader(),plan).frozen_path()
        world=HistoricalEvaluationWorld('TOY_NOT_REAL',plan.validation_target_start,plan.validation_target_end,path,tuple((p.month,100.) for p in path))
        suppliers=(Supplier('A',.02,2,80.),Supplier('B',.08,1,100.))
        settings=SimulationSettings(100.,200.,400.,3.,1500.,1.,200.,9.)
        results.append(run_historical_policy(world,settings,suppliers,FixedProcurement(),plan.validation_origin_start,plan.validation_origin_end,store.history_as_of))
    assert results[0]==results[1] and results[0]['complete']
    first=results[0]['decision_audit'][0]['context']
    assert max(p['month'] for p in first['published_prices'])==date(2021,5,1)


def test_same_world_independent_policy_state_and_paired_arithmetic(toy):
    fixed,none=execute(toy,FixedProcurement()),execute(toy,lambda _:())
    assert fixed['decision_audit'][0]['context']==none['decision_audit'][0]['context']
    assert fixed['ledger'][1]['ending_inventory']!=none['ledger'][1]['ending_inventory']
    rows,summary=paired_comparison({'fixed':fixed,'none':none},(('none_minus_fixed','none','fixed'),))
    assert len(rows)==6 and summary[0]['cost_difference']==602100-44820
    assert sum(r['total_cost_difference'] for r in rows)==summary[0]['cost_difference']
    assert summary[0]['fill_rate_difference']==pytest.approx(-2/3)
    assert execute(toy,FixedProcurement())==fixed


@pytest.mark.parametrize('failure',['solver','missing_forecast','missing_scenario','asof','capacity'])
def test_first_failure_explicit_no_partial_full_comparison(toy,failure):
    def bad(context):
        if context.origin==date(2000,8,1):
            if failure=='asof': raise LeakageError('synthetic unavailable input')
            if failure=='capacity':
                from food_procurement_intelligence.simulation.contracts import OrderRequest
                return (OrderRequest('A',81.),)
            if failure=='solver': raise PlanningFailure('synthetic INFEASIBLE')
            raise LookupError(failure)
        return FixedProcurement()(context)
    result=execute(toy,bad)
    assert not result['complete'] and result['summary'] is None
    assert result['failure']['first_failure_origin']==date(2000,8,1)
    assert result['failure']['fallback'] is None
    assert not result['failure']['failed_policy_partial_costs_available']
    with pytest.raises(ValueError): paired_comparison({'bad':result},(('x','bad','bad'),))


def test_shorter_planning_window_and_terminal_capacity(toy):
    first,last,world,settings,suppliers,_=toy
    point,_=calendar_planners(last)
    origin=last
    context=DecisionContext(origin,add_months(origin,2),0.,100.,suppliers,(),())
    points=tuple(ModelPrediction(origin,add_months(origin,-1),add_months(origin,h),h,100.,'TOY') for h in (1,2,3))
    result=point(context,points,settings,LP)
    assert result.accepted
    assert all(result.variables['q'][f'A|{k:%Y-%m}']==0 for k in (origin,add_months(origin,1)))
    assert result.variables['q'][f'B|{origin:%Y-%m}']<=100


def prepared_toy(toy):
    from food_procurement_intelligence.evaluation.policy_inputs import PreparedPolicyInputs
    first,last,*_=toy
    models={'sarimax':'TOY_S','lightgbm':'TOY_L'}
    def points(model):
        return lambda o:tuple(ModelPrediction(o,add_months(o,-1),add_months(o,h),h,100.,model) for h in (1,2,3))
    return PreparedPolicyInputs(months_between(first,last),models,{k:points(v) for k,v in models.items()},
        lambda o,model:synthetic_bundle(o,[(100.,100.,100.)]*128,model=model))


def test_seven_policy_factory_same_scenario_and_full_toy_replay(toy):
    from food_procurement_intelligence.evaluation.policy_inputs import make_policy
    from food_procurement_intelligence.evaluation.historical_backtest import POLICIES
    inputs=prepared_toy(toy)
    results,policies={},{}
    for name in POLICIES:
        policy=make_policy(name,inputs,toy[3],LP,RISK,toy[1])
        policies[name]=policy
        results[name]=execute(toy,policy)
        assert results[name]['complete']
    for label in ('sarimax','lightgbm'):
        assert inputs.scenario(label,toy[0]) is inputs.scenario(label,toy[0])
        assert [r['planning_scenarios'] for r in policies['rn_'+label].history]==[r['planning_scenarios'] for r in policies['ra_'+label].history]
    with pytest.raises(HoldoutLockedError): inputs.point('sarimax',add_months(toy[1],1))
    with pytest.raises(HoldoutLockedError): inputs.scenario('sarimax',add_months(toy[1],1))


@pytest.mark.parametrize('kind',['fa_sarimax','rn_sarimax','ra_sarimax'])
def test_optimized_history_decisions_invariant_before_future_price_demand_delay(toy,kind):
    from food_procurement_intelligence.evaluation.policy_inputs import make_policy
    inputs=prepared_toy(toy)
    first,last,world,settings,suppliers,history=toy
    changed=replace(world,prices=tuple(replace(p,price=900.) if p.month>=date(2000,9,1) else p for p in world.prices),
        realized_demands=tuple((m,300. if m==date(2000,9,1) else d) for m,d in world.realized_demands),delays=(('A',date(2000,8,1),1),))
    outputs=[]
    for w in (world,changed):
        outputs.append(run_historical_policy(w,settings,suppliers,make_policy(kind,inputs,settings,LP,RISK,last),first,last,history))
    assert all(r['complete'] for r in outputs)
    assert outputs[0]['decision_audit'][:3]==outputs[1]['decision_audit'][:3]


@pytest.mark.parametrize('bad',['forecast_model','forecast_origin','scenario_model','scenario_purpose','scenario_missing'])
def test_preflight_failure_identifies_origin_and_rejects_mixed_inputs(toy,bad):
    from food_procurement_intelligence.evaluation.policy_inputs import PreparedPolicyInputs,InputPreparationError
    origin=toy[0]
    def points(o):
        return tuple(ModelPrediction(o,add_months(o,-1),add_months(o,h),h,100.,'wrong' if bad=='forecast_model' else 'TOY') for h in (1,2,3)) if bad!='forecast_origin' else ()
    def scenario(o,model):
        if bad=='scenario_missing': raise LookupError('toy missing')
        bundle=synthetic_bundle(o,[(100.,100.,100.)]*128,model='wrong' if bad=='scenario_model' else model)
        return replace(bundle,purpose='evaluation') if bad=='scenario_purpose' else bundle
    with pytest.raises(InputPreparationError) as failure:
        PreparedPolicyInputs((origin,),{'sarimax':'TOY'},{'sarimax':points},scenario)
    assert failure.value.origin==origin


def test_runoff_engine_failure_reports_runoff_month_not_last_decision(toy,monkeypatch):
    import food_procurement_intelligence.evaluation.policy_backtest as module
    def broken(world,settings,suppliers,execution,opening):
        execution(DecisionContext(world.end,world.end,0.,100.,suppliers,(),()))
        raise ValueError('synthetic terminal pipeline fault')
    monkeypatch.setattr(module,'run_simulation',broken)
    result=execute(toy,FixedProcurement())
    assert not result['complete'] and result['failure']['first_failure_origin']==toy[2].end
    assert result['failure']['confirmed_ledger_through']<=add_months(toy[2].end,-1)
