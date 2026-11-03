"""Receding-horizon point policy: commit only the current month's decisions."""

from dataclasses import asdict
from food_procurement_intelligence.evaluation.splits import LeakageError
from food_procurement_intelligence.simulation.contracts import OrderRequest
from food_procurement_intelligence.optimization.deterministic import solve_plan, month


class PlanningFailure(RuntimeError):
    pass


class ForecastAware:
    def __init__(self, forecast_provider, settings, config: dict, planner=solve_plan):
        self._forecast_provider, self._settings, self._config, self._planner = forecast_provider, settings, dict(config), planner
        self.history, self.solutions = [], []
        self._last_origin = None

    def __call__(self, context):
        if self._last_origin is not None and context.origin <= self._last_origin:
            raise LeakageError("A decision origin cannot be executed twice or replayed backwards")
        points = self._forecast_provider(context.origin) if context.origin < context.simulation_end else ()
        result = self._planner(context, points, self._settings, self._config)
        self.solutions.append(result)
        row = {"origin": month(context.origin), "on_hand_tonnes": context.on_hand_tonnes,
               "public_pipeline": [asdict(o) for o in context.outstanding_orders],
               "forecasts": [p.record() for p in points], "plan": result.record(), "executed_orders": [],
               "normalization_absolute_tonnes": 0.0}
        self.history.append(row)
        if not result.accepted:
            raise PlanningFailure(f"Forecast-Aware aborted: {result.status}; {result.diagnostics}")
        requests = []
        for supplier in context.suppliers:
            raw = result.variables.get("q", {}).get(supplier.supplier_id + "|" + month(context.origin), 0.0)
            committed = sum(o.quantity_tonnes for o in context.outstanding_orders if o.supplier_id == supplier.supplier_id and o.order_month == context.origin)
            capacity = supplier.monthly_capacity_tonnes - committed
            tol = self._config["quantity_tolerance"]
            if raw < -tol or raw > capacity + tol:
                raise PlanningFailure("Current order violates numerical capacity bounds")
            quantity = 0.0 if abs(raw) <= tol else min(raw, capacity)
            row["normalization_absolute_tonnes"] += abs(raw - quantity)
            if quantity > 0:
                requests.append(OrderRequest(supplier.supplier_id, quantity))
        row["executed_orders"] = [asdict(r) for r in requests]
        self._last_origin = context.origin
        return tuple(requests)
