"""Synthetic Toy policy comparison and point-only validation planning smoke."""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
from statistics import fmean
import sys
import tomllib

from food_procurement_intelligence.data.audit import load_development_store
from food_procurement_intelligence.evaluation.scenario_diagnostics import _serializable
from food_procurement_intelligence.evaluation.model_backtesting import digest, save_csv, save_json
from food_procurement_intelligence.evaluation.splits import add_months, load_split_plans, parse_month_label
from food_procurement_intelligence.forecasting.common import ModelPrediction
from food_procurement_intelligence.optimization.deterministic import solve_plan
from food_procurement_intelligence.optimization.forecast_adapter import load_point_adapter
from food_procurement_intelligence.optimization.toy_lp import hand_problems
from food_procurement_intelligence.policies.fixed import FixedProcurement
from food_procurement_intelligence.policies.forecast_aware import ForecastAware
from food_procurement_intelligence.simulation.contracts import DecisionContext
from food_procurement_intelligence.simulation.engine import run_simulation
from food_procurement_intelligence.simulation.toy import toy_inputs, HAND_EXPECTED


def load_deterministic_context(path: Path):
    config=tomllib.loads(path.read_text(encoding="utf-8"))
    root=(path.resolve().parent/config["project_root"]).resolve()
    for key in ("scenario_config","report_root","synthetic_root","sarimax_run","lightgbm_run"):
        if not (root/config[key]).resolve().is_relative_to(root):
            raise ValueError("Day 7 path escapes project")
    if not config["holdout_locked"] or digest(root/config["scenario_config"])!=config["scenario_config_sha256"]:
        raise ValueError("Day 6 specification changed or holdout unlocked")
    if config["comparison_initial_inventory"]!=200 or config["comparison_initial_pipeline"]!="empty":
        raise ValueError("Keep equal empty-pipeline comparison conditions")
    if config["lp"]["fallback"]!="none_abort_comparison_on_failure" or config["lp"]["require_optimal"] is not True:
        raise ValueError("Day 7 accepts verified optimal plans without fallback")
    preserved=json.loads((root/"artifacts/day7/preservation_before.json").read_text(encoding="utf-8"))
    for name, expected in preserved["sha256"].items():
        if digest(root/name)!=expected:
            raise ValueError("Existing Day 0-6 file changed: "+name)
    d6=tomllib.loads((root/config["scenario_config"]).read_text(encoding="utf-8"))
    return root,config,d6


def run_deterministic_backtest(path: Path):
    root,config,d6=load_deterministic_context(path)
    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory=root/config["report_root"]/run_id
    synthetic=root/config["synthetic_root"]/run_id
    directory.mkdir(parents=True,exist_ok=False)
    synthetic.mkdir(parents=True,exist_ok=False)
    save_json(directory/"spec_freeze.json",{"created_at_utc":datetime.now(timezone.utc).isoformat(),"config":config,
        "config_sha256":digest(path),"comparison_started":False})
    hand=[]
    timings=[]
    for name,context,points,settings,expected in hand_problems():
        result=solve_plan(context,points,settings,config["lp"])
        timings.append({"case":name,"origin":context.origin.strftime("%Y-%m"),"status":result.status,"solve_seconds":result.solve_seconds})
        hand.append({"case":name,"expected_objective":expected,**result.record()})
        (directory/(name+".lp")).write_text(result.lp_text,encoding="utf-8")
        if not result.accepted or abs(result.objective-expected)>1e-6:
            save_json(directory/"failure.json",hand[-1])
            raise RuntimeError("Hand LP failed")
    save_json(directory/"hand_lp_results.json",hand)
    settings,suppliers,opening,worlds=toy_inputs(d6)
    regression=[]
    for world in worlds:
        prior=run_simulation(world,settings,suppliers,FixedProcurement(),opening)["summary"]
        if any(abs(prior[k]-v)>1e-6 for k,v in HAND_EXPECTED[world.scenario_id].items()):
            raise ValueError("Existing Day 6 Toy regression failed")
        regression.append(prior)
    save_json(directory/"day6_toy_regression.json",regression)
    def provider(origin):
        return tuple(ModelPrediction(origin,add_months(origin,-1),add_months(origin,h),h,
            config["toy_forecast_price"],config["toy_forecast_model"]) for h in (1,2,3))
    save_json(synthetic/"comparison_inputs.json",_serializable({"settings":asdict(settings),"suppliers":[asdict(s) for s in suppliers],
        "initial_pipeline":[],"worlds":[asdict(w) for w in worlds],"forecast_belief":{
            "price":config["toy_forecast_price"],"model":config["toy_forecast_model"],"source":"prespecified_synthetic_not_future_world"}}))
    comparisons=[]
    for world in worlds:
        for name in ("fixed","forecast_aware"):
            policy=FixedProcurement() if name=="fixed" else ForecastAware(provider,settings,config["lp"])
            prefix=world.scenario_id+"__"+name
            try:
                result=run_simulation(world,settings,suppliers,policy,())
            except Exception as error:
                save_json(directory/"failure.json",_serializable({"case":world.scenario_id,"policy":name,
                    "error":str(error),"history":getattr(policy,"history",[]),"fallback":None}))
                raise
            for kind in ("ledger","orders","receipts"):
                save_csv(directory/(prefix+"_"+kind+".csv"),_serializable(result[kind]))
            row={"comparison_type":"Synthetic Toy Policy Comparison","case":world.scenario_id,"policy":name,**result["summary"],
                "average_inventory":fmean(r["ending_inventory"] for r in result["ledger"]),
                "orders_by_supplier":{s.supplier_id:sum(o["quantity_tonnes"] for o in result["orders"] if o["supplier_id"]==s.supplier_id) for s in suppliers},
                "monthly_order_tonnes":[r["new_order_quantity"] for r in result["ledger"]],
                "solver_failure_count":0,"initial_pipeline":"empty"}
            comparisons.append(row)
            if name=="forecast_aware":
                save_json(directory/(prefix+"_rolling_plans.json"),_serializable(policy.history))
                for i,solution in enumerate(policy.solutions):
                    if solution.lp_text:
                        (directory/(prefix+f"_{i+1:02d}.lp")).write_text(solution.lp_text,encoding="utf-8")
                    timings.append({"case":world.scenario_id,"origin":policy.history[i]["origin"],"status":solution.status,"solve_seconds":solution.solve_seconds})
    save_json(directory/"toy_comparison.json",comparisons)
    save_csv(directory/"toy_comparison.csv",comparisons)
    plan,_=load_split_plans(root/"configs/evaluation/splits.toml")
    store=load_development_store(root,root/"configs/data/quality.toml")
    smoke=[]
    links={}
    for label,model in (("sarimax",config["default_model"]),("lightgbm",config["alternate_model"])):
        source=root/config[label+"_run"]
        adapter=load_point_adapter(source,plan,model)
        links[label]={"directory":config[label+"_run"],"manifest_sha256":adapter.source_id}
        for value in config["smoke_origins"]:
            origin=parse_month_label(value)
            context=DecisionContext(origin,plan.validation_target_end,200.,100.,suppliers,(),store.history_as_of(origin))
            points=adapter(origin)
            result=solve_plan(context,points,settings,config["lp"])
            timings.append({"case":"smoke_"+label,"origin":value,"status":result.status,"solve_seconds":result.solve_seconds})
            smoke.append({"model":model,"origin":value,"state":"hypothetical_inventory200_empty_pipeline",
                          "forecasts":[p.record() for p in points],"actual_procurement_evaluated":False,**result.record()})
            (directory/(label+"_"+value+"_smoke.lp")).write_text(result.lp_text,encoding="utf-8")
            if not result.accepted:
                save_json(directory/"smoke_failure.json",smoke[-1])
                raise RuntimeError("Actual point planning smoke failed")
    save_json(directory/"forecast_adapter_smoke.json",smoke)
    save_json(directory/"solver_timing.json",timings)
    package=root/"src/food_procurement_intelligence"
    sources=list((package/"optimization").glob("*.py"))+[package/"policies/forecast_aware.py",Path(__file__)]
    from ortools.linear_solver import _pywraplp
    binary=Path(_pywraplp.__file__)
    outputs={p.relative_to(root).as_posix():digest(p) for parent in (directory,synthetic) for p in sorted(parent.iterdir()) if p.is_file()}
    save_json(directory/"manifest.json",{"created_at_utc":datetime.now(timezone.utc).isoformat(),"config":config,
        "config_sha256":digest(path),"scenario_config_sha256":digest(root/config["scenario_config"]),
        "split_sha256":digest(root/"configs/evaluation/splits.toml"),"point_links":links,"python":sys.version,
        "versions":{n:version(n) for n in ("ortools","absl-py","protobuf","immutabledict","numpy","pandas","statsmodels","lightgbm")},
        "backend":hand[0]["solver_version"],"solver_extension_sha256":digest(binary),
        "code_sha256":{p.relative_to(root).as_posix():digest(p) for p in sources},"output_sha256":outputs,
        "synthetic_directory":synthetic.relative_to(root).as_posix(),"holdout_locked":True,
        "actual_validation_procurement_evaluated":False,"fallback":None,"risk_aware_implemented":False})
    return {"report_dir":directory.relative_to(root).as_posix(),"hand_lp_cases":len(hand),"smoke_plans":len(smoke),
            "toy_comparison":[{k:r[k] for k in ("case","policy","total_cost","procurement_cost","unmet_demand","orders_by_supplier")} for r in comparisons]}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,default=Path("configs/procurement/deterministic.toml"))
    args=parser.parse_args()
    print(json.dumps(run_deterministic_backtest(args.config),indent=2))
