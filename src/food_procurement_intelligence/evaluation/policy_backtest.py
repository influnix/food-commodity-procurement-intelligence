"""Historical calendar adapter around the unchanged month-level simulation engine."""

from dataclasses import asdict, replace
from datetime import date
import math

from food_procurement_intelligence.evaluation.splits import add_months, months_between
from food_procurement_intelligence.simulation.contracts import DecisionContext, OpeningOrder
from food_procurement_intelligence.simulation.engine import run_simulation


class CalendarExecution:
    """Policy receives only public context, never world or evaluator capability."""

    def __init__(self, policy, first: date, last: date, history_provider):
        self.policy, self.first, self.last = policy, first, last
        self._history_provider = history_provider
        self.decisions: list[dict] = []
        self.runoff: list[str] = []
        self.last_engine_origin = first

    def __call__(self, context):
        self.last_engine_origin = context.origin
        if context.origin > self.last:
            self.runoff.append(context.origin.strftime("%Y-%m"))
            return ()
        if context.origin < self.first or any(r["origin"] == context.origin for r in self.decisions):
            raise ValueError("Duplicate or out-of-calendar policy decision")
        public = replace(context, published_prices=tuple(self._history_provider(context.origin)))
        row = {"origin": context.origin, "context": asdict(public), "completed": False, "orders": []}
        self.decisions.append(row)
        requests = tuple(self.policy(public))
        row.update(completed=True, orders=[asdict(o) for o in requests])
        return requests


def run_historical_policy(world, settings, suppliers, policy, first: date, last: date, history_provider) -> dict:
    execution = CalendarExecution(policy, first, last, history_provider)
    try:
        if world.start != add_months(first, 1) or first > last or last >= world.end:
            raise ValueError("Initial state, decision calendar and runoff are inconsistent")
        initial = DecisionContext(first, world.end, settings.initial_inventory_tonnes,
            settings.planned_demand_tonnes, suppliers, (), ())
        first_orders = execution(initial)
        opening = tuple(OpeningOrder(f"{first:%Y-%m}|{o.supplier_id}|{i}", o.supplier_id, first, o.quantity_tonnes)
                        for i, o in enumerate(first_orders))
        result = run_simulation(world, settings, suppliers, execution, opening)
        for order in result["orders"]:
            order["engine_opening_from_first_decision"] = order["initial_pipeline"]
            order["initial_pipeline"] = False
        result["summary"]["engine_opening_after_first_decision_tonnes"] = result["summary"]["initial_pipeline_tonnes"]
        result["summary"]["initial_pipeline_tonnes"] = 0.
        if tuple(r["origin"] for r in execution.decisions) != months_between(first,last):
            raise ValueError("Incomplete decision calendar")
        if tuple(r["month"] for r in result["ledger"]) != months_between(world.start,world.end):
            raise ValueError("Incomplete ledger calendar")
        if tuple(execution.runoff) != tuple(m.strftime("%Y-%m") for m in months_between(add_months(last,1),world.end)):
            raise ValueError("Incomplete runoff calendar")
        for row in result["ledger"]:
            row["period"] = "active" if row["month"] <= last else "runoff"
        return {"complete": True, **result, "decision_audit": execution.decisions,
                "runoff_no_action": execution.runoff, "failure": None}
    except Exception as error:
        attempt = execution.last_engine_origin
        # Native engine aborts atomically: no failed-policy cost aggregate is fabricated.
        # This is a conservative confirmed prefix, not a reconstructed partial ledger.
        confirmed = min(add_months(attempt,-1),world.end)
        return {"complete": False, "failure": {"first_failure_origin": attempt,
            "error_type": type(error).__name__, "error": str(error),
            "completed_decisions": sum(r["completed"] for r in execution.decisions),
            "confirmed_ledger_through": confirmed if confirmed >= world.start else None,
            "failed_policy_partial_costs_available": False, "fallback": None},
            "decision_audit": execution.decisions, "runoff_no_action": execution.runoff,
            "ledger": [], "orders": [], "receipts": [], "summary": None}


COST_KEYS = ("procurement_cost", "transport_cost", "holding_cost", "unmet_cost", "disposal_cost", "terminal_cost", "total_cost")


def period_metrics(result: dict, period: str, suppliers) -> dict:
    rows = [r for r in result["ledger"] if period == "full" or r["period"] == period]
    total = {key: math.fsum(r[key] for r in rows) for key in (*COST_KEYS,"realized_demand","fulfilled_demand","unmet_demand")}
    total.update(period=period, ledger_months=len(rows),
        fill_rate=total["fulfilled_demand"]/total["realized_demand"] if total["realized_demand"] else None,
        stockout_months=sum(r["unmet_demand"]>1e-7 for r in rows),
        average_inventory=math.fsum(r["ending_inventory"] for r in rows)/len(rows) if rows else None,
        ending_inventory=rows[-1]["ending_inventory"] if rows else None)
    return total


def paired_comparison(results: dict, pairs: tuple[tuple[str,str,str], ...]) -> tuple[list[dict],list[dict]]:
    if not all(r["complete"] for r in results.values()):
        raise ValueError("No full comparison or ranking of incomplete policies")
    monthly, summaries = [], []
    for name,left,right in pairs:
        a,b=results[left]["ledger"],results[right]["ledger"]
        if [r["month"] for r in a] != [r["month"] for r in b]:
            raise ValueError("Paired evaluation calendars differ")
        for x,y in zip(a,b):
            monthly.append({"comparison":name,"left":left,"right":right,"month":x["month"],"period":x["period"],
                "fill_rate_difference":(x["fulfilled_demand"]/x["realized_demand"]-y["fulfilled_demand"]/y["realized_demand"])
                    if x["realized_demand"] and y["realized_demand"] else None,
                **{key+"_difference":x[key]-y[key] for key in (*COST_KEYS,"unmet_demand","fulfilled_demand","ending_inventory","new_order_quantity")}})
        for period in ("full","active","runoff"):
            values=[r for r in monthly if r["comparison"]==name and (period=="full" or r["period"]==period)]
            delta=math.fsum(r["total_cost_difference"] for r in values)
            base=math.fsum(r["total_cost"] for r in b if period=="full" or r["period"]==period)
            selected_a=[r for r in a if period=='full' or r['period']==period]
            selected_b=[r for r in b if period=='full' or r['period']==period]
            demand_a=math.fsum(r['realized_demand'] for r in selected_a)
            demand_b=math.fsum(r['realized_demand'] for r in selected_b)
            summaries.append({"comparison":name,"left":left,"right":right,"period":period,
                "cost_difference":delta,"cost_difference_ratio":delta/base if base else None,
                "unmet_difference":math.fsum(r["unmet_demand_difference"] for r in values),
                "fill_rate_difference":(math.fsum(r['fulfilled_demand'] for r in selected_a)/demand_a
                    -math.fsum(r['fulfilled_demand'] for r in selected_b)/demand_b) if demand_a and demand_b else None,
                "paired_months":len(values),"independent_months_assumed":False})
    return monthly,summaries
