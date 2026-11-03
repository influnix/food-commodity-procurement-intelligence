"""Calendar-sequential OOF release; future or unavailable actuals never form scores."""

from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from math import ceil, isfinite

from food_procurement_intelligence.evaluation.splits import (
    add_months, decision_at, HoldoutLockedError, LeakageError,
)
from food_procurement_intelligence.features.price import checked_history
from .contracts import UncertaintyPrediction, finite


@dataclass(frozen=True)
class OOFResidual:
    residual_forecast_origin: date
    residual_target_month: date
    residual_horizon: int
    residual_actual_available_at: datetime
    source_model: str
    source_method: str
    residual_value: float
    calibration_score: float
    actual_price: float
    fit_information_end: date
    fit_max_label_available_at: datetime
    first_released_at_origin: date
    phase: str

    def __post_init__(self) -> None:
        if self.residual_horizon not in (1, 2, 3) or self.residual_target_month != add_months(self.residual_forecast_origin, self.residual_horizon):
            raise LeakageError("Residual origin/horizon/target mismatch")
        if self.fit_information_end > add_months(self.residual_forecast_origin, -1):
            raise LeakageError("OOF target was not out of sample at fitting time")
        for stamp in (self.fit_max_label_available_at, self.residual_actual_available_at):
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise LeakageError("OOF timestamps must be timezone aware")
        if self.fit_max_label_available_at > decision_at(self.residual_forecast_origin):
            raise LeakageError("OOF fit used unpublished labels")
        if (self.residual_target_month > add_months(self.first_released_at_origin, -1)
                or self.residual_actual_available_at > decision_at(self.first_released_at_origin)):
            raise LeakageError("Residual released before actual publication")
        if self.phase not in ("historical_train", "validation") or not all(isfinite(v) for v in (self.residual_value, self.calibration_score, self.actual_price)):
            raise ValueError("Invalid OOF residual provenance/value")
        if self.calibration_score < 0 or self.actual_price <= 0:
            raise ValueError("Nonnegative scores and positive actual prices required")

    @property
    def key(self):
        return self.source_model, self.residual_forecast_origin, self.residual_horizon

    def record(self) -> dict:
        return {key: value.isoformat() if isinstance(value, datetime) else value.strftime("%Y-%m")
                if isinstance(value, date) else value for key, value in asdict(self).items()}


def assert_residual_available(residual: OOFResidual, calibration_origin: date, plan) -> None:
    partition = plan.target_partition(residual.residual_target_month)
    if partition not in ("train", "validation"):
        raise HoldoutLockedError("Bridge/holdout residuals are forbidden")
    if ((residual.phase == "historical_train" and partition != "train")
            or (residual.phase == "validation" and (partition != "validation"
                or not plan.validation_origin_start <= residual.residual_forecast_origin <= plan.validation_origin_end))):
        raise LeakageError("Residual phase does not match frozen partitions")
    if (residual.residual_forecast_origin >= calibration_origin
            or residual.residual_target_month > add_months(calibration_origin, -1)
            or residual.residual_actual_available_at > decision_at(calibration_origin)
            or residual.first_released_at_origin > calibration_origin):
        raise LeakageError("Calibration contains a future/unpublished residual")


class OOFPool:
    """Only forecasts enter pending; as-of histories alone can release their errors."""

    def __init__(self, plan):
        self.plan = plan
        self.pending: dict[tuple, tuple[UncertaintyPrediction, str]] = {}
        self.released: dict[tuple, OOFResidual] = {}
        self._target_keys: set[tuple] = set()
        self._last_release_origin: date | None = None

    def add(self, predictions, phase: str) -> None:
        for prediction in predictions:
            partition = self.plan.target_partition(prediction.target_month)
            if partition not in ("train", "validation"):
                raise HoldoutLockedError("Cannot add bridge/holdout OOF forecasts")
            if phase == "historical_train" and partition != "train":
                raise LeakageError("Historical OOF target must remain entirely in Train")
            if phase not in ("historical_train", "validation") or prediction.calibration_status != "raw_not_requested":
                raise ValueError("Only raw historical/validation OOF forecasts enter the pool")
            if phase == "validation" and not self.plan.validation_origin_start <= prediction.forecast_origin <= self.plan.validation_origin_end:
                raise LeakageError("Validation OOF origin outside frozen calendar")
            key = prediction.model_name, prediction.forecast_origin, prediction.horizon
            target_key = prediction.model_name, prediction.horizon, prediction.target_month
            if key in self.pending or key in self.released or target_key in self._target_keys:
                raise ValueError("Duplicate OOF forecast/target within a model and horizon")
            if self._last_release_origin and prediction.forecast_origin != self._last_release_origin:
                raise LeakageError("OOF forecasts must be added at the current sequential clock")
            self.pending[key] = prediction, phase
            self._target_keys.add(target_key)

    def release(self, store, origin: date) -> None:
        if self._last_release_origin and origin < self._last_release_origin:
            raise LeakageError("OOF pool clock cannot move backwards")
        history = checked_history(store.history_as_of(origin), origin)
        for key, (prediction, phase) in list(self.pending.items()):
            # No attempted value read for targets after t-1 or delayed publication.
            actual = history.get(prediction.target_month)
            if prediction.forecast_origin >= origin or actual is None or actual.price is None:
                continue
            if not prediction.interval_usable or not finite(prediction.point_prediction):
                continue
            score = max(prediction.lower_bound - actual.price, actual.price - prediction.upper_bound, 0.0)
            residual = OOFResidual(prediction.forecast_origin, prediction.target_month, prediction.horizon,
                actual.available_at, prediction.model_name, prediction.uncertainty_method,
                actual.price - prediction.point_prediction, score, actual.price,
                prediction.fit_information_end, prediction.fit_max_label_available_at, origin, phase)
            assert_residual_available(residual, origin, self.plan)
            self.released[key] = residual
            del self.pending[key]
        self._last_release_origin = origin


def finite_sample_adjustment(scores: list[float], coverage: float, minimum: int) -> tuple[float | None, int]:
    if not 0 < coverage < 1 or minimum < 1 or any(not isfinite(v) or v < 0 for v in scores):
        raise ValueError("Invalid conformal score/coverage/minimum")
    k = ceil((len(scores) + 1) * coverage)
    if len(scores) < minimum or k > len(scores):
        return None, k
    return sorted(scores)[k - 1], k


def calibrate(prediction: UncertaintyPrediction, residuals, plan, config: dict):
    selected = []
    for residual in residuals:
        # Do not silently accept a polluted pool, even if its other h is unselected.
        assert_residual_available(residual, prediction.forecast_origin, plan)
        if residual.source_model == prediction.model_name and residual.residual_horizon == prediction.horizon:
            if residual.source_method != prediction.uncertainty_method:
                raise ValueError("Calibration method mismatch")
            selected.append(residual)
    targets = [r.residual_target_month for r in selected]
    if len(set(targets)) != len(targets):
        raise ValueError("Repeated target in a horizon's calibration window")
    selected.sort(key=lambda r: (r.residual_target_month, r.residual_forecast_origin))
    eligible_n = len(selected)
    selected = selected[-config["calibration_window"]:]
    adjustment, rank = finite_sample_adjustment([r.calibration_score for r in selected],
        prediction.nominal_coverage, config["minimum_calibration_samples"])
    status = "calibrated" if adjustment is not None else "insufficient_raw_fallback"
    if not prediction.interval_usable:
        status, adjustment = "raw_invalid_uncalibrated", None
    stamp = max((r.residual_actual_available_at for r in selected), default=None)
    cutoff = max((r.residual_target_month for r in selected), default=None)
    result = replace(prediction, uncertainty_method=prediction.uncertainty_method + "_rolling_conformal",
        q10=None, q50=None, q90=None, base_q10=prediction.q10, base_q50=prediction.q50, base_q90=prediction.q90,
        lower_bound=prediction.lower_bound - adjustment if adjustment is not None else prediction.lower_bound,
        upper_bound=prediction.upper_bound + adjustment if adjustment is not None else prediction.upper_bound,
        calibration_sample_size=len(selected), calibration_cutoff=cutoff, calibration_max_available_at=stamp,
        calibration_status=status, calibration_adjustment=adjustment)
    # A raw crossing cannot become valid merely because interval-only q's are null.
    if not prediction.interval_usable:
        result = replace(result, lower_bound=None, upper_bound=None)
    audit = {"model_name": prediction.model_name, "calibration_origin": prediction.forecast_origin.strftime("%Y-%m"),
             "horizon": prediction.horizon, "status": status, "eligible_n": eligible_n, "selected_n": len(selected),
             "finite_sample_rank": rank, "adjustment": adjustment,
             "calibration_cutoff": cutoff.strftime("%Y-%m") if cutoff else None,
             "max_actual_available_at": stamp.isoformat() if stamp else None,
             "historical_n": sum(r.phase == "historical_train" for r in selected),
             "validation_n": sum(r.phase == "validation" for r in selected),
             "duplicate_targets_within_horizon": 0,
             "selected_residual_keys": [[r.source_model, r.residual_forecast_origin.strftime("%Y-%m"), r.residual_horizon] for r in selected]}
    return result, audit
