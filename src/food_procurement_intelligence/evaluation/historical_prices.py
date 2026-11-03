"""Evaluator-only monthly Validation capability; no bridge or Holdout export."""

from dataclasses import dataclass
from datetime import date, datetime
import math
from typing import Protocol

from food_procurement_intelligence.data.availability import VisiblePrice
from food_procurement_intelligence.evaluation.splits import (
    ForecastSample, HoldoutLockedError, SplitPlan, add_months, decision_at, months_between,
)


class ActualReader(Protocol):
    def actuals_for(self, sample: ForecastSample, assessed_at: datetime) -> tuple[VisiblePrice, ...]: ...


class GuardedValidationPrices:
    """Capability owned by evaluator; fetch each unique target once, then freeze."""

    def __init__(self, reader: ActualReader, plan: SplitPlan):
        self._reader, self._plan = reader, plan
        self._cache: dict[date, VisiblePrice] = {}
        self.requests: list[str] = []

    def __repr__(self) -> str:
        return "GuardedValidationPrices(validation_only=True, values=redacted)"

    def month(self, target: date) -> VisiblePrice:
        if self._plan.target_partition(target) != "validation":
            raise HoldoutLockedError("Only Validation months may enter historical evaluation")
        if target not in self._cache:
            origin = min(add_months(target, -1), self._plan.validation_origin_end)
            h = (target.year-origin.year)*12+target.month-origin.month
            sample = ForecastSample(origin, (h,), (target,))
            values = self._reader.actuals_for(sample, decision_at(self._plan.selection_freeze_origin))
            if len(values) != 1:
                raise ValueError("Monthly evaluation reader must return exactly one observation")
            value = values[0]
            if (value.month != target or value.unit != "USD_per_metric_tonne" or value.price is None
                    or not math.isfinite(value.price) or value.price <= 0
                    or value.available_at.tzinfo is None
                    or value.available_at > decision_at(self._plan.selection_freeze_origin)):
                raise ValueError("Invalid or unavailable monthly evaluation observation")
            self._cache[target] = value
            self.requests.append(target.strftime("%Y-%m"))
        return self._cache[target]

    def frozen_path(self) -> tuple[VisiblePrice, ...]:
        return tuple(self.month(m) for m in months_between(self._plan.validation_target_start, self._plan.validation_target_end))


@dataclass(frozen=True)
class HistoricalEvaluationWorld:
    """Structural engine input, explicitly distinct from synthetic-only ToyWorld."""

    scenario_id: str
    start: date
    end: date
    prices: tuple[VisiblePrice, ...]
    realized_demands: tuple[tuple[date, float], ...]
    delays: tuple[tuple[str, date, int], ...] = ()
    knowledge_type: str = "historical_prices_synthetic_operations"

    def __post_init__(self) -> None:
        expected = months_between(self.start, self.end)
        if (self.knowledge_type != "historical_prices_synthetic_operations"
                or not expected or tuple(p.month for p in self.prices) != expected
                or tuple(m for m, _ in self.realized_demands) != expected):
            raise ValueError("Historical world requires one ordered price and demand per ledger month")
        if any(p.price is None or not math.isfinite(p.price) or p.price <= 0 or p.unit != "USD_per_metric_tonne" for p in self.prices):
            raise ValueError("Historical engine price/unit mismatch")
        if any(not math.isfinite(d) or d < 0 for _, d in self.realized_demands):
            raise ValueError("Invalid synthetic realized demand")
        if len({(s, m) for s, m, _ in self.delays}) != len(self.delays) or any(type(d) is not int or d < 0 for _, _, d in self.delays):
            raise ValueError("Invalid synthetic cohort delays")
