"""Hand LPs, fake status handling and synthetic receding-horizon execution."""

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
import tomllib

import pytest
from ortools.linear_solver import pywraplp

from food_procurement_intelligence.optimization.deterministic import solve_plan, build_problem, inspect_solution, STATUS_NAMES
from food_procurement_intelligence.optimization.toy_lp import hand_problems
from food_procurement_intelligence.optimization.forecast_adapter import PointForecastAdapter
from food_procurement_intelligence.policies.forecast_aware import ForecastAware, PlanningFailure
from food_procurement_intelligence.forecasting.common import ModelPrediction
from food_procurement_intelligence.evaluation.splits import add_months, load_split_plans, decision_at, LeakageError, HoldoutLockedError
from food_procurement_intelligence.simulation.contracts import DecisionContext, PublicOrder, Supplier, SimulationSettings, ToyWorld
from food_procurement_intelligence.simulation.toy import toy_inputs
from food_procurement_intelligence.simulation.engine import run_simulation
from food_procurement_intelligence.data.availability import VisiblePrice
from food_procurement_intelligence.data.world_bank import assumed_available_at

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
CONFIG = tomllib.loads((ROOT / "configs/procurement/deterministic.toml").read_text(encoding="utf-8"))
LP = CONFIG["lp"]
D6 = tomllib.loads((ROOT / "configs/scenarios/joint_and_operations.toml").read_text(encoding="utf-8"))


def flat(origin, value=100.):
    return tuple(ModelPrediction(origin, add_months(origin, -1), add_months(origin, h), h, value, "synthetic_flat100_prespecified") for h in (1, 2, 3))


@pytest.mark.parametrize("index", range(5))
def test_five_real_glop_hand_calculations(index):
    name, ctx, points, settings, expected = hand_problems()[index]
    result = solve_plan(ctx, points, settings, LP)
    assert result.status == "OPTIMAL" and result.accepted
    assert result.objective == pytest.approx(expected)
    assert not result.diagnostics["violations"]
    expected_current = ({"S":8}, {"A":10,"B":10}, {"A":4,"B":6}, {"S":20}, {"S":4})[index]
    for supplier, quantity in expected_current.items():
        assert result.variables["q"][supplier + "|2000-01"] == pytest.approx(quantity)
    if index == 4:
        assert result.variables["U"]["2000-02"] == 6


def test_confirmed_pipeline_constant_and_current_cohort_capacity_are_not_double_counted():
    _, ctx, points, settings, _ = hand_problems()[0]
    supplier = Supplier("S", 0., 1, 10., maximum_delay_months=0)
    confirmed = PublicOrder("already_committed", "S", ctx.origin, add_months(ctx.origin, 1), 5., False)
    ctx = replace(ctx, on_hand_tonnes=0., suppliers=(supplier,), outstanding_orders=(confirmed,))
    result = solve_plan(ctx, points, settings, LP)
    assert result.accepted and result.variables["q"]["S|2000-01"] == 5
    assert result.components["pipeline_procurement_constant"] == 50
    assert result.components["new_procurement"] == 50 and result.objective == 100


def test_overdue_public_pipeline_uses_next_month_not_future_realized_delay():
    _, ctx, points, settings, _ = hand_problems()[0]
    supplier = Supplier("S", 0., 1, 100., maximum_delay_months=1)
    order = PublicOrder("overdue", "S", date(1999,12,1), date(2000,1,1), 10., True)
    ctx = replace(ctx, simulation_end=date(2000,3,1), on_hand_tonnes=0., suppliers=(supplier,), outstanding_orders=(order,))
    result = solve_plan(ctx, flat(ctx.origin, 10.), settings, LP)
    assert result.accepted and result.variables["R"]["2000-02"] >= 10
    assert result.components["pipeline_procurement_constant"] == 100


def test_terminal_absolute_deviation_and_no_discretionary_disposal():
    _, ctx, points, settings, _ = hand_problems()[0]
    ctx = replace(ctx, on_hand_tonnes=30.)
    settings = replace(settings, terminal_target_tonnes=5., terminal_usd_per_tonne_deviation=9.)
    result = solve_plan(ctx, points, settings, LP)
    assert result.accepted and result.objective == 135
    assert result.variables["I"]["2000-02"] == 20
    assert result.variables["W"]["2000-02"] == 0
    assert result.variables["deviation"]["plus"] == 15


def test_forced_pipeline_overflow_is_explicit_restricted_lp_infeasibility():
    _, ctx, points, settings, _ = hand_problems()[0]
    supplier = Supplier("S",0.,1,100.,maximum_delay_months=1)
    order = PublicOrder("forced", "S", date(1999,12,1), ctx.origin,100.,True)
    ctx = replace(ctx,on_hand_tonnes=100.,planned_demand_tonnes=0.,suppliers=(supplier,),outstanding_orders=(order,))
    result = solve_plan(ctx,points,settings,LP)
    assert result.status == "INFEASIBLE" and not result.accepted and result.objective is None


@pytest.mark.parametrize("code", [1,2,3,4,5,6,999])
def test_fake_statuses_never_silently_execute_or_fallback(code):
    class FakeStatus:
        def __init__(self):
            self.inner=pywraplp.Solver.CreateSolver("GLOP")
        def __getattr__(self,name):
            return getattr(self.inner,name)
        def Solve(self):
            self.inner.Solve()
            return code
    _, ctx, points, settings, _ = hand_problems()[0]
    result=solve_plan(ctx,points,settings,LP,lambda _:FakeStatus())
    assert result.status==STATUS_NAMES.get(code,"UNKNOWN_STATUS") and not result.accepted
    if code==1:
        assert result.objective==80 and result.diagnostics["ortools_verify_solution"]


def test_backend_unavailable_and_abnormal_factory_are_explicit():
    _, ctx, points, settings, _ = hand_problems()[0]
    assert solve_plan(ctx,points,settings,LP,lambda _:None).status=="BACKEND_UNAVAILABLE"
    def broken(_):
        raise RuntimeError("toy backend fault")
    failed=solve_plan(ctx,points,settings,LP,broken)
    assert failed.status=="ABNORMAL" and "toy backend fault" in failed.diagnostics["error"]


def test_nonfinite_and_missing_point_inputs_are_blocked():
    _, ctx, points, settings, _ = hand_problems()[0]
    malformed=SimpleNamespace(forecast_origin=ctx.origin,horizon=1,target_month=add_months(ctx.origin,1),predicted_price=float("nan"),model_name="toy")
    assert solve_plan(ctx,(malformed,),settings,LP).status=="INVALID_INPUT"
    assert solve_plan(ctx,(),settings,LP).status=="INVALID_INPUT"
    assert solve_plan(replace(ctx,suppliers=(replace(ctx.suppliers[0],order_multiple=5.),)),points,settings,LP).status=="INVALID_INPUT"


def test_numerical_tolerance_detects_balance_and_objective_corruption():
    _, ctx, points, settings, _ = hand_problems()[0]
    result=solve_plan(ctx,points,settings,LP)
    problem=build_problem(ctx,points,settings,LP)
    values={k:dict(v) for k,v in result.variables.items()}
    values["I"]["2000-02"]+=LP["quantity_tolerance"]*2
    _,check=inspect_solution(problem,values,result.objective,LP)
    assert check["violations"]
    _,check=inspect_solution(problem,result.variables,result.objective+1,LP)
    assert "objective_reconstruction" in check["violations"]


def test_identical_lp_is_deterministic():
    _, ctx, points, settings, _ = hand_problems()[0]
    a,b=(solve_plan(ctx,points,settings,LP) for _ in range(2))
    assert a.record()==b.record() and a.lp_text==b.lp_text


def test_only_current_orders_execute_and_future_plans_are_reoptimized():
    settings,suppliers,_,worlds=toy_inputs(D6)
    policy=ForecastAware(flat,settings,LP)
    result=run_simulation(worlds[0],settings,suppliers,policy,())
    first=policy.history[0]
    assert first["plan"]["variables"]["q"]["B|2000-02"]>0
    first_orders=[o for o in result["orders"] if o["order_month"]==date(2000,1,1)]
    assert sum(o["quantity_tonnes"] for o in first_orders)==sum(o["quantity_tonnes"] for o in first["executed_orders"])
    for row in policy.history:
        actual=[o for o in result["orders"] if o["order_month"].strftime("%Y-%m")==row["origin"]]
        assert sum(o["quantity_tonnes"] for o in actual)==pytest.approx(sum(o["quantity_tonnes"] for o in row["executed_orders"]))
    assert len(result["orders"])==len({r["order_id"] for r in result["receipts"]})
    assert policy.history[-1]["plan"]["status"]=="TERMINAL_NO_ACTION"
    with pytest.raises(LeakageError):
        policy(DecisionContext(worlds[0].end,worlds[0].end,0.,100.,suppliers,(),()))


def test_failure_aborts_policy_without_fixed_replacement():
    from food_procurement_intelligence.optimization.deterministic import PlanResult
    _,ctx,points,settings,_=hand_problems()[0]
    policy=ForecastAware(lambda _:points,settings,LP,lambda *args:PlanResult("NOT_SOLVED"))
    with pytest.raises(PlanningFailure):
        policy(ctx)
    assert not policy.history[0]["executed_orders"]


def test_future_world_price_and_demand_changes_leave_past_decision_unchanged():
    settings,suppliers,_,worlds=toy_inputs(D6)
    histories=[]
    for world in (worlds[0],worlds[4]):
        policy=ForecastAware(flat,settings,LP)
        run_simulation(world,settings,suppliers,policy,())
        histories.append(policy.history)
    assert histories[0][0]==histories[1][0]
    assert histories[0][1]==histories[1][1]


def test_lp_objective_matches_same_nominal_simulator_receipt_cost():
    _,ctx,_,settings,_=hand_problems()[0]
    supplier=ctx.suppliers[0]
    settings=replace(settings,initial_inventory_tonnes=12.)
    months=(date(2000,1,1),date(2000,2,1))
    prices=tuple(VisiblePrice(m,10.,"USD_per_metric_tonne",datetime.fromisoformat(assumed_available_at(m))) for m in months)
    world=ToyWorld("lp_ledger_consistency",months[0],months[1],prices,tuple((m,10.) for m in months))
    policy=ForecastAware(lambda o:flat(o,10.),settings,LP)
    result=run_simulation(world,settings,(supplier,),policy,())
    assert policy.history[0]["plan"]["objective"]==result["ledger"][1]["total_cost"]==80
    assert sum(r["terminal_cost"] for r in result["ledger"])==0


def test_point_adapter_limits_origin_horizon_and_holdout_access():
    plan,_=load_split_plans(ROOT/"configs/evaluation/splits.toml")
    origin=plan.validation_origin_start
    adapter=PointForecastAdapter(flat(origin),plan,"TOY")
    assert len(adapter(origin))==3
    with pytest.raises(HoldoutLockedError):
        adapter(plan.selection_freeze_origin)
    with pytest.raises(HoldoutLockedError):
        PointForecastAdapter(flat(plan.selection_freeze_origin),plan,"TOY")


@pytest.mark.parametrize("raw,expected",[(-1e-8,0.),(100.+1e-8,100.),(100.+1e-5,None)])
def test_current_order_boundary_normalization_is_logged_and_bounded(raw,expected):
    from food_procurement_intelligence.optimization.deterministic import PlanResult
    _,ctx,points,settings,_=hand_problems()[0]
    fake=PlanResult("OPTIMAL",True,variables={"q":{"S|2000-01":raw}})
    policy=ForecastAware(lambda _:points,settings,LP,lambda *args:fake)
    if expected is None:
        with pytest.raises(PlanningFailure): policy(ctx)
    else:
        orders=policy(ctx)
        assert sum(o.quantity_tonnes for o in orders)==expected
        assert policy.history[0]["normalization_absolute_tonnes"]==pytest.approx(abs(raw-expected))


def test_nonphysical_greedy_service_violation_is_not_executed_even_if_lp_optimal():
    _,ctx,points,settings,_=hand_problems()[0]
    ctx=replace(ctx,on_hand_tonnes=10.)
    settings=replace(settings,unmet_usd_per_tonne=1.,terminal_target_tonnes=10.,terminal_usd_per_tonne_deviation=9.)
    result=solve_plan(ctx,points,settings,LP)
    assert result.status=="OPTIMAL" and not result.accepted
    assert any("greedy_unmet" in v for v in result.diagnostics["violations"])


def test_solver_verify_solution_failure_is_not_treated_as_success():
    class Unverified:
        def __init__(self): self.inner=pywraplp.Solver.CreateSolver("GLOP")
        def __getattr__(self,name): return getattr(self.inner,name)
        def VerifySolution(self,*args): return False
    _,ctx,points,settings,_=hand_problems()[0]
    result=solve_plan(ctx,points,settings,LP,lambda _:Unverified())
    assert result.status=="OPTIMAL" and not result.accepted
