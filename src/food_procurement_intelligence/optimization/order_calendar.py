"""Day 9 adds the prespecified order-calendar bounds to unchanged Day 7/8 LPs."""

from datetime import date
import re

from food_procurement_intelligence.evaluation.splits import parse_month_label
from food_procurement_intelligence.optimization.deterministic import solve_plan
from food_procurement_intelligence.optimization.scenario_lp import solve_risk_plan


class OrderCalendarSolver:
    """Delegate GLOP, restricting future cohort bounds before export and solve."""

    def __init__(self, inner, last_decision: date):
        self.inner, self.last_decision = inner, last_decision
        self.closed_variables: list[str] = []

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def _apply(self) -> None:
        self.closed_variables = []
        for variable in self.inner.variables():
            match = re.fullmatch(r"(?:shared_)?q_(.+)_([0-9]{4}-[0-9]{2})", variable.name())
            if match and parse_month_label(match[2]) > self.last_decision:
                variable.SetBounds(0., 0.)
                self.closed_variables.append(variable.name())

    def ExportModelAsLpFormat(self, obfuscate):
        self._apply()
        return self.inner.ExportModelAsLpFormat(obfuscate)

    def Solve(self):
        self._apply()
        return self.inner.Solve()


def calendar_planners(last_decision: date):
    """Return planners with the same extra calendar restriction for FA/RN/RA."""
    def execute(function, context, args):
        from ortools.linear_solver import pywraplp
        backends = []
        def factory(name):
            inner = pywraplp.Solver.CreateSolver(name)
            if inner is None:
                return None
            wrapped = OrderCalendarSolver(inner, last_decision)
            backends.append(wrapped)
            return wrapped
        result = function(context, *args, backend_factory=factory)
        forbidden = {key: value for key, value in result.variables.get("q", {}).items()
                     if parse_month_label(key.rsplit("|", 1)[1]) > last_decision}
        valid = all(abs(value) <= 1e-7 for value in forbidden.values())
        result.diagnostics.update(order_calendar_last=last_decision.strftime("%Y-%m"),
            calendar_bounds_closed=backends[0].closed_variables if backends else [],
            calendar_future_q=forbidden, calendar_passed=valid)
        result.accepted = result.accepted and valid and context.origin <= last_decision
        return result
    def point(context, points, settings, lp):
        return execute(solve_plan, context, (points, settings, lp))
    def risk(context, bundle, settings, lp, risk_config):
        return execute(solve_risk_plan, context, (bundle, settings, lp, risk_config))
    return point, risk
