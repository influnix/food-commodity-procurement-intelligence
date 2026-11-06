"""Independent saved-result arithmetic; no solver or optimization helpers imported."""

import sys as _bootstrap_sys
from pathlib import Path as _BootstrapPath
_bootstrap_root = next(p for p in _BootstrapPath(__file__).resolve().parents if (p / 'pyproject.toml').is_file())
_bootstrap_sys.path.insert(0, str(_bootstrap_root))

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path


ROOT=next(p for p in Path(__file__).resolve().parents if (p / 'pyproject.toml').is_file())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def close(a,b,tol=1e-5):
    if not math.isfinite(a) or not math.isfinite(b) or not math.isclose(a,b,abs_tol=tol,rel_tol=1e-8):
        raise AssertionError(f"Arithmetic mismatch: {a} != {b}")


def index(label):
    y,m=map(int,label.split("-"))
    return y*12+m-1


def label(n):
    return f"{n//12:04d}-{n%12+1:02d}"


def independent_risk(costs,weights,alpha):
    # Alternative to core top-mass integration: enumerate all possible VaR knots.
    expectation=sum(c*w for c,w in zip(costs,weights))
    cvar=min(eta+sum(w*max(c-eta,0.) for c,w in zip(costs,weights))/(1-alpha) for eta in set(costs))
    var=next(c for c in sorted(set(costs)) if sum(w for v,w in zip(costs,weights) if v<=c)>=alpha-1e-12)
    return expectation,var,cvar


def paths_from_rows(rows):
    groups={}
    for row in rows:
        assert row["purpose"]=="planning" and row["unit"]=="USD_per_metric_tonne"
        group=groups.setdefault(row["scenario_id"],{})
        h=int(row["horizon"])
        assert h not in group and index(row["target_month"])==index(row["forecast_origin"])+h
        group[h]=row
    result=[]
    for key,group in sorted(groups.items()):
        assert set(group)=={1,2,3}
        first=group[1]
        assert all(all(r[k]==first[k] for k in ("probability","source_model","forecast_origin","source_oof_origin","seed","pool_sha256")) for r in group.values())
        prices={r["target_month"]:float(r["price"]) for r in group.values()}
        assert all(math.isfinite(p) and p>0 for p in prices.values())
        weight=float(first["probability"])
        assert weight>0
        result.append((key,weight,prices))
    close(sum(w for _,w,_ in result),1.,1e-12)
    assert len({r[1]["source_model"] for r in groups.values()})==1
    assert len({r[1]["forecast_origin"] for r in groups.values()})==1
    return result


def verify_plan(row,context,settings,scenarios,risk,solver_checks=True):
    if solver_checks:
        assert row["accepted"] and row["status"]=="OPTIMAL"
        d=row["diagnostics"]
        assert d["ortools_verify_solution"] and d["non_anticipativity_passed"] and not d["violations"]
    values=row["variables"]
    assert set(values)=={"q","R","I","U","W","deviation"}
    t=index(context["origin"])
    end=min(t+3,index(context["simulation_end"]))
    months=[label(m) for m in range(t+1,end+1)]
    suppliers={s["supplier_id"]:s for s in context["suppliers"]}
    assert len(values["q"])==len(suppliers)*(end-t)
    if solver_checks:
        assert d["shared_physical_variables"]==len(values["q"])+4*len(months)+2
        assert d["scenario_order_variables"]==0
        assert d["variable_count"]==d["shared_physical_variables"]+len(scenarios)+1
        assert d["constraints"]==2*len(months)+1+len(scenarios)
    receipts={m:0. for m in months}
    committed={}
    pipeline=[]
    for order in context["outstanding_orders"]:
        s=suppliers[order["supplier_id"]]
        k=index(order["order_month"])
        promised=index(order["promised_month"])
        assert promised==k+s["lead_time_months"]
        assert promised+s["maximum_delay_months"]<=index(context["simulation_end"])
        assert promised+s["maximum_delay_months"]>t
        cohort=(s["supplier_id"],k)
        committed[cohort]=committed.get(cohort,0.)+order["quantity_tonnes"]
        arrival=label(max(promised+s["nominal_delay_months"],t+1))
        if arrival in receipts:
            receipts[arrival]+=order["quantity_tonnes"]
            pipeline.append((s,arrival,order["quantity_tonnes"]))
    orders=[]
    for key,qty in values["q"].items():
        sid,klabel=key.split("|")
        s=suppliers[sid]
        k=index(klabel)
        assert t<=k<end and qty>=-1e-7
        capacity=s["monthly_capacity_tonnes"]-committed.get((sid,k),0.)
        assert qty<=capacity+1e-7
        arrival=label(k+s["lead_time_months"]+s["nominal_delay_months"])
        if k+s["lead_time_months"]+s["maximum_delay_months"]>end:
            close(qty,0.,1e-7)
        if qty>1e-7:
            assert arrival in receipts
        if arrival in receipts:
            receipts[arrival]+=qty
            orders.append((s,arrival,qty))
    previous=context["on_hand_tonnes"]
    for m in months:
        close(values["R"][m],receipts[m],1e-7)
        available=previous+receipts[m]
        unmet=max(context["planned_demand_tonnes"]-available,0.)
        inventory=max(available-context["planned_demand_tonnes"],0.)
        waste=max(inventory-settings["warehouse_capacity_tonnes"],0.)
        close(values["U"][m],unmet,1e-7)
        close(values["W"][m],waste,1e-7)
        close(waste,0.,1e-7)
        close(values["I"][m],inventory-waste,1e-7)
        previous=inventory-waste
    delta=previous-settings["terminal_target_tonnes"]
    close(values["deviation"]["plus"]-values["deviation"]["minus"],delta,1e-7)
    common={"new_transport":sum(q*s["unit_transport_cost"] for s,_,q in orders),
        "pipeline_transport_constant":sum(q*s["unit_transport_cost"] for s,_,q in pipeline),
        "holding":sum(values["I"].values())*settings["holding_usd_per_tonne_month"],
        "unmet":sum(values["U"].values())*settings["unmet_usd_per_tonne"],
        "disposal":sum(values["W"].values())*settings["disposal_usd_per_tonne"],
        "planning_terminal":abs(delta)*settings["terminal_usd_per_tonne_deviation"]}
    costs,weights=[],[]
    for (sid,weight,prices),stored in zip(scenarios,row["scenario_costs"]):
        assert sid==stored["scenario_id"]
        close(weight,stored["probability"],1e-12)
        components={**common,
            "new_procurement":sum(q*prices[m]*(1+s["price_premium"]) for s,m,q in orders),
            "pipeline_procurement_constant":sum(q*prices[m]*(1+s["price_premium"]) for s,m,q in pipeline)}
        for key,value in components.items(): close(value,stored["components"][key])
        total=sum(components.values())
        close(total,stored["total_cost"])
        costs.append(total)
        weights.append(weight)
    expectation,var,cvar=independent_risk(costs,weights,risk["alpha"])
    close(expectation,row["expected_cost"])
    close(var,row["var"])
    close(cvar,row["cvar"])
    close((1-risk["risk_weight"])*expectation+risk["risk_weight"]*cvar,row["objective"])
    if solver_checks:
        eta=row["eta"]
        xi=d["raw_xi"]
        assert all(x>=-1e-4 and x>=c-eta-1e-4 for x,c in zip(xi,costs))
        if risk["risk_weight"]>0: close(eta+sum(w*x for w,x in zip(weights,xi))/(1-risk["alpha"]),cvar)


def csv_rows(path):
    with path.open(encoding="utf-8",newline="") as f: return list(csv.DictReader(f))


def verify_toys(directory,synthetic):
    inputs=read(synthetic/"comparison_inputs.json")
    assert inputs["initial_pipeline"]==[] and inputs["settings"]["initial_inventory_tonnes"]==200
    settings=inputs["settings"]
    suppliers={s["supplier_id"]:s for s in inputs["suppliers"]}
    worlds={w["scenario_id"]:w for w in inputs["worlds"]}
    summaries=read(directory/"toy_comparison.json")
    verified_plans=0
    for summary in summaries:
        case,policy=summary["case"],summary["policy"]
        world=worlds[case]
        prices={p["month"]:p["price"] for p in world["prices"]}
        demand=dict(world["realized_demands"])
        delays={(s,m):v for s,m,v in world["delays"]}
        prefix=case+"__"+policy
        orders=csv_rows(directory/(prefix+"_orders.csv"))
        receipts=csv_rows(directory/(prefix+"_receipts.csv"))
        ledger=csv_rows(directory/(prefix+"_ledger.csv"))
        assert len({o["order_id"] for o in orders})==len(orders)==len(receipts)
        cohorts={}
        for order in orders:
            s=suppliers[order["supplier_id"]]
            qty=float(order["quantity_tonnes"])
            k=order["order_month"]
            assert index(k)+s["lead_time_months"]+s["maximum_delay_months"]<=index(world["end"])
            key=order["supplier_id"],k
            cohorts[key]=cohorts.get(key,0.)+qty
            assert cohorts[key]<=s["monthly_capacity_tonnes"]+1e-7
            receipt=next(r for r in receipts if r["order_id"]==order["order_id"])
            arrival=label(index(k)+s["lead_time_months"]+delays.get(key,s["nominal_delay_months"]))
            assert receipt["receipt_month"]==arrival
            close(float(receipt["quantity_tonnes"]),qty)
            close(float(receipt["procurement_cost"]),qty*prices[arrival]*(1+s["price_premium"]))
        inventory=200.
        components=["procurement_cost","transport_cost","holding_cost","unmet_cost","disposal_cost","terminal_cost","total_cost"]
        for row in ledger:
            m=row["month"]
            arrival=[r for r in receipts if r["receipt_month"]==m]
            received=sum(float(r["quantity_tonnes"]) for r in arrival)
            available=inventory+received
            served=min(available,demand[m])
            unmet=demand[m]-served
            disposal=max(available-served-settings["warehouse_capacity_tonnes"],0.)
            inventory=available-served-disposal
            close(float(row["ending_inventory"]),inventory,1e-7)
            close(float(row["unmet_demand"]),unmet,1e-7)
            values={"procurement_cost":sum(float(r["procurement_cost"]) for r in arrival),
                "transport_cost":sum(float(r["transport_cost"]) for r in arrival),
                "holding_cost":inventory*settings["holding_usd_per_tonne_month"],
                "unmet_cost":unmet*settings["unmet_usd_per_tonne"],
                "disposal_cost":disposal*settings["disposal_usd_per_tonne"],
                "terminal_cost":abs(inventory-settings["terminal_target_tonnes"])*settings["terminal_usd_per_tonne_deviation"] if m==world["end"] else 0.}
            values["total_cost"]=sum(values.values())
            for key,value in values.items(): close(float(row[key]),value)
        for key in components: close(summary[key],sum(float(r[key]) for r in ledger))
        close(summary["unmet_demand"],sum(float(r["unmet_demand"]) for r in ledger))
        close(summary["service_rate"],1-summary["unmet_demand"]/sum(demand.values()))
        close(summary["average_inventory"],sum(float(r["ending_inventory"]) for r in ledger)/len(ledger))
        for sid in suppliers: close(summary["orders_by_supplier"][sid],sum(float(o["quantity_tonnes"]) for o in orders if o["supplier_id"]==sid))
        assert summary["solver_failure_count"]==0
        if policy in ("fixed","forecast_aware"):
            previous=ROOT/"artifacts/day7/20261029T022953285525Z"
            for kind in ("orders","receipts","ledger"):
                assert sha(directory/(prefix+"_"+kind+".csv"))==sha(previous/(prefix+"_"+kind+".csv"))
        if policy!="fixed":
            history=read(directory/(prefix+"_rolling_plans.json"))
            for row in history:
                current=[o for o in orders if o["order_month"]==row["origin"]]
                close(sum(float(o["quantity_tonnes"]) for o in current),sum(o["quantity_tonnes"] for o in row["executed_orders"]))
                for o in current:
                    raw=row["plan"]["variables"]["q"][o["supplier_id"]+"|"+row["origin"]]
                    close(raw,float(o["quantity_tonnes"]),1e-7)
                if policy=="risk_aware" and row["plan"]["status"]!="TERMINAL_NO_ACTION":
                    context={"origin":row["origin"],"simulation_end":world["end"],"on_hand_tonnes":row["on_hand_tonnes"],
                        "planned_demand_tonnes":settings["planned_demand_tonnes"],"suppliers":inputs["suppliers"],"outstanding_orders":row["public_pipeline"]}
                    verify_plan(row["plan"],context,settings,paths_from_rows(row["planning_scenarios"]),row["plan"]["provenance"]["risk"])
                    verified_plans+=1
    assert len(summaries)==15 and verified_plans==25
    return verified_plans


def verify(directory: Path,repeat: Path | None):
    manifest=read(directory/"manifest.json")
    assert manifest["holdout_locked"] and not manifest["actual_validation_procurement_evaluated"]
    close(manifest["config"]["risk"]["risk_weight"],.5)
    for group in ("output_sha256","code_sha256"):
        for name,value in manifest[group].items(): assert sha(ROOT/name)==value,name
    assert sha(ROOT/"configs/procurement/risk.toml")==manifest["config_sha256"]
    preservation=read(ROOT/"artifacts/day8/preservation_before.json")
    for name,value in preservation["sha256"].items(): assert sha(ROOT/name)==value,name
    for name,record in preservation.get("append_only",{}).items():
        assert hashlib.sha256((ROOT/name).read_bytes()[:record["bytes"]]).hexdigest()==record["sha256"]
    hands=read(directory/"hand_results.json")
    for row in hands:
        verify_plan(row,row["context"],row["settings"],paths_from_rows(row["scenarios"]),row["provenance"]["risk"])
        for key,value in zip(("expected_cost","var","cvar","objective"),row["expected_E_VaR_CVaR_objective"]): close(row[key],value)
    boundaries=read(directory/"boundary_results.json")
    for row in boundaries:
        case=next(h for h in hands if h["case"]==row["case"])
        verify_plan(row,case["context"],case["settings"],paths_from_rows(case["scenarios"]),row["provenance"]["risk"])
        if row["lambda"]==0: close(row["objective"],row["deterministic_mean_objective"])
        else: close(row["objective"],row["cvar"])
    synthetic=ROOT/manifest["synthetic_directory"]
    count=verify_toys(directory,synthetic)
    common=read(directory/"common_state_planning_risk.json")
    for row in common:
        assert not row["violations"]
        verify_plan(row,row["context"],row["settings"],paths_from_rows(row["scenarios"]),manifest["config"]["risk"],False)
    smokes=read(directory/"scenario_adapter_smoke.json")
    source=csv_rows(ROOT/manifest["config"]["scenario_run"]/"joint_price_scenarios.csv")
    for row in smokes:
        assert not row["actual_procurement_evaluated"]
        selected=[r for r in source if r["purpose"]=="planning" and r["forecast_origin"]==row["origin"] and r["source_model"]==row["model"]]
        close(len(row["scenarios"]),len(selected))
        for original,saved in zip(selected,row["scenarios"]):
            for key in original: assert str(original[key])==str(saved[key])
        verify_plan(row,row["context"],row["settings"],paths_from_rows(row["scenarios"]),row["provenance"]["risk"])
    assert len(smokes)==4
    timings=read(directory/"solver_timing.json")
    assert all(r["status"] in ("OPTIMAL","TERMINAL_NO_ACTION") and r["solve_seconds"]>=0 for r in timings)
    repeated=0
    if repeat:
        other=read(repeat/"manifest.json")
        assert manifest["config_sha256"]==other["config_sha256"] and manifest["code_sha256"]==other["code_sha256"]
        for parent,peer in ((directory,repeat),(synthetic,ROOT/other["synthetic_directory"])):
            for file in parent.iterdir():
                if file.is_file() and file.name not in ("manifest.json","spec_freeze.json","solver_timing.json"):
                    assert sha(file)==sha(peer/file.name),file.name
                    repeated+=1
    return {"passed":True,"protected_files":len(preservation["sha256"]),"append_only_documents":len(preservation.get("append_only",{})),
        "hand_plans":len(hands),"boundary_plans":len(boundaries),"risk_rolling_plans":count,"smoke_plans":len(smokes),
        "solver_events":len(timings),"deterministic_files_equal":repeated,"old_day7_fixed_forecast_ledgers_equal":30}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",type=Path,required=True)
    parser.add_argument("--repeat",type=Path)
    args=parser.parse_args()
    result=verify(args.run,args.repeat)
    output=ROOT/"artifacts/day8"/("verification_"+args.run.name+("_repeat" if args.repeat else "")+".json")
    with output.open("x",encoding="utf-8") as f: json.dump(result,f,indent=2)
    print(json.dumps(result,indent=2))
