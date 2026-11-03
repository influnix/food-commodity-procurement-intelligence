"""Network-free synthetic CVaR, information boundaries and physical execution."""

from dataclasses import replace
from datetime import date
from pathlib import Path
import copy
import math
import tomllib

import pytest
from ortools.linear_solver import pywraplp

from food_procurement_intelligence.evaluation.splits import (
    add_months, HoldoutLockedError, LeakageError, load_split_plans,
)
from food_procurement_intelligence.forecasting.common import ModelPrediction
from food_procurement_intelligence.optimization.deterministic import build_problem, solve_plan, STATUS_NAMES
from food_procurement_intelligence.optimization.scenario_adapter import bundle_from_records, SavedPlanningScenarios
from food_procurement_intelligence.optimization.scenario_lp import (
    RiskPlanResult, mean_points, non_anticipativity_errors, price_plan, solve_risk_plan, weighted_tail,
)
from food_procurement_intelligence.optimization.toy_cvar import cvar_hand_problems, synthetic_bundle, toy_planning
from food_procurement_intelligence.policies.fixed import FixedProcurement
from food_procurement_intelligence.policies.forecast_aware import ForecastAware, PlanningFailure
from food_procurement_intelligence.policies.risk_aware import RiskAware
from food_procurement_intelligence.simulation.contracts import DecisionContext, PublicOrder
from food_procurement_intelligence.simulation.engine import run_simulation
from food_procurement_intelligence.simulation.toy import toy_inputs

ROOT = Path(__file__).resolve().parents[1]
D8 = tomllib.loads((ROOT/"configs/day8.toml").read_text())
D7 = tomllib.loads((ROOT/"configs/day7.toml").read_text())
D6 = tomllib.loads((ROOT/"configs/day6.toml").read_text())
LP, RISK = D7["lp"], D8["risk"]


def solve_case(index=0, **risk_overrides):
    _, ctx, bundle, settings, _ = cvar_hand_problems()[index]
    risk = {**RISK, "scenario_count": len(bundle.paths), **risk_overrides}
    return solve_risk_plan(ctx,bundle,settings,LP,risk)


@pytest.mark.parametrize("index", range(6))
def test_six_prespecified_hand_distributions(index):
    _,ctx,bundle,settings,expected = cvar_hand_problems()[index]
    result = solve_case(index)
    assert result.accepted and result.status == "OPTIMAL"
    assert (result.expected_cost,result.var,result.cvar,result.objective) == pytest.approx(expected)
    assert result.diagnostics["non_anticipativity_passed"]
    assert result.diagnostics["scenario_order_variables"] == 0
    assert result.diagnostics["ortools_verify_solution"]
    assert not result.diagnostics["violations"]
    assert all(r["total_cost"] == pytest.approx(sum(r["components"].values())) for r in result.scenario_costs)


def test_cvar_integrates_fractional_boundary_atom_not_conditional_average():
    # Top 10% consists of 5%*100 and only 5%*20; E=17, VaR20, CVaR60.
    result = weighted_tail((10.,20.,100.),(.7,.25,.05),.9)
    assert result == pytest.approx({"expected_cost":17.,"var":20.,"cvar":60.})
    eta=result["var"]
    assert eta+sum(w*max(c-eta,0) for c,w in zip((10,20,100),(.7,.25,.05)))/.1 == pytest.approx(60)


@pytest.mark.parametrize("weights", [(0.,1.),(-.1,1.1),(.5,.6),(math.nan,1.)])
def test_invalid_probability_mass_is_rejected(weights):
    with pytest.raises(ValueError):
        weighted_tail((1.,2.),weights,.9)


@pytest.mark.parametrize("alpha,weight", [(0.,.5),(1.,.5),(.9,-.1),(.9,1.1),(.9,math.nan)])
def test_invalid_risk_parameters_rejected(alpha,weight):
    assert not solve_case(alpha=alpha,risk_weight=weight).accepted


def test_identical_128_paths_equal_day7_optimum_not_unique_order_claim():
    _,ctx,bundle,settings,_ = cvar_hand_problems()[0]
    deterministic=solve_plan(ctx,mean_points(bundle),settings,LP)
    for weight in (0.,.5,1.):
        result=solve_case(0,risk_weight=weight)
        assert result.accepted and result.objective==pytest.approx(deterministic.objective)


def test_lambda_zero_equals_deterministic_mean_and_lambda_one_direct_tail():
    _,ctx,bundle,settings,_=cvar_hand_problems()[2]
    mean=solve_plan(ctx,mean_points(bundle),settings,LP)
    neutral=solve_case(2,risk_weight=0.)
    tail=solve_case(2,risk_weight=1.)
    assert neutral.accepted and tail.accepted
    assert neutral.objective==pytest.approx(mean.objective)==pytest.approx(240)
    assert neutral.variables["q"]["A|2000-01"]==pytest.approx(10)
    assert neutral.cvar==pytest.approx(420)
    assert not neutral.diagnostics["eta_identified_by_objective"]
    assert tail.objective==pytest.approx(tail.cvar)==pytest.approx(250)
    assert tail.cvar>=tail.expected_cost-1e-7


def test_non_anticipativity_blocks_cheap_perfect_foresight_current_orders():
    _,ctx,bundle,settings,_=cvar_hand_problems()[5]
    result=solve_case(5)
    problem=build_problem(ctx,mean_points(bundle),settings,LP)
    oracle=weighted_tail((220.,250.),(.9,.1),.9)
    assert .5*(oracle["expected_cost"]+oracle["cvar"])==pytest.approx(236.5)
    assert result.objective>236.5
    bad=copy.deepcopy(result.variables)
    bad["q"]["A|2000-01"]={"normal":10.,"tail":0.}
    assert non_anticipativity_errors(problem,bad)
    bad=copy.deepcopy(result.variables)
    bad["scenario_inventory"]={"normal":0.,"tail":1.}
    assert non_anticipativity_errors(problem,bad)
    assert "shared_q_A_" in result.lp_text


@pytest.mark.parametrize("field,value", [("purpose","evaluation"),("source_model","other"),("forecast_origin","2000-02"),
    ("unit","EUR_per_tonne"),("information_cutoff","2000-01"),("target_month","2001-01"),("pool_sha256","mixed")])
def test_saved_row_metadata_cannot_mix(field,value):
    _,ctx,bundle,_,_=cvar_hand_problems()[0]
    rows=bundle.records()
    rows[0][field]=value
    with pytest.raises(ValueError):
        bundle_from_records(rows,ctx.origin,bundle.model)


def test_three_horizon_probability_is_counted_once_joint_path_preserved():
    _,ctx,bundle,_,_=cvar_hand_problems()[1]
    rows=bundle.records()
    assert sum(r["probability"] for r in rows)==pytest.approx(3.)
    recovered=bundle_from_records(rows,ctx.origin,bundle.model)
    assert recovered==bundle and sum(p.weight for p in recovered.paths)==1
    for mutation in ("duplicate","missing","source","weight"):
        bad=copy.deepcopy(rows)
        if mutation=="duplicate": bad.append(dict(rows[0]))
        if mutation=="missing": bad.pop()
        if mutation=="source": bad[0]["source_oof_origin"]="1991-01"
        if mutation=="weight": bad[0]["probability"]="0.8"
        with pytest.raises(ValueError): bundle_from_records(bad,ctx.origin,bundle.model)


def test_evaluation_and_wrong_origin_refused_by_solver_and_policy():
    _,ctx,bundle,settings,_=cvar_hand_problems()[0]
    for bad in (replace(bundle,purpose="evaluation"),replace(bundle,origin=add_months(ctx.origin,1))):
        assert solve_risk_plan(ctx,bad,settings,LP,RISK).status=="INVALID_INPUT"
        policy=RiskAware(lambda _:bad,settings,LP,RISK)
        with pytest.raises(LeakageError): policy(ctx)


def test_existing_pipeline_scenario_constants_and_cohort_capacity():
    _,ctx,bundle,settings,_=cvar_hand_problems()[1]
    supplier=replace(ctx.suppliers[0],monthly_capacity_tonnes=10.)
    order=PublicOrder("confirmed",supplier.supplier_id,ctx.origin,add_months(ctx.origin,1),5.,False)
    ctx=replace(ctx,suppliers=(supplier,),outstanding_orders=(order,))
    result=solve_risk_plan(ctx,bundle,settings,LP,{**RISK,"scenario_count":2})
    assert result.accepted and result.variables["q"]["S|2000-01"]==pytest.approx(5.)
    assert [r["components"]["pipeline_procurement_constant"] for r in result.scenario_costs]==[50.,500.]
    assert result.objective==pytest.approx(595.)


def test_conservative_forced_overflow_infeasible_not_engine_failure():
    _,ctx,bundle,settings,_=cvar_hand_problems()[0]
    order=PublicOrder("overflow",ctx.suppliers[0].supplier_id,ctx.origin,add_months(ctx.origin,1),100.,False)
    ctx=replace(ctx,on_hand_tonnes=100.,outstanding_orders=(order,))
    result=solve_risk_plan(ctx,bundle,settings,LP,RISK)
    assert result.status=="INFEASIBLE" and not result.accepted


def test_low_penalty_optimal_non_greedy_flow_rejected():
    _,ctx,bundle,settings,_=cvar_hand_problems()[0]
    settings=replace(settings,unmet_usd_per_tonne=0.,holding_usd_per_tonne_month=0.,
                     terminal_target_tonnes=20.,terminal_usd_per_tonne_deviation=1000.)
    ctx=replace(ctx,on_hand_tonnes=20.)
    result=solve_risk_plan(ctx,bundle,settings,LP,RISK)
    assert result.status=="OPTIMAL" and not result.accepted
    assert any("greedy_unmet" in v for v in result.diagnostics["violations"])


@pytest.mark.parametrize("code",[1,2,3,4,5,6,999])
def test_solver_status_never_silently_falls_back(code):
    class Fake:
        def __init__(self): self.inner=pywraplp.Solver.CreateSolver("GLOP")
        def __getattr__(self,name): return getattr(self.inner,name)
        def Solve(self):
            self.inner.Solve()
            return code
    _,ctx,bundle,settings,_=cvar_hand_problems()[0]
    result=solve_risk_plan(ctx,bundle,settings,LP,RISK,lambda _:Fake())
    assert result.status==STATUS_NAMES.get(code,"UNKNOWN_STATUS") and not result.accepted


def test_backend_absent_exception_and_verify_failure_refused():
    _,ctx,bundle,settings,_=cvar_hand_problems()[0]
    assert solve_risk_plan(ctx,bundle,settings,LP,RISK,lambda _:None).status=="BACKEND_UNAVAILABLE"
    def broken(_): raise RuntimeError("synthetic backend failure")
    assert solve_risk_plan(ctx,bundle,settings,LP,RISK,broken).status=="ABNORMAL"
    class Fake:
        def __init__(self): self.inner=pywraplp.Solver.CreateSolver("GLOP")
        def __getattr__(self,name): return getattr(self.inner,name)
        def VerifySolution(self,*args): return False
    assert not solve_risk_plan(ctx,bundle,settings,LP,RISK,lambda _:Fake()).accepted


def test_tolerance_and_cost_reconstruction_detect_corruption(monkeypatch):
    import food_procurement_intelligence.optimization.scenario_lp as module
    _,ctx,bundle,settings,_=cvar_hand_problems()[0]
    result=solve_case()
    problem=build_problem(ctx,mean_points(bundle),settings,LP)
    values=copy.deepcopy(result.variables)
    values["I"]["2000-02"]+=2*LP["quantity_tolerance"]
    assert price_plan(problem,values,bundle,RISK,LP)["violations"]
    original=module.price_plan
    def corrupt(*args):
        priced=original(*args)
        priced["objective"]+=1
        return priced
    monkeypatch.setattr(module,"price_plan",corrupt)
    assert not solve_case().accepted


def flat(origin):
    return tuple(ModelPrediction(origin,add_months(origin,-1),add_months(origin,h),h,100.,"synthetic_flat100_prespecified") for h in (1,2,3))


@pytest.mark.parametrize("index",range(5))
def test_same_synthetic_world_three_policies_and_current_only(index):
    settings,suppliers,_,worlds=toy_inputs(D6)
    world=worlds[index]
    risk=RiskAware(lambda o:toy_planning(o,D8["toy"]),settings,LP,RISK)
    results=[run_simulation(world,settings,suppliers,p,()) for p in
        (FixedProcurement(),ForecastAware(flat,settings,LP),risk)]
    assert all(r["summary"]["terminal_outstanding_tonnes"]==0 for r in results)
    assert all(r["summary"]["initial_inventory_tonnes"]==200 and r["summary"]["initial_pipeline_tonnes"]==0 for r in results)
    for row in risk.history:
        actual=[o for o in results[-1]["orders"] if o["order_month"].strftime("%Y-%m")==row["origin"]]
        assert sum(o["quantity_tonnes"] for o in actual)==pytest.approx(sum(o["quantity_tonnes"] for o in row["executed_orders"]))
    assert risk.history[0]["plan"]["variables"]["q"]["B|2000-02"]>0
    assert risk.history[-1]["plan"]["status"]=="TERMINAL_NO_ACTION"


def test_future_realized_price_demand_delay_leave_past_risk_decisions_unchanged():
    settings,suppliers,_,worlds=toy_inputs(D6)
    histories=[]
    for world in (worlds[0],worlds[4]):
        policy=RiskAware(lambda o:toy_planning(o,D8["toy"]),settings,LP,RISK)
        run_simulation(world,settings,suppliers,policy,())
        histories.append(policy.history)
    assert histories[0][:2]==histories[1][:2]


def test_no_price_store_or_holdout_file_can_be_read_by_development_solver(monkeypatch):
    # Poison all file reads after supplying an immutable planning set. In particular,
    # neither a changed Holdout nor an actual-price store can affect this computation.
    _,ctx,bundle,settings,_=cvar_hand_problems()[0]
    baseline=solve_risk_plan(ctx,bundle,settings,LP,RISK)
    def forbidden(*args,**kwargs): raise AssertionError("No price file access in solver")
    monkeypatch.setattr(Path,"open",forbidden)
    assert solve_risk_plan(ctx,bundle,settings,LP,RISK).record()==baseline.record()


def test_saved_adapter_blocks_holdout_before_any_file_read():
    adapter=SavedPlanningScenarios.__new__(SavedPlanningScenarios)
    adapter.plan=load_split_plans(ROOT/"configs/splits.toml")[0]
    with pytest.raises(HoldoutLockedError): adapter(date(2024,9,1),"sarimax_110_10012")


def test_policy_failure_replay_and_numerical_quantity_limits():
    _,ctx,bundle,settings,_=cvar_hand_problems()[0]
    failed=RiskAware(lambda _:bundle,settings,LP,RISK,lambda *args:RiskPlanResult("NOT_SOLVED"))
    with pytest.raises(PlanningFailure): failed(ctx)
    assert failed.history[0]["executed_orders"]==[]
    policy=RiskAware(lambda _:bundle,settings,LP,RISK)
    policy(ctx)
    with pytest.raises(LeakageError): policy(ctx)
    def fake(*args): return RiskPlanResult("OPTIMAL",True,variables={"q":{"S|2000-01":100.+2*LP["quantity_tolerance"]}})
    with pytest.raises(PlanningFailure): RiskAware(lambda _:bundle,settings,LP,RISK,fake)(ctx)


def test_seeded_generator_and_solve_reproduce_without_global_rng_or_world():
    from random import getstate
    state=getstate()
    origin=date(2000,1,1)
    a,b=toy_planning(origin,D8["toy"]),toy_planning(origin,D8["toy"])
    assert a==b and getstate()==state
    assert sum(p.weight for p in a.paths)==1 and len(a.paths)==128
    assert solve_case().record()==solve_case().record()


@pytest.mark.parametrize("value",[0.,-1.,math.nan,math.inf])
def test_consumer_rechecks_nonpositive_nonfinite_price(value):
    # Explicitly bypass the dataclass constructor to exercise the consuming boundary.
    _,ctx,bundle,settings,_=cvar_hand_problems()[0]
    bad=copy.deepcopy(bundle)
    object.__setattr__(bad.paths[0],"prices",(value,10.,10.))
    assert solve_risk_plan(ctx,bad,settings,LP,RISK).status=="INVALID_INPUT"


@pytest.mark.parametrize("raw,expected",[(-5e-8,0.),(100.+5e-8,100.),(math.nan,None),(math.inf,None)])
def test_policy_normalization_only_inside_quantity_tolerance(raw,expected):
    _,ctx,bundle,settings,_=cvar_hand_problems()[0]
    def fake(*args): return RiskPlanResult("OPTIMAL",True,variables={"q":{"S|2000-01":raw}})
    policy=RiskAware(lambda _:bundle,settings,LP,RISK,fake)
    if expected is None:
        with pytest.raises(PlanningFailure): policy(ctx)
    else:
        orders=policy(ctx)
        assert sum(o.quantity_tonnes for o in orders)==expected
        assert policy.history[0]["normalization_absolute_tonnes"]==pytest.approx(abs(raw-expected))


def test_holdout_value_mutation_preserves_asof_scenarios_and_risk_plan():
    from types import SimpleNamespace
    from random import Random
    from food_procurement_intelligence.data.availability import DevelopmentPriceStore
    from food_procurement_intelligence.data.world_bank import assumed_available_at
    from food_procurement_intelligence.evaluation.splits import decision_at
    from food_procurement_intelligence.uncertainty.joint_scenarios import SavedOOFForecasts, generate_joint_scenarios
    plan,_=load_split_plans(ROOT/"configs/splits.toml")
    origin=plan.validation_origin_start
    past=date(2021,1,1)
    model="sarimax_110_10012"
    rows=[{"model_name":model,"forecast_origin":o.strftime("%Y-%m"),"horizon":h,
        "target_month":add_months(o,h).strftime("%Y-%m"),"point_prediction":"100",
        "fit_information_end":add_months(o,-1).strftime("%Y-%m"),
        "fit_max_label_available_at":decision_at(o).isoformat(),"forecast_asof_at":decision_at(o).isoformat(),
        "unit":"USD_per_metric_tonne","phase":phase,"uncertainty_method":"sarimax_native"}
        for o,phase in ((past,"historical_train"),(origin,"validation")) for h in (1,2,3)]
    source=SavedOOFForecasts(rows,plan)
    settings,suppliers,_,_=toy_inputs(D6)
    results=[]
    for holdout_price in (100.,1e90):
        records=[SimpleNamespace(date=m,price=p,unit="USD_per_metric_tonne",available_at=assumed_available_at(m))
            for m,p in [(add_months(past,h),100.+h) for h in (1,2,3)]+[(plan.holdout_target_start,holdout_price)]]
        store=DevelopmentPriceStore(records,plan)
        pool,_=source.vectors_as_of(store,origin,model,60)
        bundle,_=generate_joint_scenarios(pool,source.points_at(origin,model),origin,model,"planning",
            {**D6["scenarios"],"minimum_joint_vectors":1},plan,Random(7),7)
        ctx=DecisionContext(origin,plan.validation_target_end,200.,100.,suppliers,(),store.history_as_of(origin))
        result=solve_risk_plan(ctx,bundle,settings,LP,RISK)
        assert result.accepted
        results.append((bundle,result.record()))
    assert results[0]==results[1]


def test_shared_context_rejects_current_or_unpublished_actual_price():
    from datetime import datetime, timezone
    from food_procurement_intelligence.data.availability import VisiblePrice
    _,ctx,_,_,_=cvar_hand_problems()[0]
    for observation,publication in ((ctx.origin,datetime(2000,1,31,tzinfo=timezone.utc)),
                                    (date(1999,12,1),datetime(2000,2,1,tzinfo=timezone.utc))):
        with pytest.raises(LeakageError):
            replace(ctx,published_prices=(VisiblePrice(observation,100.,"USD_per_metric_tonne",publication),))


def test_scenario_proof_view_selects_origin_before_decoding_price_values(tmp_path):
    import json
    from food_procurement_intelligence.optimization.scenario_adapter import pool_proof_view
    path=tmp_path/"synthetic_proof.json"
    rows=[{"source_model":"toy","construction_origin":"2000-01","actual_prices":[100.25]},
          {"source_model":"toy","construction_origin":"2001-01","actual_prices":[1e90]}]
    path.write_text(json.dumps(rows))
    selected=pool_proof_view(path,date(2000,1,1),"toy")
    assert len(selected)==1 and selected[0]["actual_prices"]==["100.25"]
