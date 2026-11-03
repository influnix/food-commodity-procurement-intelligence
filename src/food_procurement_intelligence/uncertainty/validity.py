"""Stage-specific validity: statistical bounds may be nonpositive; market points may not."""
from dataclasses import dataclass
from numbers import Real
import math
from typing import Any


def finite_number(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)


@dataclass(frozen=True)
class ForecastValidity:
    point_valid: bool
    quantile_valid: bool
    interval_valid: bool
    crossing: bool
    nonpositive_bound_review: bool
    issues: tuple[str, ...]

    @property
    def calibration_usable(self) -> bool:
        return self.point_valid and self.quantile_valid and self.interval_valid

    @property
    def states(self) -> tuple[str, ...]:
        states = []
        if not self.point_valid: states.append('INVALID_POINT')
        if self.crossing: states.append('QUANTILE_CROSSING')
        elif not self.quantile_valid: states.append('INVALID_QUANTILE')
        if not self.interval_valid: states.append('INVALID_INTERVAL')
        if self.nonpositive_bound_review: states.append('NONPOSITIVE_BOUND_REVIEW')
        return tuple(states) or ('VALID_RAW',)


def validate_forecast(prediction) -> ForecastValidity:
    """No mutation, clipping, q50/point substitution, sorting, or numeric coercion.

    Raw q10/q90 must equal raw interval endpoints. Interval-only calibrated rows
    retain the original triple in base_q*, so missing/invalid raw quantiles cannot
    disappear when current q* are deliberately null. Finite nonpositive bounds
    remain statistically usable with a review flag (Day5 contract).
    """
    p = prediction
    raw = p.calibration_status == 'raw_not_requested'
    q = (p.q10, p.q50, p.q90) if raw else (p.base_q10, p.base_q50, p.base_q90)
    point_valid = finite_number(p.point_prediction) and p.point_prediction > 0
    quantile_finite = all(finite_number(v) for v in q)
    crossing = quantile_finite and not q[0] <= q[1] <= q[2]
    interval_finite = finite_number(p.lower_bound) and finite_number(p.upper_bound)
    ordered = interval_finite and p.lower_bound <= p.upper_bound
    aligned = (not raw or not quantile_finite or not interval_finite
        or p.lower_bound == q[0] and p.upper_bound == q[2])
    issues = []
    if not finite_number(p.point_prediction): issues.append('missing_or_nonfinite_point')
    elif p.point_prediction <= 0: issues.append('nonpositive_point')
    if not interval_finite: issues.append('missing_or_nonfinite_interval')
    elif not ordered: issues.append('inverted_interval')
    if crossing: issues.append('quantile_crossing')
    if not quantile_finite: issues.append('missing_or_nonfinite_quantile')
    if not aligned: issues.append('quantile_interval_mismatch')
    review = any(finite_number(v) and v <= 0 for v in (*q,p.lower_bound,p.upper_bound))
    if review: issues.append('nonpositive_price_boundary')
    return ForecastValidity(point_valid, quantile_finite and not crossing and aligned,
        bool(ordered), bool(crossing), review, tuple(issues))


def assert_native_raw(prediction) -> None:
    """Valid positive point; finite aligned quantiles/bounds. Preserve crossing.

    Crossing remains a recorded invalid statistical interval, while its point can
    still supply Joint ratios. Negative finite statistical bounds are retained and
    flagged; actual observations and generated price paths still require >0.
    """
    v = validate_forecast(prediction)
    if not v.point_valid or any(not finite_number(x) for x in
        (prediction.q10,prediction.q50,prediction.q90,prediction.lower_bound,prediction.upper_bound)):
        raise ValueError('Invalid native point/quantile/interval; no fallback')
    if prediction.lower_bound != prediction.q10 or prediction.upper_bound != prediction.q90:
        raise ValueError('Raw quantile/interval endpoint mismatch')
    if not v.crossing and not v.interval_valid:
        raise ValueError('Invalid native interval; no fallback')
