"""Development-only price access with explicit as-of and holdout guards."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping, Sequence

from .world_bank import PriceObservation
from food_procurement_intelligence.evaluation.splits import (
    ForecastSample, HoldoutLockedError, LeakageError, SplitPlan, add_months,
    assert_training_available, decision_at,
)


def assert_feature_available(
    months: Sequence[date], origin: date, availability: Mapping[date, datetime],
) -> None:
    """Reject both future observation months and delayed publications."""
    for month in months:
        if month > add_months(origin, -1):
            raise LeakageError("Feature observation exceeds the origin minus one month cutoff")
        stamp = availability[month]
        if stamp.tzinfo is None or stamp.utcoffset() is None or stamp > decision_at(origin):
            raise LeakageError("Feature publication is unavailable at decision time")


@dataclass(frozen=True)
class VisiblePrice:
    month: date
    price: float | None
    unit: str
    available_at: datetime


class ValidationActualsReader:
    """Evaluator-only capability, restricted to the selected validation window.

    The forecast/feature functions never receive this reader. It cannot serve
    train, bridge or holdout values, even with a later assessment timestamp.
    """

    def __init__(self, values: Sequence[VisiblePrice], plan: SplitPlan):
        self._plan = plan
        self._values = {value.month: value for value in values if plan.target_partition(value.month) == "validation"}

    def __repr__(self) -> str:
        return "ValidationActualsReader(validation_only=True, actuals=redacted)"

    def actuals_for(self, sample: ForecastSample, assessed_at: datetime) -> tuple[VisiblePrice, ...]:
        if any(self._plan.target_partition(target) != "validation" for target in sample.targets):
            raise HoldoutLockedError("Scoring reader only permits validation target months")
        if not self._plan.validation_origin_start <= sample.origin <= self._plan.validation_origin_end:
            raise ValueError("Forecast origin is outside the fixed validation window")
        if assessed_at.tzinfo is None or assessed_at.utcoffset() is None:
            raise LeakageError("Assessment timestamp must be timezone-aware")
        if assessed_at > decision_at(self._plan.selection_freeze_origin):
            raise LeakageError("Validation assessment exceeds its selection-freeze clock")
        values = []
        for target in sample.targets:
            value = self._values.get(target)
            if value is None or value.price is None:
                raise LookupError("Validation actual is missing")
            if value.available_at > assessed_at:
                raise LeakageError("Validation actual has not been published at assessment time")
            values.append(value)
        return tuple(values)


class DevelopmentPriceStore:
    """Expose historical values, never holdout labels or holdout-origin histories.

    There is deliberately no unlock flag/method or unfiltered public row export.
    This is an API guard, not OS-level protection for the existing raw/CSV files.
    """

    def __init__(self, records: Sequence[PriceObservation], plan: SplitPlan):
        self._plan = plan
        self._values = tuple(
            VisiblePrice(record.date, record.price, record.unit, datetime.fromisoformat(record.available_at))
            for record in records
        )
        if len({value.month for value in self._values}) != len(self._values):
            raise ValueError("Duplicate observation months in price store")
        if any(value.available_at.tzinfo is None or value.available_at.utcoffset() is None for value in self._values):
            raise LeakageError("Availability timestamps must be timezone-aware")
        self._availability = {value.month: value.available_at for value in self._values}

    def __repr__(self) -> str:
        return "DevelopmentPriceStore(holdout_locked=True, prices=redacted)"

    @property
    def calendar(self) -> tuple[date, ...]:
        return tuple(value.month for value in self._values)

    def _check_origin(self, origin: date) -> None:
        if origin >= self._plan.selection_freeze_origin:
            raise HoldoutLockedError("Holdout-origin value access requires a later authorized final evaluator")

    def history_as_of(self, origin: date) -> tuple[VisiblePrice, ...]:
        self._check_origin(origin)
        return tuple(
            value for value in self._values
            if value.month <= add_months(origin, -1)
            and value.month <= self._plan.validation_target_end
            and value.available_at <= decision_at(origin)
        )

    def feature(self, month: date, origin: date) -> float:
        self._check_origin(origin)
        if month > self._plan.validation_target_end:
            raise HoldoutLockedError("Bridge and holdout values are excluded from development access")
        assert_feature_available([month], origin, self._availability)
        values = [value for value in self._values if value.month == month]
        if not values or values[0].price is None:
            raise LookupError("Requested feature is missing")
        return values[0].price

    def training_targets(self, sample: ForecastSample, evaluation_origin: date) -> tuple[float, ...]:
        self._check_origin(evaluation_origin)
        assert_training_available([sample], evaluation_origin, self._availability)
        return tuple(self.feature(target, evaluation_origin) for target in sample.targets)

    def assert_training_samples_available(self, samples: Sequence[ForecastSample], evaluation_origin: date) -> None:
        """Reuse Day 2 maturity checks without exporting any target values."""
        self._check_origin(evaluation_origin)
        assert_training_available(samples, evaluation_origin, self._availability)

    def validation_actuals_reader(self) -> ValidationActualsReader:
        """Only the backtest evaluator requests this; it is not a holdout unlock."""
        return ValidationActualsReader(self._values, self._plan)
