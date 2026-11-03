"""Monthly Seasonal Naive: forecast target price from target minus 12 months."""

from dataclasses import asdict, dataclass
from datetime import date, datetime
import math

from food_procurement_intelligence.data.availability import DevelopmentPriceStore
from food_procurement_intelligence.evaluation.splits import ForecastSample, add_months, decision_at
from food_procurement_intelligence.features.price import checked_history


class ForecastUnavailableError(ValueError):
    """The exact seasonal reference observation is missing or unpublished."""


@dataclass(frozen=True)
class Prediction:
    forecast_origin: date
    information_cutoff: date
    target_month: date
    horizon: int
    predicted_price: float
    reference_month: date
    reference_available_at: str
    unit: str = "USD_per_metric_tonne"
    model_name: str = "seasonal_naive_12"

    def __post_init__(self) -> None:
        if self.horizon not in (1, 2, 3) or self.target_month != add_months(self.forecast_origin, self.horizon):
            raise ValueError("Prediction target/horizon schema mismatch")
        if self.information_cutoff != add_months(self.forecast_origin, -1):
            raise ValueError("Prediction information cutoff mismatch")
        if self.reference_month != add_months(self.target_month, -12) or self.reference_month > self.information_cutoff:
            raise ValueError("Invalid seasonal reference month")
        if self.unit != "USD_per_metric_tonne" or not math.isfinite(self.predicted_price) or self.predicted_price <= 0:
            raise ValueError("Invalid prediction unit/value")
        published = datetime.fromisoformat(self.reference_available_at)
        if published.tzinfo is None or published.utcoffset() is None or published > decision_at(self.forecast_origin):
            raise ValueError("Prediction reference was unpublished at origin")

    def record(self) -> dict:
        record = asdict(self)
        for key in ("forecast_origin", "information_cutoff", "target_month", "reference_month"):
            record[key] = record[key].strftime("%Y-%m")
        return {**record, "forecast_asof_at": decision_at(self.forecast_origin).isoformat(), "steps_from_latest_observation": self.horizon + 1}


def predict(store: DevelopmentPriceStore, sample: ForecastSample) -> tuple[Prediction, ...]:
    history = checked_history(store.history_as_of(sample.origin), sample.origin)
    result = []
    for horizon, target in zip(sample.horizons, sample.targets):
        reference = add_months(target, -12)
        value = history.get(reference)
        if value is None or value.price is None:
            raise ForecastUnavailableError(f"Seasonal reference missing/unpublished: {reference:%Y-%m}")
        # Existing Day 2 direct access guard rechecks month AND publication time.
        price = store.feature(reference, sample.origin)
        result.append(Prediction(sample.origin, sample.feature_cutoff, target, horizon, price, reference, value.available_at.isoformat(), value.unit))
    return tuple(result)
