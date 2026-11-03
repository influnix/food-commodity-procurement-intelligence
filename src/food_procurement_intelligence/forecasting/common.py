"""Point forecast contract shared by new models, without seasonal assumptions."""

from dataclasses import asdict, dataclass
from datetime import date
import math

from food_procurement_intelligence.evaluation.splits import add_months, decision_at


@dataclass(frozen=True)
class ModelPrediction:
    forecast_origin: date
    information_cutoff: date
    target_month: date
    horizon: int
    predicted_price: float
    model_name: str
    unit: str = "USD_per_metric_tonne"

    def __post_init__(self) -> None:
        if self.horizon not in (1, 2, 3) or self.target_month != add_months(self.forecast_origin, self.horizon):
            raise ValueError("Prediction target/horizon mismatch")
        if self.information_cutoff != add_months(self.forecast_origin, -1):
            raise ValueError("Prediction cutoff must be origin minus one month")
        if self.unit != "USD_per_metric_tonne" or not self.model_name:
            raise ValueError("Prediction unit/model name mismatch")
        if not math.isfinite(self.predicted_price) or self.predicted_price <= 0:
            raise ValueError("Nonpositive/nonfinite prediction; no clipping or fallback")

    def record(self) -> dict:
        record = asdict(self)
        for key in ("forecast_origin", "information_cutoff", "target_month"):
            record[key] = record[key].strftime("%Y-%m")
        return {**record, "forecast_asof_at": decision_at(self.forecast_origin).isoformat(), "steps_from_latest_observation": self.horizon + 1}


@dataclass(frozen=True)
class ModelFold:
    predictions: tuple[ModelPrediction, ...]
    events: tuple[dict, ...]


def adapt_seasonal_prediction(prediction) -> ModelPrediction:
    """Adapter only: leave the original Day 3 implementation and files intact."""
    return ModelPrediction(prediction.forecast_origin, prediction.information_cutoff, prediction.target_month,
                           prediction.horizon, prediction.predicted_price, prediction.model_name, prediction.unit)
