"""MAE and seasonal MASE, using only each origin's published history."""

from dataclasses import dataclass
from datetime import date
import math
from statistics import fmean
from typing import Sequence

from food_procurement_intelligence.data.availability import VisiblePrice
from food_procurement_intelligence.evaluation.splits import add_months
from food_procurement_intelligence.features.price import checked_history


@dataclass(frozen=True)
class SeasonalScale:
    value: float | None
    pair_count: int
    status: str
    observed_through: date | None


def seasonal_scale(history: Sequence[VisiblePrice], origin: date) -> SeasonalScale:
    values = checked_history(history, origin)
    differences = [
        abs(value.price - values[add_months(month, -12)].price)
        for month, value in sorted(values.items())
        if value.price is not None and add_months(month, -12) in values
        and values[add_months(month, -12)].price is not None
    ]
    through = max(values) if values else None
    if not differences:
        return SeasonalScale(None, 0, "insufficient_seasonal_pairs", through)
    scale = fmean(differences)
    if scale == 0:
        return SeasonalScale(None, len(differences), "zero_seasonal_scale", through)
    return SeasonalScale(scale, len(differences), "ok", through)


def mean_absolute_error(errors: Sequence[float]) -> float | None:
    if any(not math.isfinite(error) for error in errors):
        raise ValueError("Nonfinite forecast error")
    return fmean(abs(error) for error in errors) if errors else None


def summarize_metrics(rows: Sequence[dict], expected_pairs: int) -> dict:
    """Equal pair weights; MASE is mean of individual |e|/scale_t ratios."""
    keys = [(row["forecast_origin"], row["horizon"]) for row in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate origin/horizon forecast keys")

    def summary(group: Sequence[dict]) -> dict:
        scaled = [row["scaled_error"] for row in group if row["scaled_error"] is not None]
        fixed = [row["fixed_initial_scaled_error"] for row in group if row["fixed_initial_scaled_error"] is not None]
        return {
            "n": len(group), "mae": mean_absolute_error([row["error"] for row in group]),
            "mase": fmean(scaled) if scaled else None, "mase_defined_n": len(scaled),
            "mase_undefined_n": len(group) - len(scaled),
            "mase_fixed_initial_asof": fmean(fixed) if fixed else None,
            "fixed_mase_defined_n": len(fixed),
        }
    return {
        "expected_pairs": expected_pairs, "evaluated_pairs": len(rows), "complete": len(rows) == expected_pairs,
        "overall": summary(rows),
        "by_horizon": {str(h): summary([row for row in rows if row["horizon"] == h]) for h in (1, 2, 3)},
        "by_origin": {str(origin): summary([row for row in rows if row["forecast_origin"] == origin]) for origin in sorted({row["forecast_origin"] for row in rows})},
        "mae_unit": "USD_per_metric_tonne", "mase_unit": "dimensionless",
        "primary_scale": "expanding_fold_asof", "comparison_scale": "fixed_first_validation_asof",
        "aggregation": "equal weights per origin/horizon pair; defined MASE ratios only, with missing counts",
    }
