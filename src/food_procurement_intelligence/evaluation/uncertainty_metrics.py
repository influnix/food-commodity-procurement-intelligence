"""Explicit uncertainty metric denominators, including incomplete/invalid keys."""

from collections import Counter
from statistics import fmean

from food_procurement_intelligence.uncertainty.contracts import finite


def pinball(actual: float, forecast: float, quantile: float) -> float:
    if not finite(actual) or not finite(forecast) or not 0 < quantile < 1:
        raise ValueError("Pinball requires finite values and an interior quantile")
    error = actual - forecast
    return error * (quantile - int(error < 0))


def score_predictions(predictions, actuals: dict, expected_keys: set) -> list[dict]:
    seen, rows = set(), []
    for prediction in predictions:
        key = prediction.forecast_origin.strftime("%Y-%m"), prediction.horizon
        if prediction.key in seen or key not in expected_keys:
            raise ValueError("Duplicate or unexpected uncertainty forecast key")
        seen.add(prediction.key)
        actual = actuals[key]
        if actual["target_month"] != prediction.target_month.strftime("%Y-%m") or actual["unit"] != prediction.unit:
            raise ValueError("Uncertainty models must share the same target/unit/actual contract")
        value = actual["actual_price"]
        usable = prediction.interval_usable
        rows.append({**prediction.record(), "actual_price": value,
                     "covered": int(prediction.lower_bound <= value <= prediction.upper_bound) if usable else None,
                     "interval_width": prediction.upper_bound - prediction.lower_bound if usable else None,
                     **{f"pinball_q{int(q * 100)}": pinball(value, f, q) if finite(f) else None
                        for q, f in ((.1, prediction.q10), (.5, prediction.q50), (.9, prediction.q90))}})
    return rows


def summarize_uncertainty(rows: list[dict], expected_keys: set) -> list[dict]:
    groups = sorted({(row["model_name"], row["uncertainty_method"]) for row in rows})
    result = []
    for model, method in groups:
        for h in (1, 2, 3, "Overall"):
            subset = [row for row in rows if row["model_name"] == model and row["uncertainty_method"] == method
                      and (h == "Overall" or row["horizon"] == h)]
            expected = {key for key in expected_keys if h == "Overall" or key[1] == h}
            keys = {(row["forecast_origin"], row["horizon"]) for row in subset}
            if len(keys) != len(subset) or keys - expected:
                raise ValueError("Uncertainty summary key mismatch")
            intervals = [row for row in subset if row["covered"] is not None]
            widths = [row["interval_width"] for row in intervals]
            summary = {"model_name": model, "method": method, "horizon": h, "expected_n": len(expected),
                       "record_n": len(subset), "missing_keys": len(expected - keys), "interval_n": len(intervals),
                       "undefined_interval_n": len(expected) - len(intervals),
                       "unique_targets": len({row["target_month"] for row in subset}),
                       "empirical_coverage": fmean(row["covered"] for row in intervals) if intervals else None,
                       "covered_n": sum(row["covered"] for row in intervals),
                       "average_interval_width": fmean(widths) if widths else None,
                       "max_interval_width": max(widths) if widths else None,
                       "negative_boundary_n": sum(any(finite(row[key]) and row[key] < 0 for key in ("lower_bound", "upper_bound")) for row in subset),
                       "nonpositive_boundary_n": sum(any(finite(row[key]) and row[key] <= 0 for key in ("lower_bound", "upper_bound")) for row in subset),
                       "crossing_n": sum(row["quantile_crossing"] for row in subset),
                       "validity_counts": dict(Counter(row["validity_status"] for row in subset)),
                       "calibration_status_counts": dict(Counter(row["calibration_status"] for row in subset))}
            for q in (10, 50, 90):
                values = [row[f"pinball_q{q}"] for row in subset if row[f"pinball_q{q}"] is not None]
                summary[f"pinball_q{q}"] = fmean(values) if values else None
                summary[f"pinball_q{q}_n"] = len(values)
            result.append(summary)
    return result
