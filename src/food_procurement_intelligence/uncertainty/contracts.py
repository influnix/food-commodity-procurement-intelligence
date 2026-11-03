"""Separate uncertainty contract: never overwrite the Day 4 point forecast."""

from dataclasses import asdict, dataclass
from datetime import date, datetime
import math
from .validity import finite_number, validate_forecast

from food_procurement_intelligence.evaluation.splits import add_months, decision_at, LeakageError


def finite(value: float | None) -> bool:
    return finite_number(value)


@dataclass(frozen=True)
class UncertaintyPrediction:
    model_name: str
    uncertainty_method: str
    forecast_origin: date
    information_cutoff: date
    target_month: date
    horizon: int
    point_prediction: float | None
    q10: float | None
    q50: float | None
    q90: float | None
    lower_bound: float | None
    upper_bound: float | None
    fit_information_end: date
    fit_max_label_available_at: datetime
    nominal_coverage: float = .8
    calibration_sample_size: int = 0
    calibration_cutoff: date | None = None
    calibration_max_available_at: datetime | None = None
    calibration_status: str = "raw_not_requested"
    calibration_adjustment: float | None = None
    base_q10: float | None = None
    base_q50: float | None = None
    base_q90: float | None = None
    unit: str = "USD_per_metric_tonne"

    def __post_init__(self) -> None:
        if (not isinstance(self.model_name,str) or not self.model_name.strip()
                or not isinstance(self.uncertainty_method,str) or not self.uncertainty_method.strip()):
            raise ValueError('Explicit model and uncertainty method required')
        if type(self.horizon) is not int or self.horizon not in (1, 2, 3) or self.target_month != add_months(self.forecast_origin, self.horizon):
            raise ValueError("Uncertainty horizon/target mismatch")
        if self.information_cutoff != add_months(self.forecast_origin, -1):
            raise LeakageError("Uncertainty requires the t-1 cutoff")
        stamp = self.fit_max_label_available_at
        if (self.fit_information_end > self.information_cutoff or stamp.tzinfo is None
                or stamp.utcoffset() is None or stamp > decision_at(self.forecast_origin)):
            raise LeakageError("OOF forecast training information was not available")
        if self.unit != "USD_per_metric_tonne" or self.nominal_coverage != .8:
            raise ValueError("Unsupported uncertainty unit or nominal coverage")
        if self.calibration_max_available_at is not None:
            stamp = self.calibration_max_available_at
            if stamp.tzinfo is None or stamp.utcoffset() is None or stamp > decision_at(self.forecast_origin):
                raise LeakageError("Calibration publication exceeds forecast clock")
        if self.calibration_cutoff is not None and self.calibration_cutoff > self.information_cutoff:
            raise LeakageError("Calibration target exceeds t-1")

    @property
    def interval_usable(self) -> bool:
        return validate_forecast(self).calibration_usable

    @property
    def crossing(self) -> bool:
        values = (self.q10, self.q50, self.q90)
        return all(finite(value) for value in values) and not self.q10 <= self.q50 <= self.q90

    @property
    def validity_status(self) -> str:
        issues = validate_forecast(self).issues
        return ";".join(issues) or "valid"

    @property
    def key(self) -> tuple[str, date, int, str]:
        return self.model_name, self.forecast_origin, self.horizon, self.uncertainty_method

    def record(self) -> dict:
        row = asdict(self)
        for key, value in row.items():
            if isinstance(value, datetime):
                row[key] = value.isoformat()
            elif isinstance(value, date):
                row[key] = value.strftime("%Y-%m")
            elif isinstance(value, float) and not math.isfinite(value):
                row[key] = None
        row.update(forecast_asof_at=decision_at(self.forecast_origin).isoformat(),
                   validity_status=self.validity_status, interval_usable=self.interval_usable,
                   quantile_crossing=self.crossing, steps_from_latest_observation=self.horizon + 1,
                   record_id="|".join((self.model_name, self.forecast_origin.strftime("%Y-%m"),
                                       str(self.horizon), self.uncertainty_method)))
        return row
