"""GLOP procurement LP with independent numerical and physical plan checks."""

from dataclasses import dataclass, field
import math
from time import perf_counter

from food_procurement_intelligence.evaluation.splits import add_months, months_between
from food_procurement_intelligence.forecasting.common import ModelPrediction
from food_procurement_intelligence.simulation.contracts import DecisionContext, SimulationSettings


STATUS_NAMES = {0: "OPTIMAL", 1: "FEASIBLE", 2: "INFEASIBLE", 3: "UNBOUNDED", 4: "ABNORMAL", 5: "MODEL_INVALID", 6: "NOT_SOLVED"}


def month(value):
    return value.strftime("%Y-%m")


@dataclass
class PlanResult:
    status: str
    accepted: bool = False
    objective: float | None = None
    variables: dict = field(default_factory=dict)
    components: dict = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)
    solver_version: str | None = None
    solve_seconds: float = 0.0
    lp_text: str = ""

    def record(self) -> dict:
        return {key: getattr(self, key) for key in ("status", "accepted", "objective", "variables", "components", "diagnostics", "solver_version")}


def build_problem(context: DecisionContext, points: tuple[ModelPrediction, ...], settings: SimulationSettings, config: dict) -> dict:
    if config["planned_disposal"] != "zero_conservative" or config["horizon_months"] != 3:
        raise ValueError("Day 7 requires a three-month LP with no planned disposal")
    if context.origin >= context.simulation_end:
        return {"terminal_no_action": True}
    end = min(add_months(context.origin, 3), context.simulation_end)
    months = months_between(add_months(context.origin, 1), end)
    suppliers = {s.supplier_id: s for s in context.suppliers}
    if len(suppliers) != len(context.suppliers) or not suppliers:
        raise ValueError("Unique nonempty supplier catalogue required")
    if any(s.minimum_order_quantity != 0 or s.order_multiple != 0 for s in suppliers.values()):
        raise ValueError("Nonzero MOQ/order multiple requires a separately authorized model")
    if context.on_hand_tonnes > settings.warehouse_capacity_tonnes:
        raise ValueError("Public inventory exceeds warehouse capacity")
    if any(p.forecast_origin != context.origin for p in points) or len({p.horizon for p in points}) != len(points):
        raise ValueError("Point forecasts must share origin and unique horizons")
    if len({p.model_name for p in points}) != 1:
        raise ValueError("Do not mix forecast models in one deterministic path")
    prices = {p.target_month: p.predicted_price for p in points}
    if any(m not in prices or not math.isfinite(prices[m]) or prices[m] <= 0 for m in months):
        raise ValueError("Finite positive forecast needed for every planned delivery month")
    committed, pipeline, deferred = {}, [], []
    if len({o.order_id for o in context.outstanding_orders}) != len(context.outstanding_orders):
        raise ValueError("Duplicate confirmed order IDs")
    for order in context.outstanding_orders:
        supplier = suppliers[order.supplier_id]
        supplier.validate_quantity(order.quantity_tonnes)
        if order.promised_month != add_months(order.order_month, supplier.lead_time_months):
            raise ValueError("Confirmed pipeline promise/lead mismatch")
        if add_months(order.promised_month, supplier.maximum_delay_months) > context.simulation_end:
            raise ValueError("Confirmed pipeline violates global terminal admission rule")
        if add_months(order.promised_month, supplier.maximum_delay_months) <= context.origin:
            raise ValueError("Outstanding order is inconsistent with declared maximum delay")
        key = order.supplier_id, order.order_month
        committed[key] = committed.get(key, 0.0) + order.quantity_tonnes
        arrival = max(add_months(order.promised_month, supplier.nominal_delay_months), add_months(context.origin, 1))
        row = {"order_id": order.order_id, "supplier": order.supplier_id, "arrival": arrival, "quantity": order.quantity_tonnes}
        (pipeline if arrival <= end else deferred).append(row)
    q = []
    for supplier in context.suppliers:
        for order_month in months_between(context.origin, add_months(end, -1)):
            remaining = supplier.monthly_capacity_tonnes - committed.get((supplier.supplier_id, order_month), 0.0)
            if remaining < 0:
                raise ValueError("Confirmed supplier cohort exceeds monthly capacity")
            nominal = add_months(order_month, supplier.lead_time_months + supplier.nominal_delay_months)
            allowed = add_months(order_month, supplier.lead_time_months + supplier.maximum_delay_months) <= end
            q.append({"key": supplier.supplier_id + "|" + month(order_month), "supplier": supplier.supplier_id,
                      "order_month": order_month, "arrival": nominal, "upper": remaining if allowed else 0.0})
    return {"terminal_no_action": False, "context": context, "settings": settings, "months": months,
            "end": end, "prices": prices, "suppliers": suppliers, "q": q, "pipeline": pipeline, "deferred": deferred}


def inspect_solution(problem: dict, values: dict, objective: float, config: dict):
    """Do not trust solver status alone; check balances and engine-compatible flow."""
    tol = config["quantity_tolerance"]
    errors, max_violation = [], 0.0

    def check(name, violation):
        nonlocal max_violation
        if not math.isfinite(violation):
            errors.append(name + ":nonfinite")
        else:
            max_violation = max(max_violation, abs(violation))
            if abs(violation) > tol:
                errors.append(name)

    for group in values.values():
        for value in group.values():
            if not math.isfinite(value):
                return {}, {"violations": ["nonfinite_solution"], "max_quantity_violation": None}
    settings, suppliers = problem["settings"], problem["suppliers"]
    variable_procurement = variable_transport = fixed_procurement = fixed_transport = 0.0
    for q in problem["q"]:
        v = values["q"][q["key"]]
        check("q_lower:" + q["key"], max(-v, 0.0))
        check("q_upper:" + q["key"], max(v - q["upper"], 0.0))
        if q["upper"] > 0:
            supplier = suppliers[q["supplier"]]
            variable_procurement += v * problem["prices"][q["arrival"]] * (1 + supplier.price_premium)
            variable_transport += v * supplier.unit_transport_cost
    for order in problem["pipeline"]:
        supplier = suppliers[order["supplier"]]
        fixed_procurement += order["quantity"] * problem["prices"][order["arrival"]] * (1 + supplier.price_premium)
        fixed_transport += order["quantity"] * supplier.unit_transport_cost
    previous = problem["context"].on_hand_tonnes
    for m in problem["months"]:
        key = month(m)
        receipt = sum(o["quantity"] for o in problem["pipeline"] if o["arrival"] == m)
        receipt += sum(values["q"][q["key"]] for q in problem["q"] if q["arrival"] == m)
        check("receipt:" + key, values["R"][key] - receipt)
        inventory, unmet, waste = (values[name][key] for name in ("I", "U", "W"))
        check("inventory_balance:" + key, inventory - (previous + receipt - problem["context"].planned_demand_tonnes + unmet - waste))
        check("inventory_lower:" + key, max(-inventory, 0))
        check("inventory_upper:" + key, max(inventory - settings.warehouse_capacity_tonnes, 0))
        check("unmet_lower:" + key, max(-unmet, 0))
        check("unmet_upper:" + key, max(unmet - problem["context"].planned_demand_tonnes, 0))
        check("planned_disposal_zero:" + key, waste)
        available = previous + receipt
        physical_unmet = max(problem["context"].planned_demand_tonnes - available, 0.0)
        physical_waste = max(available - problem["context"].planned_demand_tonnes - settings.warehouse_capacity_tonnes, 0.0)
        check("greedy_unmet:" + key, unmet - physical_unmet)
        check("overflow_disposal:" + key, waste - physical_waste)
        previous = inventory
    delta = values["deviation"]["plus"] - values["deviation"]["minus"]
    check("terminal_deviation", previous - settings.terminal_target_tonnes - delta)
    for name, value in values["deviation"].items():
        check("deviation_nonnegative:" + name, max(-value, 0))
    components = {"new_procurement": variable_procurement, "pipeline_procurement_constant": fixed_procurement,
        "new_transport": variable_transport, "pipeline_transport_constant": fixed_transport,
        "holding": settings.holding_usd_per_tonne_month * sum(values["I"].values()),
        "unmet": settings.unmet_usd_per_tonne * sum(values["U"].values()),
        "disposal": settings.disposal_usd_per_tonne * sum(values["W"].values()),
        "planning_terminal": settings.terminal_usd_per_tonne_deviation * sum(values["deviation"].values())}
    expected = math.fsum(components.values())
    if not math.isfinite(objective) or not math.isclose(expected, objective,
            abs_tol=config["objective_absolute_tolerance"], rel_tol=config["objective_relative_tolerance"]):
        errors.append("objective_reconstruction")
    return components, {"violations": errors, "max_quantity_violation": max_violation,
                        "reconstructed_objective": expected, "objective_difference": objective - expected}


def solve_plan(context, points, settings, config: dict, backend_factory=None) -> PlanResult:
    started = perf_counter()
    try:
        problem = build_problem(context, points, settings, config)
    except (ValueError, KeyError, TypeError) as error:
        return PlanResult("INVALID_INPUT", diagnostics={"error": f"{type(error).__name__}: {error}"})
    if problem["terminal_no_action"]:
        return PlanResult("TERMINAL_NO_ACTION", True, diagnostics={"reason": "no future planning month"})
    try:
        from ortools.linear_solver import pywraplp
        import ortools
        if ortools.__version__ != config["ortools_version"] or config["backend"] != "GLOP":
            raise ValueError("Frozen solver version/backend mismatch")
        solver = (backend_factory or pywraplp.Solver.CreateSolver)("GLOP")
        if solver is None:
            return PlanResult("BACKEND_UNAVAILABLE")
        solver.SetTimeLimit(config["time_limit_ms"])
        parameters = (f"primal_feasibility_tolerance: {config['primal_tolerance']}\n"
                      f"dual_feasibility_tolerance: {config['dual_tolerance']}\n"
                      f"random_seed: {config['random_seed']}\nuse_dual_simplex: true")
        if not solver.SetSolverSpecificParametersAsString(parameters):
            raise ValueError("GLOP parameter configuration failed")
        qvars = {q["key"]: solver.NumVar(0., q["upper"], "q_" + q["key"].replace("|", "_")) for q in problem["q"]}
        variables = {"q": qvars}
        for name in ("I", "U", "R", "W"):
            upper = settings.warehouse_capacity_tonnes if name == "I" else context.planned_demand_tonnes if name == "U" else 0. if name == "W" else solver.infinity()
            variables[name] = {month(m): solver.NumVar(0., upper, name + "_" + month(m)) for m in problem["months"]}
        bound = settings.warehouse_capacity_tonnes + settings.terminal_target_tonnes
        variables["deviation"] = {key: solver.NumVar(0., bound, "terminal_" + key) for key in ("plus", "minus")}
        previous = context.on_hand_tonnes
        for m in problem["months"]:
            key = month(m)
            fixed = sum(o["quantity"] for o in problem["pipeline"] if o["arrival"] == m)
            incoming = solver.Sum([qvars[q["key"]] for q in problem["q"] if q["arrival"] == m])
            solver.Add(variables["R"][key] == fixed + incoming, "receipt_" + key)
            solver.Add(variables["I"][key] == previous + variables["R"][key] - context.planned_demand_tonnes + variables["U"][key] - variables["W"][key], "balance_" + key)
            previous = variables["I"][key]
        solver.Add(previous - settings.terminal_target_tonnes == variables["deviation"]["plus"] - variables["deviation"]["minus"], "terminal_deviation")
        objective = solver.Objective()
        for q in problem["q"]:
            if q["upper"] > 0:
                supplier = problem["suppliers"][q["supplier"]]
                cost = problem["prices"][q["arrival"]] * (1 + supplier.price_premium) + supplier.unit_transport_cost
                objective.SetCoefficient(qvars[q["key"]], cost)
        offset = sum(o["quantity"] * (problem["prices"][o["arrival"]] * (1 + problem["suppliers"][o["supplier"]].price_premium)
                    + problem["suppliers"][o["supplier"]].unit_transport_cost) for o in problem["pipeline"])
        objective.SetOffset(offset)
        for name, coefficient in (("I", settings.holding_usd_per_tonne_month), ("U", settings.unmet_usd_per_tonne), ("W", settings.disposal_usd_per_tonne), ("deviation", settings.terminal_usd_per_tonne_deviation)):
            for var in variables[name].values():
                objective.SetCoefficient(var, coefficient)
        objective.SetMinimization()
        lp_text = solver.ExportModelAsLpFormat(False)
        status_code = solver.Solve()
        status = STATUS_NAMES.get(status_code, "UNKNOWN_STATUS")
        result = PlanResult(status, solver_version=solver.SolverVersion(), lp_text=lp_text)
        result.diagnostics.update(status_code=status_code, constraints=solver.NumConstraints(), variable_count=solver.NumVariables(),
            deferred_pipeline=[{**o, "arrival": month(o["arrival"])} for o in problem["deferred"]],
            planning_end=month(problem["end"]), iterations=solver.iterations(), fallback=None)
        if status_code not in (0, 1):
            result.solve_seconds = perf_counter() - started
            return result
        result.variables = {name: {key: var.solution_value() for key, var in group.items()} for name, group in variables.items()}
        result.objective = objective.Value()
        result.components, checks = inspect_solution(problem, result.variables, result.objective, config)
        result.diagnostics.update(checks)
        result.diagnostics["ortools_verify_solution"] = solver.VerifySolution(config["quantity_tolerance"], False)
        result.accepted = (status == "OPTIMAL" and not checks["violations"] and result.diagnostics["ortools_verify_solution"])
        result.solve_seconds = perf_counter() - started
        return result
    except Exception as error:
        return PlanResult("ABNORMAL", diagnostics={"error": f"{type(error).__name__}: {error}"}, solve_seconds=perf_counter() - started)
