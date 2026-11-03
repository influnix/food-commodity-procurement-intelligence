"""Leakage-safe monthly features and a fold-local future preprocessing boundary."""

from dataclasses import dataclass
from datetime import date
import math
from statistics import fmean, stdev
from typing import Sequence

from food_procurement_intelligence.data.availability import (
    DevelopmentPriceStore, VisiblePrice, assert_feature_available,
)
from food_procurement_intelligence.evaluation.splits import (
    ForecastSample, add_months, decision_at, eligible_training_samples,
)


class FeatureUnavailableError(ValueError):
    """A required lag/window is incomplete; no zero filling is performed."""


@dataclass(frozen=True)
class FeatureSpec:
    lags: tuple[int, ...] = (1, 3, 6, 12)
    rolling_windows: tuple[int, ...] = (3, 6, 12)
    rolling_std_ddof: int = 1
    monthly_change: bool = True
    yearly_change: bool = True
    missing_strategy: str = "fail_with_reason"
    scaling: str = "none"

    def __post_init__(self) -> None:
        if any(type(value) is not int or value < 1 for value in self.lags):
            raise ValueError("Lag offsets must be positive integers relative to origin")
        if any(type(value) is not int or value < 2 for value in self.rolling_windows):
            raise ValueError("Rolling windows must be integers >=2 for sample standard deviation")
        if len(set(self.lags)) != len(self.lags) or len(set(self.rolling_windows)) != len(self.rolling_windows):
            raise ValueError("Duplicate feature offsets")
        if self.rolling_std_ddof != 1 or self.missing_strategy != "fail_with_reason" or self.scaling != "none":
            raise ValueError("Day 3 uses sample std, explicit missing failures and no fitted preprocessing")


def checked_history(history: Sequence[VisiblePrice], origin: date) -> dict[date, VisiblePrice]:
    """Validate all dependencies before a statistic or forecast uses them."""
    values = {value.month: value for value in history}
    if len(values) != len(history):
        raise ValueError("Duplicate months in as-of history")
    assert_feature_available(list(values), origin, {month: value.available_at for month, value in values.items()})
    for value in values.values():
        if value.month.day != 1 or value.unit != "USD_per_metric_tonne":
            raise ValueError("Invalid monthly observation/unit schema")
        if value.price is not None and (not math.isfinite(value.price) or value.price <= 0):
            raise ValueError("Observed price must be finite and positive")
    return values


@dataclass(frozen=True)
class FeatureVector:
    forecast_origin: date
    information_cutoff: date
    target_month: date
    horizon: int
    values: dict[str, float | int]
    observed_dependencies: dict[str, tuple[date, ...]]
    latest_dependency_available_at: dict[str, str]
    known_in_advance: tuple[str, ...] = ("origin_calendar_month", "target_calendar_month", "forecast_horizon")

    def record(self) -> dict:
        return {
            "forecast_origin": self.forecast_origin.strftime("%Y-%m"),
            "feature_asof_at": decision_at(self.forecast_origin).isoformat(),
            "information_cutoff": self.information_cutoff.strftime("%Y-%m"),
            "target_month": self.target_month.strftime("%Y-%m"), "horizon": self.horizon,
            "price_unit": "USD_per_metric_tonne", **self.values,
        }

    def provenance(self) -> dict:
        return {
            "forecast_origin": self.forecast_origin.strftime("%Y-%m"),
            "target_month": self.target_month.strftime("%Y-%m"), "horizon": self.horizon,
            "observed_dependencies": {key: [month.strftime("%Y-%m") for month in months] for key, months in self.observed_dependencies.items()},
            "latest_dependency_available_at": self.latest_dependency_available_at,
            "known_in_advance": self.known_in_advance,
        }


def build_features(store: DevelopmentPriceStore, sample: ForecastSample, spec: FeatureSpec) -> tuple[FeatureVector, ...]:
    history = checked_history(store.history_as_of(sample.origin), sample.origin)
    features: dict[str, float | int] = {}
    dependencies: dict[str, tuple[date, ...]] = {}
    availability: dict[str, str] = {}

    def prices(name: str, offsets: Sequence[int]) -> list[float]:
        months = tuple(add_months(sample.origin, -offset) for offset in offsets)
        if any(month not in history or history[month].price is None for month in months):
            raise FeatureUnavailableError(f"Required lookback is missing/unpublished: {name}")
        dependencies[name] = months
        availability[name] = max(history[month].available_at for month in months).isoformat()
        return [history[month].price for month in months]  # type: ignore[misc]

    for lag in spec.lags:
        features[f"lag_{lag}"] = prices(f"lag_{lag}", [lag])[0]
    for window in spec.rolling_windows:
        mean_name, std_name = f"rolling_mean_{window}", f"rolling_std_{window}"
        window_prices = prices(mean_name, range(1, window + 1))
        features[mean_name], features[std_name] = fmean(window_prices), stdev(window_prices)
        dependencies[std_name], availability[std_name] = dependencies[mean_name], availability[mean_name]
    if spec.monthly_change:
        latest, previous = prices("monthly_change_fraction", [1, 2])
        features["monthly_change_fraction"] = latest / previous - 1
    if spec.yearly_change:
        latest, previous = prices("yearly_change_fraction", [1, 13])
        features["yearly_change_fraction"] = latest / previous - 1
    return tuple(FeatureVector(
        sample.origin, sample.feature_cutoff, target, horizon,
        {**features, "origin_calendar_month": sample.origin.month, "target_calendar_month": target.month, "forecast_horizon": horizon},
        dict(dependencies), dict(availability),
    ) for horizon, target in zip(sample.horizons, sample.targets))


@dataclass(frozen=True)
class TrainingBatch:
    """Only this mature, as-of batch may feed a future fitted preprocessor.

    No imputer/scaler is fitted today. Validation features/labels are not arguments
    of this interface. Future transform uses the preprocessor fitted to this batch.
    """
    evaluation_origin: date
    feature_vectors: tuple[FeatureVector, ...]
    target_values: tuple[float, ...]
    excluded_samples: tuple[dict, ...]


def build_training_batch(
    store: DevelopmentPriceStore, candidates: Sequence[ForecastSample],
    evaluation_origin: date, spec: FeatureSpec,
) -> TrainingBatch:
    mature = eligible_training_samples(candidates, evaluation_origin)
    store.assert_training_samples_available(mature, evaluation_origin)
    vectors, labels, excluded = [], [], []
    for sample in candidates:
        if sample not in mature:
            excluded.append({"origin": sample.origin.isoformat(), "reason": "unpublished_or_future_target"})
            continue
        try:
            features = build_features(store, sample, spec)
        except FeatureUnavailableError as error:
            excluded.append({"origin": sample.origin.isoformat(), "reason": str(error)})
            continue
        vectors.extend(features)
        labels.extend(store.training_targets(sample, evaluation_origin))
    return TrainingBatch(evaluation_origin, tuple(vectors), tuple(labels), tuple(excluded))
