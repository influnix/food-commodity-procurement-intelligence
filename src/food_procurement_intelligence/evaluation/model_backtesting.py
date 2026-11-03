"""Day 4 single-model phases and coverage-aware comparison of saved results."""

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
import hashlib
import json
import math
import os
from pathlib import Path
from statistics import fmean, median
import sys
import tomllib
from time import perf_counter

from food_procurement_intelligence.data.audit import load_development_store
from food_procurement_intelligence.evaluation.backtesting import run_validation
from food_procurement_intelligence.evaluation.forecast_metrics import seasonal_scale, summarize_metrics
from food_procurement_intelligence.evaluation.splits import (
    assert_no_target_overlap, decision_at, eligible_training_samples, forecast_samples,
    load_split_plans, months_between,
)
from food_procurement_intelligence.features.price import FeatureSpec, FeatureUnavailableError
from food_procurement_intelligence.forecasting.common import ModelFold


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as file:
        json.dump(value, file, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        file.write("\n")


def save_csv(path: Path, records: list[dict]) -> None:
    with path.open("x", encoding="utf-8", newline="") as file:
        if records:
            keys = list(dict.fromkeys(key for record in records for key in record))
            writer = csv.DictWriter(file, fieldnames=keys, lineterminator="\n")
            writer.writeheader()
            for record in records:
                writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list, tuple)) else v for k, v in record.items()})


def read_baseline(directory: Path) -> tuple[list[dict], dict]:
    manifest = json.loads((directory / "run_manifest.json").read_text(encoding="utf-8"))
    for filename, expected in manifest["output_sha256"].items():
        if digest(directory / filename) != expected:
            raise ValueError("Existing Day 3 baseline artifact changed")
    with (directory / "validation_predictions.csv").open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    numeric = ("predicted_price", "actual_price", "error", "absolute_error", "mase_scale", "scaled_error", "fixed_initial_scale", "fixed_initial_scaled_error")
    for row in rows:
        row["horizon"] = int(row["horizon"])
        for key in numeric:
            row[key] = float(row[key]) if row[key] else None
    return rows, manifest


def evaluate_model(store, plan, spec: FeatureSpec, config: dict, model: str, predictor=None) -> dict:
    origins = months_between(plan.validation_origin_start, plan.validation_origin_end)
    samples = forecast_samples(store.calendar, origins, plan.minimum_history_months)
    if tuple(sample.origin for sample in samples) != origins:
        raise ValueError("Incomplete frozen validation calendar")
    if any(plan.target_partition(target) != "validation" for sample in samples for target in sample.targets):
        raise ValueError("Evaluation attempted non-validation target")
    if predictor is None:
        if model == "sarimax":
            from food_procurement_intelligence.forecasting.sarimax import fit_predict
        elif model == "lightgbm":
            from food_procurement_intelligence.forecasting.lightgbm import fit_predict
        else:
            raise ValueError("Unknown model")
        predictor = fit_predict
    candidates = forecast_samples(store.calendar, store.calendar, plan.minimum_sample_history_months)
    prepared, events = [], []
    first_scale = seasonal_scale(store.history_as_of(origins[0]), origins[0])
    for sample in samples:
        mature = eligible_training_samples(candidates, sample.origin)
        store.assert_training_samples_available(mature, sample.origin)
        assert_no_target_overlap(mature, [sample])
        scale = seasonal_scale(store.history_as_of(sample.origin), sample.origin)
        try:
            if model == "sarimax":
                fold = predictor(store, sample, config)
            else:
                fold = predictor(store, sample, config, spec, candidates)
        except FeatureUnavailableError as error:
            # Expected insufficient current lookback is a recorded failed fold;
            # leakage/holdout violations remain hard errors and are not swallowed.
            fold = ModelFold((), ({"model_name": config["model_name"], "forecast_origin": sample.origin.strftime("%Y-%m"),
                                   "horizon": "all", "train_n": 0, "fit_seconds": 0.0, "predict_seconds": 0.0,
                                   "status": "failed", "failure_reason": str(error), "warnings": []},))
        for event in fold.events:
            event["mature_candidate_n"] = len(mature)
            event["last_mature_origin"] = mature[-1].origin.isoformat() if mature else None
        events.extend(fold.events)
        for prediction in fold.predictions:
            if prediction.forecast_origin != sample.origin or prediction.target_month not in sample.targets:
                raise ValueError("Model returned an unexpected prediction key")
        prepared.append((sample, fold.predictions, scale))
    # All model fitting is finished before any evaluation-only actual is read.
    reader = store.validation_actuals_reader()
    rows = []
    for sample, predictions, scale in prepared:
        actuals = {value.month: value for value in reader.actuals_for(sample, decision_at(plan.selection_freeze_origin))}
        for prediction in predictions:
            actual = actuals[prediction.target_month]
            if actual.unit != prediction.unit:
                raise ValueError("Model/actual units differ")
            error = actual.price - prediction.predicted_price
            rows.append({**prediction.record(), "actual_price": actual.price, "error": error, "absolute_error": abs(error),
                         "mase_scale": scale.value, "mase_scale_status": scale.status,
                         "scaled_error": abs(error) / scale.value if scale.value is not None else None,
                         "fixed_initial_scale": first_scale.value,
                         "fixed_initial_scaled_error": abs(error) / first_scale.value if first_scale.value is not None else None})
    expected = {(s.origin.strftime("%Y-%m"), h) for s in samples for h in s.horizons}
    actual_keys = {(row["forecast_origin"], row["horizon"]) for row in rows}
    metrics = summarize_metrics(rows, len(expected))
    metrics["missing_keys"] = [list(key) for key in sorted(expected - actual_keys)]
    metrics["complete"] = actual_keys == expected and len(rows) == len(expected)
    return {"rows": rows, "events": events, "metrics": metrics}


def timing_summary(events: list[dict]) -> dict:
    totals = {}
    for event in events:
        totals[event["forecast_origin"]] = totals.get(event["forecast_origin"], 0.0) + event["fit_seconds"]
    times = sorted(totals.values())
    index = .9 * (len(times) - 1)
    low = int(index)
    p90 = times[low] + (times[min(low + 1, len(times) - 1)] - times[low]) * (index - low) if times else None
    return {"total_fit_seconds": sum(times), "origin_fit_seconds": totals,
            "mean": fmean(times) if times else None, "median": median(times) if times else None,
            "min": min(times) if times else None, "max": max(times) if times else None, "p90": p90,
            "warning_count": sum(len(event.get("warnings", [])) + len(event.get("import_warnings", [])) for event in events),
            "total_import_seconds": sum(event.get("import_seconds", 0.0) for event in events),
            "total_batch_preparation_seconds": sum(event.get("batch_preparation_seconds", 0.0) for event in events),
            "failed_fit_events": sum(event["status"] != "success" for event in events)}


def load_context(config_path: Path):
    config_path = config_path.resolve()
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    root = (config_path.parent / config["project_root"]).resolve()
    if config["holdout_locked"] is not True or config["hyperparameter_search"] is not False or config["fallback"] != "none":
        raise ValueError("Day 4 requires locked holdout, no search and no fallback")
    for key in ("day2_config", "day3_config", "split_config", "baseline_run", "report_root"):
        if not (root / config[key]).resolve().is_relative_to(root):
            raise ValueError("Config path escapes project")
    if digest(root / config["split_config"]) != config["split_config_sha256"]:
        raise ValueError("Frozen split changed")
    # Process-local only, before lazy imports of scientific model libraries.
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[name] = str(config["threads"])
    plan, _ = load_split_plans(root / config["split_config"])
    d3 = tomllib.loads((root / config["day3_config"]).read_text(encoding="utf-8"))
    if digest(root / config["day2_config"]) != d3["day2_config_sha256"]:
        raise ValueError("Day 2 input config changed")
    features = dict(d3["features"])
    features["lags"], features["rolling_windows"] = tuple(features["lags"]), tuple(features["rolling_windows"])
    return root, config, plan, FeatureSpec(**features)


def run_phase(config_path: Path, model: str) -> dict:
    root, config, plan, spec = load_context(config_path)
    baseline, old_manifest = read_baseline(root / config["baseline_run"])
    directory = root / config["report_root"] / (model + "_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    directory.mkdir(parents=True, exist_ok=False)
    save_json(directory / "spec_freeze.json", {"created_at_utc": datetime.now(timezone.utc).isoformat(), "config": config,
                                              "config_sha256": digest(config_path), "model": model, "validation_fit_started": False})
    store = load_development_store(root, root / config["day2_config"])
    evaluation_start = perf_counter()
    result = evaluate_model(store, plan, spec, config[model], model)
    evaluation_wall_seconds = perf_counter() - evaluation_start
    baseline_keys = {(row["forecast_origin"], row["horizon"]): row for row in baseline}
    for row in result["rows"]:
        original = baseline_keys[(row["forecast_origin"], row["horizon"])]
        if any(row[field] != original[field] for field in ("actual_price", "mase_scale", "target_month", "unit")):
            raise ValueError("Day 3 actual/scale/unit/target contract mismatch")
    save_csv(directory / "predictions.csv", result["rows"])
    save_json(directory / "fold_fit_log.json", result["events"])
    save_json(directory / "metrics.json", result["metrics"])
    timings = timing_summary(result["events"])
    timings["evaluation_wall_seconds"] = evaluation_wall_seconds
    save_json(directory / "timing.json", timings)
    package = Path(__file__).resolve().parents[1]
    source_files = [Path(__file__).resolve(), package / f"forecasting/{model}.py", package / "forecasting/common.py",
                    package / "features/price.py", package / "data/availability.py", package / "evaluation/splits.py",
                    package / "evaluation/forecast_metrics.py"]
    save_json(directory / "manifest.json", {
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "model": model, "config": config,
        "config_sha256": digest(config_path), "split_sha256": digest(root / config["split_config"]),
        "baseline_manifest_sha256": digest(root / config["baseline_run"] / "run_manifest.json"),
        "input_snapshot": old_manifest["raw_snapshot_id"], "raw_sha256": old_manifest["raw_sha256"],
        "processed_input": old_manifest["selected_processed_input"], "feature_spec": asdict(spec),
        "python": sys.version, "library_versions": {name: version(name) for name in ("statsmodels", "lightgbm", "patsy", "numpy", "scipy", "pandas", "packaging")},
        "code_sha256": {path.relative_to(package).as_posix(): digest(path) for path in source_files},
        "output_sha256": {path.name: digest(path) for path in sorted(directory.iterdir()) if path.is_file()},
        "holdout_locked": True, "fallback": None, "search": False,
        "vintage_mode": "latest_vintage_pseudo_real_time", "complete": result["metrics"]["complete"],
        "threads": {name: os.environ[name] for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")},
    })
    return {"report_dir": directory.relative_to(root).as_posix(), "model": model, "complete": result["metrics"]["complete"],
            "overall": result["metrics"]["overall"], "timing": {key: value for key, value in timings.items() if key != "origin_fit_seconds"}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/day4.toml"))
    parser.add_argument("--model", choices=("sarimax", "lightgbm"), required=True)
    args = parser.parse_args()
    print(json.dumps(run_phase(args.config, args.model), indent=2))
