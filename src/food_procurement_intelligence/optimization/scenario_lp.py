"""Shared-order, shared-flow price-scenario LP; no perfect-information recourse."""

from dataclasses import dataclass, field
import math
from time import perf_counter
from typing import Callable

from food_procurement_intelligence.evaluation.splits import add_months
from food_procurement_intelligence.forecasting.common import ModelPrediction
from food_procurement_intelligence.optimization.deterministic import (
    PlanResult, STATUS_NAMES, build_problem, inspect_solution, month,
)
from food_procurement_intelligence.uncertainty.joint_scenarios import ScenarioSet


@dataclass
class RiskPlanResult(PlanResult):
    expected_cost: float | None = None
    var: float | None = None
    cvar: float | None = None
    eta: float | None = None
    scenario_costs: list[dict] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    def record(self) -> dict:
        return {**super().record(), **{k: getattr(self, k) for k in (
            "expected_cost", "var", "cvar", "eta", "scenario_costs", "provenance")}}


def weighted_tail(costs: tuple[float, ...], weights: tuple[float, ...], alpha: float) -> dict:
    """Integrate exactly the worst 1-alpha probability mass, including partial atoms."""
    if (not math.isfinite(alpha) or not 0 < alpha < 1 or not costs or len(costs) != len(weights)
            or any(not math.isfinite(c) for c in costs)
            or any(not math.isfinite(w) or w <= 0 for w in weights)
            or not math.isclose(math.fsum(weights), 1., rel_tol=0, abs_tol=1e-12)):
        raise ValueError("Finite costs, positive unit-mass weights, and 0<alpha<1 required")
    ordered = sorted(zip(costs, weights))
    cumulative, var = 0., ordered[-1][0]
    for cost, weight in ordered:
        cumulative = math.fsum((cumulative, weight))
        if cumulative >= alpha - 1e-14:
            var = cost
            break
    remaining, terms = 1 - alpha, []
    for cost, weight in reversed(ordered):
        take = min(remaining, weight)
        terms.append(take * cost)
        remaining -= take
        if remaining <= 1e-14:
            break
    return {"expected_cost": math.fsum(c * w for c, w in zip(costs, weights)),
            "var": var, "cvar": math.fsum(terms) / (1 - alpha)}


def validate_scenarios(bundle: ScenarioSet, origin, risk: dict) -> None:
    bundle.for_policy(origin)
    if (not bundle.model or not bundle.method or not bundle.pool_sha256
            or len(bundle.paths) != risk["scenario_count"]
            or risk["non_anticipativity"] != "all_orders_and_physical_flows_shared"
            or risk["fallback"] != "none_abort"):
        raise ValueError("Wrong scenario cardinality, provenance or shared-order specification")
    if (type(bundle.seed) is not int or bundle.seed < 0
            or not 0 < risk["alpha"] < 1 or not math.isfinite(risk["alpha"])
            or not 0 <= risk["risk_weight"] <= 1 or not math.isfinite(risk["risk_weight"])):
        raise ValueError("Invalid seed, alpha or lambda")
    # Recheck at the consumer boundary, even if the immutable constructor was bypassed.
    if len({p.scenario_id for p in bundle.paths}) != len(bundle.paths):
        raise ValueError("Duplicate scenario ID")
    for path in bundle.paths:
        if len(path.prices) != 3 or any(not math.isfinite(p) or p <= 0 for p in path.prices):
            raise ValueError("All joint paths require three positive finite prices")
    weighted_tail(tuple(0. for _ in bundle.paths), tuple(p.weight for p in bundle.paths), risk["alpha"])


def mean_points(bundle: ScenarioSet) -> tuple[ModelPrediction, ...]:
    return tuple(ModelPrediction(bundle.origin, add_months(bundle.origin, -1), add_months(bundle.origin, h), h,
        math.fsum(p.weight * p.prices[h-1] for p in bundle.paths), bundle.model) for h in (1, 2, 3))


def scenario_problem(problem: dict, path) -> dict:
    origin = problem["context"].origin
    return {**problem, "prices": {add_months(origin, h): p for h, p in enumerate(path.prices, 1)}}


def non_anticipativity_errors(problem: dict, values: dict) -> list[str]:
    """One scalar per supplier/cohort and month; any scenario-indexed flow is forbidden."""
    expected = {"q": {q["key"] for q in problem["q"]}, "deviation": {"plus", "minus"},
                **{name: {month(m) for m in problem["months"]} for name in ("I", "U", "R", "W")}}
    if set(values) != set(expected):
        return ["scenario_indexed_or_missing_physical_group"]
    return ["non_anticipative_shape:" + group for group, keys in expected.items()
            if set(values[group]) != keys or any(not isinstance(v, (int, float)) for v in values[group].values())]


def price_plan(problem: dict, values: dict, bundle: ScenarioSet, risk: dict, lp: dict) -> dict:
    """Reprice a fixed, shared physical plan; does not optimize or read actual prices."""
    errors = non_anticipativity_errors(problem, values)
    if errors:
        return {"violations": errors}
    rows, maximum = [], 0.
    for path in bundle.paths:
        p = scenario_problem(problem, path)
        components, checks = inspect_solution(p, values, 0., lp)
        # inspect_solution independently computes all components; zero was only a placeholder.
        total = math.fsum(components.values())
        errors.extend(e for e in checks["violations"] if e != "objective_reconstruction")
        maximum = max(maximum, checks["max_quantity_violation"] or 0.)
        rows.append({"scenario_id": path.scenario_id, "probability": path.weight,
                     "components": components, "total_cost": total})
    summary = weighted_tail(tuple(r["total_cost"] for r in rows), tuple(r["probability"] for r in rows), risk["alpha"])
    summary["objective"] = (1-risk["risk_weight"]) * summary["expected_cost"] + risk["risk_weight"] * summary["cvar"]
    return {**summary, "scenario_costs": rows, "violations": sorted(set(errors)), "max_quantity_violation": maximum}


def solve_risk_plan(context, bundle, settings, lp: dict, risk: dict,
                    backend_factory: Callable | None = None) -> RiskPlanResult:
    started = perf_counter()
    try:
        validate_scenarios(bundle, context.origin, risk)
        problem = build_problem(context, mean_points(bundle), settings, lp)
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        return RiskPlanResult("INVALID_INPUT", diagnostics={"error": f"{type(error).__name__}: {error}"})
    provenance = {"model": bundle.model, "origin": month(bundle.origin), "purpose": bundle.purpose,
                  "method": bundle.method, "seed": str(bundle.seed), "pool_sha256": bundle.pool_sha256,
                  "scenario_count": len(bundle.paths), "unit": "USD_per_metric_tonne", "risk": dict(risk)}
    if problem["terminal_no_action"]:
        return RiskPlanResult("TERMINAL_NO_ACTION", True, provenance=provenance)
    try:
        import ortools
        from ortools.linear_solver import pywraplp
        if ortools.__version__ != lp["ortools_version"] or lp["backend"] != "GLOP":
            raise ValueError("Frozen solver version/backend mismatch")
        solver = (backend_factory or pywraplp.Solver.CreateSolver)("GLOP")
        if solver is None:
            return RiskPlanResult("BACKEND_UNAVAILABLE", provenance=provenance)
        solver.SetTimeLimit(lp["time_limit_ms"])
        parameters = (f"primal_feasibility_tolerance: {lp['primal_tolerance']}\n"
                      f"dual_feasibility_tolerance: {lp['dual_tolerance']}\n"
                      f"random_seed: {lp['random_seed']}\nuse_dual_simplex: true")
        if not solver.SetSolverSpecificParametersAsString(parameters):
            raise ValueError("GLOP parameter configuration failed")
        variables = {"q": {q["key"]: solver.NumVar(0., q["upper"], "shared_q_" + q["key"].replace("|", "_")) for q in problem["q"]}}
        for name in ("I", "U", "R", "W"):
            upper = settings.warehouse_capacity_tonnes if name == "I" else context.planned_demand_tonnes if name == "U" else 0. if name == "W" else solver.infinity()
            variables[name] = {month(m): solver.NumVar(0., upper, "shared_" + name + "_" + month(m)) for m in problem["months"]}
        bound = settings.warehouse_capacity_tonnes + settings.terminal_target_tonnes
        variables["deviation"] = {k: solver.NumVar(0., bound, "shared_terminal_" + k) for k in ("plus", "minus")}
        previous = context.on_hand_tonnes
        for m in problem["months"]:
            key = month(m)
            incoming = solver.Sum([variables["q"][q["key"]] for q in problem["q"] if q["arrival"] == m])
            fixed = sum(o["quantity"] for o in problem["pipeline"] if o["arrival"] == m)
            solver.Add(variables["R"][key] == fixed + incoming, "receipt_" + key)
            solver.Add(variables["I"][key] == previous + variables["R"][key] - context.planned_demand_tonnes + variables["U"][key] - variables["W"][key], "balance_" + key)
            previous = variables["I"][key]
        solver.Add(previous - settings.terminal_target_tonnes == variables["deviation"]["plus"] - variables["deviation"]["minus"], "terminal")
        common = solver.Sum([v * c for name, c in (("I", settings.holding_usd_per_tonne_month),
            ("U", settings.unmet_usd_per_tonne), ("W", settings.disposal_usd_per_tonne),
            ("deviation", settings.terminal_usd_per_tonne_deviation)) for v in variables[name].values()])
        eta = solver.NumVar(-solver.infinity(), solver.infinity(), "eta_USD")
        excess, costs = [], []
        for i, path in enumerate(bundle.paths):
            prices = scenario_problem(problem, path)["prices"]
            terms = [common]
            for q in problem["q"]:
                if q["upper"] > 0:
                    supplier = problem["suppliers"][q["supplier"]]
                    terms.append(variables["q"][q["key"]] * (prices[q["arrival"]] * (1+supplier.price_premium) + supplier.unit_transport_cost))
            terms.extend(o["quantity"] * (prices[o["arrival"]] * (1+problem["suppliers"][o["supplier"]].price_premium)
                + problem["suppliers"][o["supplier"]].unit_transport_cost) for o in problem["pipeline"])
            cost = solver.Sum(terms)
            xi = solver.NumVar(0., solver.infinity(), f"xi_{i:04d}_USD")
            solver.Add(xi >= cost-eta, f"tail_{i:04d}")
            costs.append(cost)
            excess.append(xi)
        mean = solver.Sum([p.weight*c for p, c in zip(bundle.paths, costs)])
        tail = eta + solver.Sum([p.weight*x for p, x in zip(bundle.paths, excess)]) / (1-risk["alpha"])
        solver.Minimize((1-risk["risk_weight"])*mean + risk["risk_weight"]*tail)
        result = RiskPlanResult("NOT_SOLVED", solver_version=solver.SolverVersion(),
                                lp_text=solver.ExportModelAsLpFormat(False), provenance=provenance)
        code = solver.Solve()
        result.status = STATUS_NAMES.get(code, "UNKNOWN_STATUS")
        result.diagnostics = {"status_code": code, "constraints": solver.NumConstraints(), "variable_count": solver.NumVariables(),
            "shared_physical_variables": sum(len(g) for g in variables.values()), "scenario_order_variables": 0,
            "non_anticipativity": "shared_variables_by_construction", "planning_end": month(problem["end"]),
            "deferred_pipeline": [{**o, "arrival": month(o["arrival"])} for o in problem["deferred"]],
            "iterations": solver.iterations(), "fallback": None, "tolerances": dict(lp)}
        if code not in (0, 1):
            result.solve_seconds = perf_counter()-started
            return result
        result.variables = {name: {k: v.solution_value() for k, v in group.items()} for name, group in variables.items()}
        result.objective, result.eta = solver.Objective().Value(), eta.solution_value()
        priced = price_plan(problem, result.variables, bundle, risk, lp)
        errors = priced["violations"]
        for name in ("expected_cost", "var", "cvar", "scenario_costs"):
            setattr(result, name, priced[name])
        result.components = {key: math.fsum(r["probability"] * r["components"][key] for r in result.scenario_costs)
                             for key in result.scenario_costs[0]["components"]}
        close = lambda a, b: math.isfinite(a) and math.isclose(a, b, abs_tol=lp["objective_absolute_tolerance"], rel_tol=lp["objective_relative_tolerance"])
        raw_xi = [x.solution_value() for x in excess]
        raw_costs = [c.solution_value() for c in costs]
        if not all(math.isfinite(v) for v in [result.eta, *raw_xi, *raw_costs]):
            raise ArithmeticError("Nonfinite tail auxiliary or scenario cost")
        max_epigraph = max([0.] + [max(row["total_cost"]-result.eta-x, -x, 0.) for row, x in zip(result.scenario_costs, raw_xi)])
        raw_tail = result.eta + math.fsum(p.weight*x for p, x in zip(bundle.paths, raw_xi))/(1-risk["alpha"])
        if any(not close(raw, row["total_cost"]) for raw, row in zip(raw_costs, result.scenario_costs)):
            errors.append("scenario_cost_reconstruction")
        if max_epigraph > lp["objective_absolute_tolerance"]:
            errors.append("tail_epigraph")
        if risk["risk_weight"] > 0 and not close(raw_tail, result.cvar):
            errors.append("cvar_reconstruction")
        if not close(result.objective, priced["objective"]):
            errors.append("mixed_objective_reconstruction")
        if result.cvar < result.expected_cost-lp["objective_absolute_tolerance"]:
            errors.append("cvar_below_mean")
        verified = solver.VerifySolution(lp["quantity_tolerance"], False)
        result.diagnostics.update(violations=errors, max_quantity_violation=priced["max_quantity_violation"],
            max_epigraph_violation_usd=max_epigraph, raw_epigraph_cvar=raw_tail, raw_xi=raw_xi,
            eta_identified_by_objective=risk["risk_weight"] > 0, ortools_verify_solution=verified,
            reconstructed_objective=priced["objective"], objective_difference=result.objective-priced["objective"],
            non_anticipativity_passed=not non_anticipativity_errors(problem, result.variables))
        result.accepted = result.status == "OPTIMAL" and verified and not errors
        result.solve_seconds = perf_counter()-started
        return result
    except Exception as error:
        return RiskPlanResult("ABNORMAL", diagnostics={"error": f"{type(error).__name__}: {error}"},
                              solve_seconds=perf_counter()-started, provenance=provenance)
