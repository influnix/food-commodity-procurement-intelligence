"""Day 8: synthetic three-policy comparison and saved planning-only smoke."""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
import json
import math
from pathlib import Path
from statistics import fmean
import sys
import tomllib

from food_procurement_intelligence.evaluation.scenario_diagnostics import _serializable
from food_procurement_intelligence.evaluation.model_backtesting import digest, save_csv, save_json
from food_procurement_intelligence.evaluation.splits import add_months, load_split_plans, months_between, parse_month_label
from food_procurement_intelligence.forecasting.common import ModelPrediction
from food_procurement_intelligence.optimization.deterministic import build_problem, solve_plan
from food_procurement_intelligence.optimization.scenario_adapter import SavedPlanningScenarios
from food_procurement_intelligence.optimization.scenario_lp import mean_points, price_plan, solve_risk_plan
from food_procurement_intelligence.optimization.toy_cvar import cvar_hand_problems, toy_planning
from food_procurement_intelligence.policies.fixed import FixedProcurement
from food_procurement_intelligence.policies.forecast_aware import ForecastAware
from food_procurement_intelligence.policies.risk_aware import RiskAware
from food_procurement_intelligence.simulation.contracts import DecisionContext
from food_procurement_intelligence.simulation.engine import run_simulation
from food_procurement_intelligence.simulation.toy import toy_inputs


def verify_preservation(root: Path) -> int:
    snapshot=json.loads((root/"artifacts/day8/preservation_before.json").read_text(encoding="utf-8"))
    for name,expected in snapshot["sha256"].items():
        if digest(root/name)!=expected:
            raise ValueError("Existing Day 0-7 file changed: "+name)
    for name,record in snapshot.get("append_only",{}).items():
        import hashlib
        if hashlib.sha256((root/name).read_bytes()[:record["bytes"]]).hexdigest()!=record["sha256"]:
            raise ValueError("Existing documentation prefix changed: "+name)
    return len(snapshot["sha256"])


def load_scenario_backtest_context(path: Path):
    config=tomllib.loads(path.read_text(encoding="utf-8"))
    root=(path.resolve().parent/config["project_root"]).resolve()
    for key in ("lp_config","scenario_run","report_root","synthetic_root"):
        if not (root/config[key]).resolve().is_relative_to(root):
            raise ValueError("Day 8 path escapes project")
    if config["holdout_locked"] is not True or digest(root/config["lp_config"])!=config["lp_config_sha256"]:
        raise ValueError("Holdout unlocked or Day 7 config changed")
    if config["risk"]!={"alpha":.9,"risk_weight":.5,"scenario_count":128,
            "non_anticipativity":"all_orders_and_physical_flows_shared","fallback":"none_abort"}:
        raise ValueError("Keep the prespecified Day 8 risk specification")
    if config["toy"]["initial_inventory"]!=200 or config["toy"]["initial_pipeline"]!="empty":
        raise ValueError("Keep common comparison state")
    verify_preservation(root)
    d7=tomllib.loads((root/config["lp_config"]).read_text(encoding="utf-8"))
    d6=tomllib.loads((root/d7["scenario_config"]).read_text(encoding="utf-8"))
    if digest(root/d7["scenario_config"])!=d7["scenario_config_sha256"]:
        raise ValueError("Day 6 config changed")
    return root,config,d7,d6


def run_scenario_backtest(path: Path) -> dict:
    root,config,d7,d6=load_scenario_backtest_context(path)
    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory=root/config["report_root"]/run_id
    synthetic=root/config["synthetic_root"]/run_id
    directory.mkdir(parents=True,exist_ok=False)
    synthetic.mkdir(parents=True,exist_ok=False)
    save_json(directory/"spec_freeze.json",{"created_at_utc":datetime.now(timezone.utc).isoformat(),
        "config":config,"config_sha256":digest(path),"spec_sha256":digest(root/"docs/PROCUREMENT_OPTIMIZATION.md"),"comparison_started":False})
    timings=[]
    def save_solution(name,result):
        timings.append({"case":name,"status":result.status,"solve_seconds":result.solve_seconds})
        if result.lp_text:
            (directory/(name+".lp")).write_text(result.lp_text,encoding="utf-8")
        if not result.accepted:
            save_json(directory/"failure.json",{"case":name,**result.record()})
            raise RuntimeError("Unverified plan: "+name)
    hands=[]
    for name,ctx,bundle,settings,expected in cvar_hand_problems():
        risk={**config["risk"],"scenario_count":len(bundle.paths)}
        result=solve_risk_plan(ctx,bundle,settings,d7["lp"],risk)
        save_solution(name,result)
        observed=(result.expected_cost,result.var,result.cvar,result.objective)
        if any(not math.isclose(a,b,abs_tol=1e-6) for a,b in zip(observed,expected)):
            raise ArithmeticError("CVaR hand calculation mismatch")
        hands.append({"case":name,"expected_E_VaR_CVaR_objective":expected,
            "context":asdict(ctx),"settings":asdict(settings),"scenarios":bundle.records(),**result.record()})
    save_json(directory/"hand_results.json",_serializable(hands))
    boundaries=[]
    for index in (0,2):
        name,ctx,bundle,settings,_=cvar_hand_problems()[index]
        deterministic=solve_plan(ctx,mean_points(bundle),settings,d7["lp"])
        save_solution(name+"_deterministic_mean",deterministic)
        for weight in (0.,1.):
            risk={**config["risk"],"scenario_count":len(bundle.paths),"risk_weight":weight}
            result=solve_risk_plan(ctx,bundle,settings,d7["lp"],risk)
            save_solution(name+"_lambda"+str(int(weight)),result)
            if weight==0 and not math.isclose(result.objective,deterministic.objective,abs_tol=1e-6):
                raise ArithmeticError("Lambda zero mean-price equivalence failed")
            boundaries.append({"case":name,"lambda":weight,"deterministic_mean_objective":deterministic.objective,**result.record()})
    save_json(directory/"boundary_results.json",boundaries)
    settings,suppliers,_,worlds=toy_inputs(d6)
    beliefs={o:toy_planning(o,config["toy"]) for o in months_between(worlds[0].start,worlds[0].end)}
    save_csv(synthetic/"planning_scenarios.csv",[r for bundle in beliefs.values() for r in bundle.records()])
    save_json(synthetic/"comparison_inputs.json",_serializable({"settings":asdict(settings),
        "suppliers":[asdict(s) for s in suppliers],"initial_pipeline":[],"worlds":[asdict(w) for w in worlds],
        "forecast_belief":{"price":d7["toy_forecast_price"],"model":d7["toy_forecast_model"]},
        "risk_generator":config["toy"],"knowledge_type":"synthetic_not_world_bank"}))
    def point_provider(origin):
        return tuple(ModelPrediction(origin,add_months(origin,-1),add_months(origin,h),h,
            d7["toy_forecast_price"],d7["toy_forecast_model"]) for h in (1,2,3))
    comparison=[]
    common_plan_comparison=[]
    for world in worlds:
        policies={"fixed":FixedProcurement(),"forecast_aware":ForecastAware(point_provider,settings,d7["lp"]),
                  "risk_aware":RiskAware(lambda o:beliefs[o],settings,d7["lp"],config["risk"])}
        for name,policy in policies.items():
            prefix=world.scenario_id+"__"+name
            try:
                result=run_simulation(world,settings,suppliers,policy,())
            except Exception as error:
                save_json(directory/"failure.json",_serializable({"case":world.scenario_id,"policy":name,
                    "error":str(error),"history":getattr(policy,"history",[]),"fallback":None}))
                raise
            for kind in ("ledger","orders","receipts"):
                save_csv(directory/(prefix+"_"+kind+".csv"),_serializable(result[kind]))
            demand=math.fsum(r["realized_demand"] for r in result["ledger"])
            comparison.append({"case":world.scenario_id,"policy":name,**result["summary"],
                "service_rate":result["summary"]["fulfilled_demand"]/demand if demand else None,
                "average_inventory":fmean(r["ending_inventory"] for r in result["ledger"]),
                "orders_by_supplier":{s.supplier_id:math.fsum(o["quantity_tonnes"] for o in result["orders"] if o["supplier_id"]==s.supplier_id) for s in suppliers},
                "monthly_order_tonnes":[r["new_order_quantity"] for r in result["ledger"]],
                "solver_failure_count":0,"comparison_type":"Synthetic Toy, not Validation performance"})
            if name!="fixed":
                save_json(directory/(prefix+"_rolling_plans.json"),_serializable(policy.history))
                for i,solution in enumerate(policy.solutions):
                    save_solution(prefix+f"_{i+1:02d}",solution)
        if world==worlds[0]:
            ctx=DecisionContext(world.start,world.end,100.,100.,suppliers,(),())
            problem=build_problem(ctx,mean_points(beliefs[ctx.origin]),settings,d7["lp"])
            for name in ("forecast_aware","risk_aware"):
                values=policies[name].history[0]["plan"]["variables"]
                common_plan_comparison.append({"policy":name,"origin":ctx.origin.strftime("%Y-%m"),
                    "state":"common_after_January_demand_I100_empty_pipeline",
                    "interpretation":"same planning set; not realized or long-run CVaR",
                    "context":asdict(ctx),"settings":asdict(settings),"scenarios":beliefs[ctx.origin].records(),
                    "variables":values,
                    **price_plan(problem,values,beliefs[ctx.origin],config["risk"],d7["lp"])})
    save_json(directory/"toy_comparison.json",comparison)
    save_csv(directory/"toy_comparison.csv",comparison)
    save_json(directory/"common_state_planning_risk.json",_serializable(common_plan_comparison))
    # Saved planning scenarios carry their own as-of/OOF proof. No actual-price store is loaded.
    plan,_=load_split_plans(root/"configs/evaluation/splits.toml")
    adapter=SavedPlanningScenarios(root/config["scenario_run"],root,plan,config["scenario_manifest_sha256"])
    smokes=[]
    for model in config["models"]:
        for label in config["smoke_origins"]:
            origin=parse_month_label(label)
            bundle=adapter(origin,model)
            ctx=DecisionContext(origin,plan.validation_target_end,200.,100.,suppliers,(),())
            result=solve_risk_plan(ctx,bundle,settings,d7["lp"],config["risk"])
            save_solution(model+"_"+label+"_smoke",result)
            smokes.append({"origin":label,"model":model,"context":asdict(ctx),"settings":asdict(settings),
                "state":"synthetic_inventory200_empty_pipeline","actual_procurement_evaluated":False,
                "scenarios":bundle.records(),**result.record()})
    save_json(directory/"scenario_adapter_smoke.json",_serializable(smokes))
    save_json(directory/"solver_timing.json",timings)
    verify_preservation(root)
    from ortools.linear_solver import _pywraplp
    package=root/"src/food_procurement_intelligence"
    sources=[package/"optimization"/n for n in ("scenario_lp.py","scenario_adapter.py","toy_cvar.py")]
    sources += [package/"policies/risk_aware.py",Path(__file__),root/"scripts/validation/verify_scenario_plans.py"]
    outputs={p.relative_to(root).as_posix():digest(p) for parent in (directory,synthetic) for p in sorted(parent.iterdir()) if p.is_file()}
    d6manifest=json.loads((root/config["scenario_run"]/"manifest.json").read_text(encoding="utf-8"))
    save_json(directory/"manifest.json",{"created_at_utc":datetime.now(timezone.utc).isoformat(),"config":config,
        "config_sha256":digest(path),"spec_sha256":digest(root/"docs/PROCUREMENT_OPTIMIZATION.md"),
        "lp_config_sha256":digest(root/config["lp_config"]),"scenario_manifest_sha256":adapter.source_id,
        "day6_scenarios_sha256":digest(root/config["scenario_run"]/"joint_price_scenarios.csv"),
        "source_data":d6manifest["source_data"],"raw_sha256":d6manifest["raw_sha256"],
        "vintage_mode":"latest_vintage_pseudo_real_time",
        "deterministic_manifest_sha256":digest(root/"artifacts/day7/20261029T022953285525Z/manifest.json"),
        "split_sha256":digest(root/"configs/evaluation/splits.toml"),"python":sys.version,
        "versions":{n:version(n) for n in ("ortools","absl-py","protobuf","immutabledict","numpy","pandas","statsmodels","lightgbm")},
        "solver_extension_sha256":digest(Path(_pywraplp.__file__)),"backend":"GLOP",
        "code_sha256":{p.relative_to(root).as_posix():digest(p) for p in sources},"output_sha256":outputs,
        "synthetic_directory":synthetic.relative_to(root).as_posix(),"holdout_locked":True,
        "actual_validation_procurement_evaluated":False,"fallback":None})
    return {"report_dir":directory.relative_to(root).as_posix(),"solver_events":len(timings),
        "toy_comparison":[{k:r[k] for k in ("case","policy","total_cost","unmet_demand","service_rate","orders_by_supplier")} for r in comparison],
        "smoke_plans":len(smokes)}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,default=Path("configs/procurement/risk.toml"))
    args=parser.parse_args()
    print(json.dumps(run_scenario_backtest(args.config),indent=2))
