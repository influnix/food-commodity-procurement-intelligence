"""Read-only independent plan/ledger arithmetic, preservation and replay audit."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def jr(path): return json.loads(path.read_text(encoding="utf-8"))
def cr(path):
    with path.open(encoding="utf-8",newline="") as stream: return list(csv.DictReader(stream))
def plus(label,offset):
    y,m=map(int,label.split("-")); index=y*12+m-1+offset
    return f"{index//12:04d}-{index%12+1:02d}"
def same(a,b): assert math.isclose(float(a),float(b),abs_tol=1e-5,rel_tol=1e-9),(a,b)


def verify_plan(row,suppliers,settings):
    result=row["plan"]
    assert result["accepted"] and result["status"] in ("OPTIMAL","TERMINAL_NO_ACTION")
    if result["status"]=="TERMINAL_NO_ACTION":
        assert not row["executed_orders"]
        return
    v=result["variables"]; origin=row["origin"]; end=result["diagnostics"]["planning_end"]
    prices={p["target_month"]:p["predicted_price"] for p in row["forecasts"]}
    assert all(p["forecast_origin"]==origin and p["information_cutoff"]==plus(origin,-1) for p in row["forecasts"])
    fixed={}; pipeline_cost=0.
    for order in row["public_pipeline"]:
        s=suppliers[order["supplier_id"]]
        arrival=max(plus(order["promised_month"],s["nominal_delay_months"]),plus(origin,1))
        if arrival<=end:
            fixed[arrival]=fixed.get(arrival,0.)+order["quantity_tonnes"]
            pipeline_cost+=order["quantity_tonnes"]*(prices[arrival]*(1+s["price_premium"])+s["unit_transport_cost"])
        assert "actual_arrival" not in order
    new_cost=0.; incoming=dict(fixed); executed={r["supplier_id"]:r["quantity_tonnes"] for r in row["executed_orders"]}
    for key,quantity in v["q"].items():
        sid,k=key.split("|"); s=suppliers[sid]
        committed=sum(o["quantity_tonnes"] for o in row["public_pipeline"] if o["supplier_id"]==sid and o["order_month"]==k)
        assert -1e-7<=quantity<=s["monthly_capacity_tonnes"]-committed+1e-7
        allowed=plus(k,s["lead_time_months"]+s["maximum_delay_months"])<=end
        if not allowed: same(quantity,0)
        arrival=plus(k,s["lead_time_months"]+s["nominal_delay_months"])
        if allowed:
            new_cost+=quantity*(prices[arrival]*(1+s["price_premium"])+s["unit_transport_cost"])
            incoming[arrival]=incoming.get(arrival,0.)+quantity
        if k==origin: same(executed.get(sid,0),quantity)
    inventory=row["on_hand_tonnes"]
    holding=unmet_cost=0.
    for m in v["I"]:
        received=incoming.get(m,0.)
        same(v["R"][m],received)
        demand=settings["planned_demand_tonnes"]
        fulfilled=min(inventory+received,demand)
        unmet=demand-fulfilled
        stock=inventory+received-fulfilled
        waste=max(stock-settings["warehouse_capacity_tonnes"],0.)
        inventory=stock-waste
        same(v["I"][m],inventory); same(v["U"][m],unmet); same(v["W"][m],waste)
        assert -1e-7<=inventory<=settings["warehouse_capacity_tonnes"]+1e-7
        holding+=inventory*settings["holding_usd_per_tonne_month"]
        unmet_cost+=unmet*settings["unmet_usd_per_tonne"]
    terminal=settings["terminal_usd_per_tonne_deviation"]*abs(inventory-settings["terminal_target_tonnes"])
    same(result["objective"],new_cost+pipeline_cost+holding+unmet_cost+terminal)
    same(result["objective"],sum(result["components"].values()))
    assert result["diagnostics"]["ortools_verify_solution"] and not result["diagnostics"]["violations"]


def verify(directory,repeat=None):
    manifest=jr(directory/"manifest.json")
    for name,expected in manifest["output_sha256"].items(): assert sha(ROOT/name)==expected,name
    for name,expected in manifest["code_sha256"].items(): assert sha(ROOT/name)==expected,name
    before=jr(ROOT/"artifacts/day7/preservation_before.json")
    assert all(sha(ROOT/n)==h for n,h in before["sha256"].items())
    assert sha(ROOT/"configs/day7.toml")==manifest["config_sha256"]
    assert manifest["holdout_locked"] and not manifest["actual_validation_procurement_evaluated"] and manifest["fallback"] is None
    inputs=jr(ROOT/manifest["synthetic_directory"]/"comparison_inputs.json")
    assert inputs["initial_pipeline"]==[] and inputs["settings"]["initial_inventory_tonnes"]==200
    suppliers={s["supplier_id"]:s for s in inputs["suppliers"]}; settings=inputs["settings"]
    summaries={(r["case"],r["policy"]):r for r in jr(directory/"toy_comparison.json")}
    fold_count=0
    for world in inputs["worlds"]:
        market={p["month"]:p["price"] for p in world["prices"]}
        demand=dict(world["realized_demands"])
        delays={(s,m):d for s,m,d in world["delays"]}
        for policy in ("fixed","forecast_aware"):
            prefix=world["scenario_id"]+"__"+policy
            orders=cr(directory/(prefix+"_orders.csv")); receipts=cr(directory/(prefix+"_receipts.csv")); ledger=cr(directory/(prefix+"_ledger.csv"))
            assert all(o["initial_pipeline"]=="False" for o in orders)
            assert len(orders)==len(receipts)==len({r["order_id"] for r in receipts})
            order_map={o["order_id"]:o for o in orders}
            cohorts={}
            for order in orders:
                s=suppliers[order["supplier_id"]]; k=order["order_month"]
                same_order=(order["supplier_id"],k)
                cohorts[same_order]=cohorts.get(same_order,0.)+float(order["quantity_tonnes"])
                assert plus(k,s["lead_time_months"]+s["maximum_delay_months"])<=world["end"]
                assert cohorts[same_order]<=s["monthly_capacity_tonnes"]+1e-7
            for receipt in receipts:
                order=order_map[receipt["order_id"]]; s=suppliers[order["supplier_id"]]
                arrival=plus(order["promised_month"],delays.get((order["supplier_id"],order["order_month"]),0))
                assert receipt["receipt_month"]==arrival
                same(receipt["procurement_cost"],float(order["quantity_tonnes"])*market[arrival]*(1+s["price_premium"]))
            stock=200.
            for i,row in enumerate(ledger):
                m=row["month"]
                received=sum(float(r["quantity_tonnes"]) for r in receipts if r["receipt_month"]==m)
                procurement=sum(float(r["procurement_cost"]) for r in receipts if r["receipt_month"]==m)
                available=stock+received; served=min(available,demand[m]); unmet=demand[m]-served
                disposed=max(available-served-settings["warehouse_capacity_tonnes"],0.)
                ending=available-served-disposed
                same(row["beginning_inventory"],stock);same(row["received_quantity"],received)
                same(row["fulfilled_demand"],served);same(row["unmet_demand"],unmet);same(row["ending_inventory"],ending)
                terminal=settings["terminal_usd_per_tonne_deviation"]*abs(ending-settings["terminal_target_tonnes"]) if i==len(ledger)-1 else 0
                expected=procurement+ending*settings["holding_usd_per_tonne_month"]+unmet*settings["unmet_usd_per_tonne"]+disposed*settings["disposal_usd_per_tonne"]+terminal
                same(row["terminal_cost"],terminal);same(row["total_cost"],expected)
                stock=ending
            summary=summaries[(world["scenario_id"],policy)]
            for key in ("total_cost","procurement_cost","holding_cost","unmet_cost","unmet_demand"):
                same(summary[key],sum(float(r[key]) for r in ledger))
            same(summary["average_inventory"],sum(float(r["ending_inventory"]) for r in ledger)/len(ledger))
            assert summary["solver_failure_count"]==0 and summary["terminal_outstanding_tonnes"]==0
            if policy=="forecast_aware":
                history=jr(directory/(prefix+"_rolling_plans.json"))
                assert len(history)==len(ledger)
                for row,state in zip(history,ledger):
                    same(row["on_hand_tonnes"],state["ending_inventory"])
                    same(sum(r["quantity_tonnes"] for r in row["executed_orders"]),state["new_order_quantity"])
                    verify_plan(row,suppliers,settings)
                    fold_count+=1
    hand=jr(directory/"hand_lp_results.json")
    for row,expected in zip(hand,(80,220,112,210,6040)):
        same(row["objective"],expected);assert row["accepted"] and row["status"]=="OPTIMAL"
    smoke=jr(directory/"forecast_adapter_smoke.json")
    for row in smoke:
        assert row["accepted"] and not row["actual_procurement_evaluated"]
        assert row["origin"] in ("2021-06","2024-05")
        assert all(p["target_month"]<="2024-08" for p in row["forecasts"])
        fake={"origin":row["origin"],"on_hand_tonnes":200.,"public_pipeline":[],"forecasts":row["forecasts"],"plan":row,
              "executed_orders":[{"supplier_id":s,"quantity_tonnes":row["variables"]["q"].get(s+"|"+row["origin"],0.)} for s in suppliers]}
        verify_plan(fake,suppliers,settings)
    timing=jr(directory/"solver_timing.json")
    assert len(timing)==39 and sum(t["status"]=="OPTIMAL" for t in timing)==34
    assert all(math.isfinite(t["solve_seconds"]) and t["solve_seconds"]>=0 for t in timing)
    equal=None
    if repeat:
        other=jr(repeat/"manifest.json")
        assert manifest["code_sha256"]==other["code_sha256"] and manifest["config_sha256"]==other["config_sha256"]
        names=[p.name for p in directory.iterdir() if p.is_file() and p.name not in ("manifest.json","spec_freeze.json","solver_timing.json")]
        equal={name:sha(directory/name)==sha(repeat/name) for name in names}
        equal["synthetic/comparison_inputs.json"]=sha(ROOT/manifest["synthetic_directory"]/"comparison_inputs.json")==sha(ROOT/other["synthetic_directory"]/"comparison_inputs.json")
        assert all(equal.values())
    report={"passed":True,"run":directory.relative_to(ROOT).as_posix(),"protected_files_unchanged":len(before["sha256"]),
        "hand_lp_cases":5,"toy_policy_pairs":5,"rolling_decisions_audited":fold_count,"actual_forecast_plans_audited":len(smoke),
        "no_future_planned_orders_committed":True,"receipt_price_cost_and_terminal_audited":True,"repeated_bytes_equal":equal,
        "actual_validation_or_holdout_procurement_evaluated":False}
    target=ROOT/"artifacts/day7"/("verification_"+directory.name+("_repeat" if repeat else "")+".json")
    with target.open("x",encoding="utf-8") as stream:json.dump(report,stream,indent=2)
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--run",type=Path,required=True);parser.add_argument("--repeat",type=Path)
    args=parser.parse_args();print(json.dumps(verify(args.run.resolve(),args.repeat.resolve() if args.repeat else None),indent=2))
