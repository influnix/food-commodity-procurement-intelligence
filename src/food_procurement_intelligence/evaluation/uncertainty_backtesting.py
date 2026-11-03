"""Day 5 historical walk-forward, matured OOF calibration, then validation scoring."""

import argparse
import csv
from datetime import datetime, timezone
from importlib.metadata import version
import json
import math
from pathlib import Path
import sys
from time import perf_counter
import tomllib

from food_procurement_intelligence.data.audit import load_development_store
from food_procurement_intelligence.features.price import checked_history, FeatureUnavailableError
from food_procurement_intelligence.evaluation.model_backtesting import digest, load_context, save_csv, save_json
from food_procurement_intelligence.evaluation.splits import (
    add_months, decision_at, forecast_samples, months_between, parse_month_label, LeakageError,
)
from food_procurement_intelligence.uncertainty.calibration import OOFPool, calibrate
from food_procurement_intelligence.uncertainty.contracts import UncertaintyPrediction, finite
from food_procurement_intelligence.uncertainty.models import sarimax_intervals, lightgbm_quantiles
from .uncertainty_metrics import score_predictions, summarize_uncertainty


def load_day5_context(path: Path):
    config = tomllib.loads(path.read_text(encoding="utf-8"))
    root = (path.resolve().parent / config["project_root"]).resolve()
    for key in ("day4_config", "sarimax_point_run", "lightgbm_point_run", "report_root"):
        if not (root / config[key]).resolve().is_relative_to(root):
            raise ValueError("Day 5 path escapes project")
    if digest(root / config["day4_config"]) != config["day4_config_sha256"]:
        raise ValueError("Day 4 specification changed")
    _, d4, plan, spec = load_context(root / config["day4_config"])
    frozen = {"schema_version": 1, "holdout_locked": True, "quantiles": [.1, .5, .9], "nominal_coverage": .8,
              "historical_origins": 60, "calibration_window": 60, "minimum_calibration_samples": 24,
              "calibration_score": "max(lower_minus_actual,actual_minus_upper,0)",
              "finite_quantile": "ceil((n+1)*coverage)_order_statistic_no_interpolation",
              "calibration_fallback": "raw_interval_explicit_insufficient_status",
              "quantile_crossing_policy": "record_invalid_no_rearrangement", "positivity_policy": "retain_and_flag_no_clipping",
              "rise_threshold_fraction": .1, "wide_interval_reference_multiple": 1.0}
    if any(config[key] != value for key, value in frozen.items()):
        raise ValueError("Day 5 initial experiment must preserve its prerecorded specification")
    historical_end = add_months(plan.train_target_end, -3)
    if (parse_month_label(config["historical_origin_end"]) != historical_end
            or parse_month_label(config["historical_origin_start"]) != add_months(historical_end, -59)):
        raise ValueError("Historical OOF dates must be the last 60 complete Train origins")
    return root, config, d4, plan, spec


def point_links(root, config, d4) -> tuple[dict, dict]:
    """Export point values only. Saved actual columns never reach forecast/calibration."""
    points, links = {}, {}
    for model in ("sarimax", "lightgbm"):
        directory = root / config[model + "_point_run"]
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if manifest["config_sha256"] != config["day4_config_sha256"] or manifest["model"] != model:
            raise ValueError("Wrong Day 4 point artifact")
        for filename, expected in manifest["output_sha256"].items():
            if digest(directory / filename) != expected:
                raise ValueError("Existing Day 4 output changed")
        for relative, expected in manifest["code_sha256"].items():
            if digest(root / "src/food_procurement_intelligence" / relative) != expected:
                raise ValueError("Existing point code changed")
        with (directory / "predictions.csv").open(encoding="utf-8", newline="") as file:
            for row in csv.DictReader(file):
                key = d4[model]["model_name"], row["forecast_origin"], int(row["horizon"])
                if key in points:
                    raise ValueError("Duplicate Day 4 point key")
                points[key] = float(row["predicted_price"])
        links[model] = {"directory": directory.relative_to(root).as_posix(), "manifest_sha256": digest(directory / "manifest.json")}
    return points, links


def risk_signal(store, prediction, config) -> dict:
    history = checked_history(store.history_as_of(prediction.forecast_origin), prediction.forecast_origin)
    public = [v for v in history.values() if v.price is not None]
    reference = max(public, key=lambda v: v.month)
    threshold = reference.price * (1 + config["rise_threshold_fraction"])
    raw = prediction.calibration_status == "raw_not_requested"
    width = prediction.upper_bound - prediction.lower_bound if prediction.interval_usable else None
    return {"record_id": prediction.record()["record_id"], "model_name": prediction.model_name,
            "uncertainty_method": prediction.uncertainty_method,
            "forecast_origin": prediction.forecast_origin.strftime("%Y-%m"), "horizon": prediction.horizon,
            "target_month": prediction.target_month.strftime("%Y-%m"), "reference_month": reference.month.strftime("%Y-%m"),
            "reference_available_at": reference.available_at.isoformat(), "reference_price": reference.price,
            "rise_threshold_price": threshold,
            "raw_q90_exceeds_threshold": prediction.q90 > threshold if raw and finite(prediction.q90) else None,
            "interval_upper_exceeds_threshold": prediction.upper_bound > threshold if prediction.interval_usable else None,
            "wide_interval": width > reference.price * config["wide_interval_reference_multiple"] if width is not None else None,
            "event_probability": None, "probability_basis": "not_estimated; three quantiles do not define a distribution",
            "unit": prediction.unit}


def generate_uncertainty(store, plan, spec, d4, config, points=None, predictors=None, progress=None):
    """No validation truth reader is an argument; only mature history may feed OOF."""
    predictors = predictors or {"sarimax": sarimax_intervals, "lightgbm": lightgbm_quantiles}
    history_origins = months_between(parse_month_label(config["historical_origin_start"]), parse_month_label(config["historical_origin_end"]))
    val_origins = months_between(plan.validation_origin_start, plan.validation_origin_end)
    origins = history_origins + val_origins
    samples = forecast_samples(store.calendar, origins, plan.minimum_history_months)
    if tuple(s.origin for s in samples) != origins:
        raise ValueError("Incomplete OOF/validation calendar")
    candidates = forecast_samples(store.calendar, store.calendar, plan.minimum_sample_history_months)
    pool = OOFPool(plan)
    raw_oof, validation_predictions, audits, events, risks = [], [], [], [], []
    for index, sample in enumerate(samples):
        historical = sample.origin in history_origins
        phase = "historical_train" if historical else "validation"
        if historical and any(plan.target_partition(target) != "train" for target in sample.targets):
            raise LeakageError("Historical OOF target escaped Train")
        pool.release(store, sample.origin)
        current = []
        for model, predictor in predictors.items():
            try:
                if model == "sarimax":
                    predictions, fits = predictor(store, sample, d4[model])
                else:
                    predictions, fits = predictor(store, sample, d4[model], spec, candidates)
            except FeatureUnavailableError as error:
                predictions, fits = (), [{"model": model, "forecast_origin": sample.origin.strftime("%Y-%m"),
                    "horizon": "all", "status": "failed", "failure_reason": str(error), "warnings": []}]
            for event in fits:
                event["phase"] = phase
            events.extend(fits)
            supplied = {p.horizon: p for p in predictions}
            if len(supplied) != len(predictions) or set(supplied) - set(sample.horizons):
                raise ValueError("Unexpected or duplicate uncertainty keys")
            for h, target in zip(sample.horizons, sample.targets):
                prediction = supplied.get(h)
                if prediction is None:
                    prediction = UncertaintyPrediction(d4[model]["model_name"], model + ("_native" if model == "sarimax" else "_quantile"),
                        sample.origin, sample.feature_cutoff, target, h, None, None, None, None, None, None,
                        sample.feature_cutoff, decision_at(sample.origin))
                if (prediction.forecast_origin != sample.origin or prediction.target_month != target
                        or prediction.model_name != d4[model]["model_name"]):
                    raise ValueError("Uncertainty predictor violated origin/model/target contract")
                if not historical and points is not None and finite(prediction.point_prediction):
                    original = points[(prediction.model_name, sample.origin.strftime("%Y-%m"), h)]
                    if not math.isclose(prediction.point_prediction, original, rel_tol=0, abs_tol=1e-10):
                        raise ValueError("Day 5 recomputed point differs from unchanged Day 4 prediction")
                current.append(prediction)
                raw_oof.append({**prediction.record(), "phase": phase})
                if not historical:
                    corrected, audit = calibrate(prediction, tuple(pool.released.values()), plan, config)
                    validation_predictions.extend((prediction, corrected))
                    audits.append(audit)
                    risks.extend(risk_signal(store, p, config) for p in (prediction, corrected))
        pool.add(current, phase)
        if progress and (index + 1) % 12 == 0:
            progress({"completed_origins": index + 1, "total_origins": len(samples), "phase": phase,
                      "origin": sample.origin.strftime("%Y-%m"), "released_oof_residuals": len(pool.released)})
    return {"predictions": validation_predictions, "raw_oof": raw_oof, "audits": audits, "events": events,
            "risks": risks, "residuals": [r.record() for r in pool.released.values()],
            "pending_metadata": [{"model_name": p.model_name, "forecast_origin": p.forecast_origin.strftime("%Y-%m"),
                "horizon": p.horizon, "target_month": p.target_month.strftime("%Y-%m"), "phase": phase,
                "reason": "not_released_at_last_validation_clock_or_invalid_raw"} for p, phase in pool.pending.values()]}


def evaluate_uncertainty(store, plan, generated):
    # Only after ALL historical/validation forecasts and calibrations exist.
    reader = store.validation_actuals_reader()
    origins = months_between(plan.validation_origin_start, plan.validation_origin_end)
    samples = forecast_samples(store.calendar, origins, plan.minimum_history_months)
    actuals = {}
    for sample in samples:
        visible = reader.actuals_for(sample, decision_at(plan.selection_freeze_origin))
        for h, value in zip(sample.horizons, visible):
            actuals[(sample.origin.strftime("%Y-%m"), h)] = {
                "actual_price": value.price, "unit": value.unit, "target_month": value.month.strftime("%Y-%m")}
    expected = set(actuals)
    rows = score_predictions(generated["predictions"], actuals, expected)
    if len(expected) != 108 or len({v["target_month"] for v in actuals.values()}) != 38:
        raise ValueError("Frozen validation calendar changed")
    return rows, summarize_uncertainty(rows, expected)


def run_day5(path: Path) -> dict:
    root, config, d4, plan, spec = load_day5_context(path)
    points, links = point_links(root, config, d4)
    directory = root / config["report_root"] / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory.mkdir(parents=True, exist_ok=False)
    save_json(directory / "spec_freeze.json", {"created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": config, "day4_config": d4, "config_sha256": digest(path), "fit_started": False})
    store = load_development_store(root, root / d4["day2_config"])
    started = perf_counter()
    generated = generate_uncertainty(store, plan, spec, d4, config, points,
                                     progress=lambda item: print(json.dumps(item), flush=True))
    rows, metrics = evaluate_uncertainty(store, plan, generated)
    save_csv(directory / "sarimax_native_intervals.csv", [r for r in rows if r["uncertainty_method"] == "sarimax_native"])
    save_csv(directory / "lightgbm_quantiles.csv", [r for r in rows if r["uncertainty_method"] == "lightgbm_quantile"])
    save_csv(directory / "calibrated_intervals.csv", [r for r in rows if r["calibration_status"] != "raw_not_requested"])
    save_csv(directory / "all_oof_forecasts.csv", generated["raw_oof"])
    save_csv(directory / "historical_oof_calibration.csv", [r for r in generated["residuals"] if r["phase"] == "historical_train"])
    save_csv(directory / "validation_oof_calibration.csv", [r for r in generated["residuals"] if r["phase"] == "validation"])
    save_json(directory / "calibration_audit.json", generated["audits"])
    save_json(directory / "pending_oof_metadata.json", generated["pending_metadata"])
    save_json(directory / "fit_log.json", generated["events"])
    save_json(directory / "metrics.json", metrics)
    save_csv(directory / "uncertainty_comparison.csv", metrics)
    save_csv(directory / "risk_signals.csv", generated["risks"])
    failures = [e for e in generated["events"] if e["status"] != "success"]
    warnings = [{"model": e["model"], "origin": e["forecast_origin"], "horizon": e["horizon"],
                 "warnings": e.get("warnings", []) + e.get("import_warnings", [])}
                for e in generated["events"] if e.get("warnings") or e.get("import_warnings")]
    save_json(directory / "failures_and_warnings.json", {"failures": failures, "warnings": warnings,
        "fit_events": len(generated["events"]), "failed_fit_events": len(failures),
        "invalid_prediction_counts": {m["model_name"] + ":" + m["method"]: m["validity_counts"] for m in metrics if m["horizon"] == "Overall"}})
    save_json(directory / "timing.json", {"wall_seconds": perf_counter() - started,
        "fit_seconds": sum(e.get("fit_seconds", 0.0) for e in generated["events"]),
        "batch_preparation_seconds": sum(e.get("preparation_seconds", 0.0) for e in generated["events"])})
    package = root / "src/food_procurement_intelligence"
    sources = list((package / "uncertainty").glob("*.py")) + [Path(__file__), Path(__file__).with_name("uncertainty_metrics.py")]
    save_json(directory / "manifest.json", {"created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": config, "config_sha256": digest(path), "day4_config_sha256": digest(root / config["day4_config"]),
        "split_sha256": digest(root / d4["split_config"]), "point_links": links,
        "day2_input_config_sha256": digest(root / d4["day2_config"]),
        "source_data": json.loads((root / config["sarimax_point_run"] / "manifest.json").read_text(encoding="utf-8"))["processed_input"],
        "raw_sha256": json.loads((root / config["sarimax_point_run"] / "manifest.json").read_text(encoding="utf-8"))["raw_sha256"],
        "python": sys.version, "library_versions": {p: version(p) for p in ("statsmodels", "lightgbm", "numpy", "scipy", "pandas")},
        "code_sha256": {p.relative_to(package).as_posix(): digest(p) for p in sources},
        "output_sha256": {p.name: digest(p) for p in sorted(directory.iterdir()) if p.is_file()},
        "holdout_locked": True, "vintage_mode": "latest_vintage_pseudo_real_time",
        "no_search": True, "no_early_stopping": True, "raw_fit_fallback": None,
        "definition_boundary": plan.definition_boundary.strftime("%Y-%m"),
        "inference_limit": "108 dependent pairs share 38 target months; rolling OOF is not an exchangeability guarantee"})
    return {"report_dir": directory.relative_to(root).as_posix(), "metrics": [m for m in metrics if m["horizon"] == "Overall"],
            "failed_fit_events": len(failures)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/day5.toml"))
    args = parser.parse_args()
    print(json.dumps(run_day5(args.config), indent=2))
