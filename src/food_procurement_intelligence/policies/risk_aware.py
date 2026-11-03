"""Execute only the current shared order of a verified planning-scenario LP."""

from dataclasses import asdict
import math

from food_procurement_intelligence.evaluation.splits import LeakageError
from food_procurement_intelligence.optimization.deterministic import month
from food_procurement_intelligence.optimization.scenario_lp import RiskPlanResult, solve_risk_plan
from food_procurement_intelligence.policies.forecast_aware import PlanningFailure
from food_procurement_intelligence.simulation.contracts import OrderRequest


class RiskAware:
    def __init__(self, scenario_provider, settings, lp: dict, risk: dict, planner=solve_risk_plan):
        self._provider, self._settings = scenario_provider, settings
        self._lp, self._risk, self._planner = dict(lp), dict(risk), planner
        self._last_origin = None
        self.history, self.solutions = [], []

    def __call__(self, context):
        if self._last_origin is not None and context.origin <= self._last_origin:
            raise LeakageError("Duplicate or backwards Risk-Aware decision")
        bundle = None
        if context.origin < context.simulation_end:
            bundle = self._provider(context.origin).for_policy(context.origin)
            result = self._planner(context, bundle, self._settings, self._lp, self._risk)
        else:
            result = RiskPlanResult("TERMINAL_NO_ACTION", True)
        self.solutions.append(result)
        row = {"origin": month(context.origin), "on_hand_tonnes": context.on_hand_tonnes,
               "public_pipeline": [asdict(o) for o in context.outstanding_orders],
               "planning_scenarios": bundle.records() if bundle else [], "plan": result.record(),
               "executed_orders": [], "normalization_absolute_tonnes": 0.}
        self.history.append(row)
        if not result.accepted or result.status not in ("OPTIMAL", "TERMINAL_NO_ACTION"):
            raise PlanningFailure(f"Risk-Aware aborted: {result.status}; {result.diagnostics}")
        requests = []
        for supplier in context.suppliers:
            raw = result.variables.get("q", {}).get(supplier.supplier_id + "|" + month(context.origin), 0.)
            committed = sum(o.quantity_tonnes for o in context.outstanding_orders
                if o.supplier_id == supplier.supplier_id and o.order_month == context.origin)
            capacity = supplier.monthly_capacity_tonnes - committed
            tol = self._lp["quantity_tolerance"]
            if not math.isfinite(raw) or raw < -tol or raw > capacity + tol:
                raise PlanningFailure("Risk-Aware current order violates capacity")
            quantity = 0. if abs(raw) <= tol else min(raw, capacity)
            row["normalization_absolute_tonnes"] += abs(raw-quantity)
            if quantity > 0:
                requests.append(OrderRequest(supplier.supplier_id, quantity))
        row["executed_orders"] = [asdict(o) for o in requests]
        self._last_origin = context.origin
        return tuple(requests)
